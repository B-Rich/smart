#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  session handling
#
# Copyright 2006-2012 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

"""Implements several helper classes to handle the state of a session
and the communication with the module processes"""

import base64
import ldap
import os
import time
import json

import notifier
import notifier.signals as signals
import notifier.popen as popen

from OpenSSL import *

import univention.admin.uldap as udm_uldap
import univention.admin.objects as udm_objects
import univention.admin.modules as udm_modules
import univention.admin.uexceptions as udm_errors

users_module = None


from univention.lib.i18n import Translation, I18N_Error

from .message import Response, Request, MIMETYPE_JSON, InvalidOptionsError
from .client import Client, NoSocketError
from .version import VERSION
from .definitions import *

from ..resources import moduleManager, categoryManager
from ..auth import AuthHandler
from ..acl import LDAP_ACLs
from ..log import CORE
from ..config import MODULE_INACTIVITY_TIMER, MODULE_DEBUG_LEVEL, MODULE_COMMAND, ucr
from ..locales import I18N, I18N_Manager

TEMPUPLOADDIR = '/var/tmp/univention-management-console-frontend'

class State( signals.Provider ):
	"""Holds information about the state of an active session

	:param str client: IP address + port
	:param fd socket: file descriptor or socket obbject
	"""
	def __init__( self, client, socket ):
		signals.Provider.__init__( self )
		self.__auth = AuthHandler()
		self.__auth.signal_connect( 'authenticated', self._authenticated )
		self.client = client
		self.socket = socket
		self.processor = None
		self.authenticated = False
		self.buffer = ''
		self.requests = {}
		self.authResponse = None
		self.signal_new( 'authenticated' )
		self.resend_queue = []
		self.running = False
		self.username = None

	def __del__( self ):
		CORE.info( 'The session is shutting down' )
		del self.processor

	def _authenticated( self, success ):
		self.signal_emit( 'authenticated', success, self )

	def authenticate( self, username, password ):
		"""Initiates an authentication process"""
		self.username = username
		self.__auth.authenticate( username, password )

	def credentials( self ):
		"""Returns the credentials"""
		return self.__auth.credentials()


class ModuleProcess( Client ):
	"""handles the communication with a UMC module process

	:param str module: name of the module to start
	:param str debug: debug level as a string
	:param str locale: locale to use for the module process
	"""

	def __init__( self, module, debug = '0', locale = None ):
		socket = '/var/run/univention-management-console/%u-%lu.socket' % ( os.getpid(), long( time.time() * 1000 ) )
		# determine locale settings
		modxmllist = moduleManager[ module ]
		args = [ MODULE_COMMAND, '-m', module, '-s', socket, '-d', str( debug ) ]
		for modxml in modxmllist:
			if modxml.notifier:
				args.extend( [ '-n', modxml.notifier ] )
				break
		if locale:
			args.extend( ( '-l', '%s' % locale ) )
			self.__locale = locale
		else:
			self.__locale = None
		Client.__init__( self, unix = socket, ssl = False, auth = False )
		self.signal_connect( 'response', self._response )
		CORE.process( 'running: %s' % args )
		self.__process = popen.RunIt( args, stdout = False )
		self.__process.signal_connect( 'killed', self._died )
		self.__pid = self.__process.start()
		self._connect_retries = 1
		self.signal_new( 'result' )
		self.signal_new( 'finished' )
		self.name = module
		self.running = False
		self._queued_requests = []
		self._inactivity_timer = None
		self._inactivity_counter = 0

	def __del__( self ):
		CORE.process( 'ModuleProcess: dying' )
		self.disconnect()
		self.__process.signal_disconnect( 'killed', self._died )
		self.__process.stop()
		CORE.process( 'ModuleProcess: child stopped' )

	def _died( self, pid, status ):
		CORE.process( 'ModuleProcess: child died' )
		self.signal_emit( 'finished', pid, status )

	def _response( self, msg ):
		# these responses must not be send to the external client as
		# this commands were generated within the server
		if msg.command == 'SET' and 'commands/permitted' in msg.arguments:
			return
		if msg.command == 'EXIT' and 'internal' in msg.arguments:
			return

		self.signal_emit( 'result', msg )

	def pid( self ):
		"""Returns process ID of module process"""
		return self.__pid

class Processor( signals.Provider ):
	"""Implements a proxy and command handler. It handles all internal
	UMCP commands and passes the commands for a module to the
	subprocess.

	:param str username: name of the user who authenticated for this session
	:param str password: password of the user
	"""

	def __init__( self, username, password ):
		global users_module
		self.__username = username
		self.__password = password
		self.__user_dn = None
		signals.Provider.__init__( self )
		self.core_i18n = Translation( 'univention-management-console' )
		self.i18n = I18N_Manager()
		self.i18n[ 'umc-core' ] = I18N()

		# stores the module processes [ modulename ] = <>
		self.__processes = {}

		self.__killtimer = {}

		lo = ldap.open( ucr[ 'ldap/server/name' ], int( ucr.get( 'ldap/server/port', 7389 ) ) )

		try:
			# get LDAP connection with machine account
			self.lo, self.po = udm_uldap.getMachineConnection( ldap_master = False )

			# get the LDAP DN of the authorized user
			ldap_dn = self.lo.searchDn( '(&(uid=%s)(objectClass=posixAccount))' % self.__username )
			if ldap_dn:
				self.__user_dn = ldap_dn[ 0 ]
				CORE.info( 'The LDAP DN for user %s is %s' % ( self.__username, self.__user_dn ) )
			else:
				CORE.info( 'The LDAP DN for user %s could not be found' % self.__username )

			# initiate the users/user UDM module
			udm_modules.update()
			users_module = udm_modules.get('users/user')
			udm_modules.init(self.lo, self.po, users_module)
		except ( ldap.LDAPError, IOError ) as e:
			# problems connection to LDAP server or the server is not joined (machine.secret is missing)
			CORE.warn('An error occurred connecting to the LDAP server: %s' % e)
			self.lo = None
			users_module = None
		except udm_errors.base as e:
			# UDM error, user module coule not be initiated
			CORE.warn('An error occurred intializing the UDM users/user module: %s' % e)
			users_module = None

		# read the ACLs
		self.acls = LDAP_ACLs( self.lo, self.__username, ucr[ 'ldap/base' ] )
		self.__command_list = moduleManager.permitted_commands( ucr[ 'hostname' ], self.acls )

		self.signal_new( 'response' )

	def shutdown( self ):
		"""Instructs the module process to shutdown"""
		CORE.info( 'The session is shutting down. Sending UMC modules an EXIT request (%d processes)' % len( self.__processes ) )
		for module_name in self.__processes:
			CORE.info( 'Ask module %s to shutdown gracefully' % module_name )
			req = Request( 'EXIT', arguments = [ module_name, 'internal' ] )
			self.__processes[ module_name ].request( req )

	def __del__( self ):
		CORE.process( 'Processor: dying' )
		for process in self.__processes.values():
			del process

	def get_module_name( self, command ):
		"""Returns the name of the module that provides the given command

		:param str command: the command name
		"""
		return moduleManager.module_providing( self.__comand_list, command )

	def request( self, msg ):
		"""Handles an incoming UMCP request and passes the requests to
		specific handler functions.

		:param Request msg: UMCP request
		"""
		if msg.command == 'EXIT':
			self.handle_request_exit( msg )
		elif msg.command == 'GET':
			self.handle_request_get( msg )
		elif msg.command == 'SET':
			self.handle_request_set( msg )
		elif msg.command == 'VERSION':
			self.handle_request_version( msg )
		elif msg.command == 'COMMAND':
			self.handle_request_command( msg )
		elif msg.command == 'UPLOAD':
			self.handle_request_upload( msg )
		elif msg.command in ( 'STATUS', 'CANCEL', 'CLOSE' ):
			self.handle_request_unknown( msg )
		else:
			self.handle_request_unknown( msg )

	def _purge_child(self, module_name):
		if module_name in self.__processes:
			CORE.process( 'module %s is still running - purging module out of memory' % module_name)
			pid = self.__processes[ module_name ].pid()
			os.kill(pid, 9)
		return False

	def handle_request_exit( self, msg ):
		"""Handles an EXIT request. If the request does not have an
		argument that contains a valid name of a running UMC module
		instance the request is returned as a bad request.

		If the request is valid it is passed on to the module
		process. Additionally a timer of 3000 milliseconds is
		started. After that amount of time the module process MUST have
		been exited itself. If not the UMC server will kill the module
		process.

		:param Request msg: UMCP request
		"""
		if len( msg.arguments ) < 1:
			return self.handle_request_unknown( msg )

		module_name = msg.arguments[ 0 ]
		if module_name:
			if module_name in self.__processes:
				self.__processes[ module_name ].request( msg )
				CORE.info( 'Ask module %s to shutdown gracefully' % module_name )
				# added timer to kill away module after 3000ms
				cb = notifier.Callback( self._purge_child, module_name )
				self.__killtimer[ module_name ] = notifier.timer_add( 3000, cb )
			else:
				CORE.info( 'Got EXIT request for a non-existing module %s' % module_name )

	def handle_request_version( self, msg ):
		"""Handles a VERSION request by returning the version of the UMC
		server's protocol version.

		:param Request msg: UMCP request
		"""
		res = Response( msg )
		res.status = SUCCESS # Ok
		res.body[ 'version' ] = VERSION

		self.signal_emit( 'response', res )

	def _get_user_obj(self):
		try:
			# make sure that the UDM users/user module could be initiated
			if not users_module:
				raise udm_errors.base('UDM module users/user could not be initiated')

			# open an LDAP connection with the user password and credentials
			lo = udm_uldap.access(host = ucr.get('ldap/server/name'), base = ucr.get('ldap/base'), port = int(ucr.get('ldap/server/port', '7389')), binddn = self.__user_dn, bindpw = self.__password, follow_referral=True)

			# try to open the user object
			userObj = udm_objects.get(users_module, None, lo, self.po, self.__user_dn)
			if not userObj:
				raise udm_errors.noObject()
			userObj.open()
			return userObj
		except udm_errors.noObject as e:
			CORE.warn('Failed to open UDM user object for user %s' % (self.__username))
		except (udm_errors.base, ldap.LDAPError) as e:
			CORE.warn('Failed to open UDM user object %s: %s' % (self.__user_dn, e))
		return None

	def handle_request_get( self, msg ):
		"""Handles a GET request. The following possible variants are supported:

		modules/list
			Returns a list of all available UMC modules within the current session

		categories/list
			Returns a list of all known categories

		user/preferences
			Returns the user preferences as a dict.

		:param Request msg: UMCP request
		"""

		res = Response( msg )

		if 'modules/list' in msg.arguments:
			modules = []
			for id, module in self.__command_list.items():
				# check for translation
				if module.flavors:
					for flavor in module.flavors:
						translationId = flavor.translationId
						if not translationId:
							translationId = id
						modules.append( { 'id' : id, 'flavor' : flavor.id, 'name' : self.i18n._( flavor.name, translationId ), 'description' : self.i18n._( flavor.description, translationId ), 'icon' : flavor.icon, 'categories' : module.categories, 'priority' : flavor.priority } )
				else:
						modules.append( { 'id' : id, 'name' : self.i18n._( module.name, id ), 'description' : self.i18n._( module.description, id ), 'icon' : module.icon, 'categories' : module.categories, 'priority' : module.priority } )
			res.body[ 'modules' ] = modules
			_ucr_dict = dict( ucr.items() )

			categories = []
			for catID, category in categoryManager.items():
				categories.append( { 'id' : catID, 'name' : self.i18n._( category.name, category.domain ).format( **_ucr_dict ), 'priority' : category.priority } )

			res.body[ 'categories' ] = categories
			CORE.info( 'Modules: %s' % modules )
			CORE.info( 'Categories: %s' % str( res.body[ 'categories' ] ) )
			res.status = SUCCESS # Ok

		elif 'categories/list' in msg.arguments:
			res.body[ 'categories' ] = categoryManager.all()
			res.status = SUCCESS # Ok
		elif 'user/preferences' in msg.arguments:
			# fallback is an empty dict
			res.body['preferences'] = {}

			# query user's UMC properties
			userObj = self._get_user_obj()
			if userObj:
				res.body['preferences'] = dict(userObj.info.get('umcProperty', []))
				res.status = SUCCESS
			else:
				res.status = BAD_REQUEST_INVALID_OPTS
		else:
			res.status = BAD_REQUEST_INVALID_ARGS

		self.signal_emit( 'response', res )

	def handle_request_set( self, msg ):
		"""Handles a SET request. No argument may be given. The
		variables that should be set are passed via the request
		options. Currently the only variable that may be set is the
		locale. If any unknown variable is given the the request is
		invalidated.

		:param Request msg: UMCP request
		"""
		res = Response( msg )
		if len( msg.arguments ):
			res.status = BAD_REQUEST_INVALID_ARGS
			res.message = status_description( res.status )

			self.signal_emit( 'response', res )
			return

		res.status = SUCCESS
		if not isinstance(msg.options, dict):
			raise InvalidOptionsError
		for key, value in msg.options.items():
			if key == 'locale':
				try:
					self.core_i18n.set_language( value )
					CORE.info( 'Setting locale: %s' % value )
					self.i18n.set_locale( value )
				except I18N_Error, e:
					res.status = BAD_REQUEST_UNAVAILABLE_LOCALE
					res.message = status_description( res.status )
					CORE.warn( 'Setting locale to specified locale failed (%s)' % value )
					CORE.warn( 'Falling back to C' )
					self.core_i18n.set_language( 'C' )
					self.i18n.set_locale( 'C' )
					break
			elif key == 'user' and isinstance(value, dict) and 'preferences' in value:
				# try to open the user object
				userObj = self._get_user_obj()
				if not userObj:
					res.status = BAD_REQUEST_INVALID_OPTS
					res.message = status_description( res.status )
					break
				try:
					# make sure we got a dict
					prefs = value['preferences']
					if not isinstance(prefs, dict):
						raise ValueError('user preferences are not a dict: %s' % prefs)

					# iterate over all given user preferences
					newPrefs = []
					for prefKey, prefValue in prefs.iteritems():
						if not isinstance(prefKey, basestring):
							raise ValueError('user preferences keys needs to be strings: %s' % prefKey)

						# we can put strings directly into the dict
						if isinstance(prefValue, basestring):
							newPrefs.append((prefKey, prefValue))
						else:
							newPrefs.append((prefKey, json.dumps(prefValue)))

					if newPrefs:
						# eliminate double entries
						newPrefs = dict(userObj.info.get('umcProperty', []) + newPrefs)

						# apply changes
						userObj.info['umcProperty'] = newPrefs.items()
						userObj.modify()

				except (ValueError, udm_errors.base) as e:
					CORE.warn('Could not set given option: %s' % e)
					res.status = BAD_REQUEST_INVALID_OPTS
					res.message = status_description( res.status )
					break
			else:
				res.status = BAD_REQUEST_INVALID_OPTS
				res.message = status_description( res.status )
				break

		self.signal_emit( 'response', res )

	def __is_command_known( self, msg ):
		# only one command?
		command = None
		if len( msg.arguments ) > 0:
			command = msg.arguments[ 0 ]

		module_name = moduleManager.module_providing( self.__command_list, command )
		if not module_name:
			res = Response( msg )
			res.status = BAD_REQUEST_FORBIDDEN
			res.message = status_description( res.status )
			self.signal_emit( 'response', res )
			return None

		return module_name

	def _inactivitiy_tick( self, module ):
		if module._inactivity_counter > 0:
			module._inactivity_counter -= 1000
			return True
		if self._mod_inactive( module ): # open requests -> waiting
			module._inactivity_counter = MODULE_INACTIVITY_TIMER
			return True

		module._inactivity_timer = None
		module._inactivity_counter = 0

		return False

	def reset_inactivity_timer( self, module ):
		"""Resets the inactivity timer. This timer watches the
		inactivity of the module process. If the module did not receive
		a request for MODULE_INACTIVITY_TIMER seconds the module process
		is shut down to save resources. The timer ticks each seconds to
		handle glitches of the system clock.

		:param Module module: a module 
		"""
		if module._inactivity_timer is None:
			module._inactivity_timer = notifier.timer_add( 1000, notifier.Callback( self._inactivitiy_tick, module ) )

		module._inactivity_counter = MODULE_INACTIVITY_TIMER

	def handle_request_upload( self, msg ):
		"""Handles an UPLOAD request. The command is used for the HTTP
		access to the UMC server. Incoming HTTP requests that send a
		list of files are passed on to the UMC server by storing the
		files in temporary files and passing the information about the
		files to the UMC server in the options of the request. The
		request options must be a list of dictionaries. Each dictionary
		must contain the following keys:

		* *filename* -- the original name of the file
		* *name* -- name of the form field
		* *tmpfile* -- filename of the temporary file

		:param Request msg: UMCP request
		"""
		# request.options = ( { 'filename' : store.filename, 'name' : store.name, 'tmpfile' : tmpfile } )

		if not isinstance( msg.options, ( list, tuple ) ):
			raise InvalidOptionsError

		for file_obj in msg.options:
			# check if required options exists and file_obj is a dict
			try:
				tmpfilename, filename, name = file_obj['tmpfile'], file_obj['filename'], file_obj['name']
			except:
				raise InvalidOptionsError('required options "tmpfile", "filename" or "name" is missing')

			# limit files to tmpdir
			if not os.path.realpath(tmpfilename).startswith(TEMPUPLOADDIR):
				raise InvalidOptionsError('invalid file: invalid path')

			# check if file exists
			if not os.path.isfile( tmpfilename ):
				raise InvalidOptionsError('invalid file: file does not exists')

			# don't accept files bigger than umc/server/upload/max
			st = os.stat( tmpfilename )
			max_size = int( ucr.get( 'umc/server/upload/max', 64 ) ) * 1024
			if st.st_size > max_size:
				raise InvalidOptionsError('filesize is too large, maximum allowed filesize is %d' % (max_size,))

		if msg.arguments and msg.arguments[0] not in ('', '/'):
			# The request has arguments, so it will be treaten as COMMAND
			self.handle_request_command(msg)
			return

		# The request is an generic UPLOAD command (/upload)
		result = []
		for file_obj in msg.options:
			# read tmpfile and convert to base64
			tmpfilename, filename, name = file_obj['tmpfile'], file_obj['filename'], file_obj['name']
			with open( tmpfilename ) as buf:
				b64buf = base64.b64encode( buf.read() )
			result.append( { 'filename' : filename, 'name' : name, 'content' : b64buf } )

		response = Response( msg )
		response.result = result
		response.status = SUCCESS

		self.signal_emit( 'response', response )

	def handle_request_command( self, msg ):
		"""Handles a COMMAND request. The request must contain a valid
		and known command that can be accessed by the current user. If
		access to the command is prohibited the request is answered as a
		forbidden command.

		If there is no running module process for the given command a
		new one is started and the request is added to a queue of
		requests that will be passed on when the process is ready.

		If a module process is already running the request is passed on
		and the inactivity timer is reset.

		:param Request msg: UMCP request
		"""
		module_name = self.__is_command_known( msg )
		if module_name and msg.arguments:
			if msg.mimetype == MIMETYPE_JSON:
				is_allowed = self.acls.is_command_allowed( msg.arguments[ 0 ], options = msg.options, flavor = msg.flavor )
			else:
				is_allowed = self.acls.is_command_allowed( msg.arguments[ 0 ] )
			if not is_allowed:
				response = Response( msg )
				response.status = BAD_REQUEST_FORBIDDEN
				response.message = status_description( response.status )
				self.signal_emit( 'response', response )
				return
			if not module_name in self.__processes:
				CORE.info( 'Starting new module process and passing new request to module %s: %s' % (module_name, str(msg._id)) )
				mod_proc = ModuleProcess( module_name, debug = MODULE_DEBUG_LEVEL, locale = self.i18n.locale )
				mod_proc.signal_connect( 'result', self._mod_result )
				cb = notifier.Callback( self._socket_died, module_name )
				mod_proc.signal_connect( 'closed', cb )
				cb = notifier.Callback( self._mod_died, module_name )
				mod_proc.signal_connect( 'finished', cb )
				self.__processes[ module_name ] = mod_proc
				cb = notifier.Callback( self._mod_connect, mod_proc, msg )
				notifier.timer_add( 50, cb )
			else:
				proc = self.__processes[ module_name ]
				if proc.running:
					CORE.info( 'Passing new request to running module %s' % module_name )
					proc.request( msg )
					self.reset_inactivity_timer( proc )
				else:
					CORE.info( 'Queuing incoming request for module %s that is not yet ready to receive' % module_name )
					proc._queued_requests.append( msg )

	def _mod_connect( self, mod, msg ):
		"""Callback for a timer event: Trying to connect to newly started module process"""
		def _send_error():
			# inform client
			res = Response( msg )
			res.status = SERVER_ERR_MODULE_FAILED # error connecting to module process
			res.message = status_description( res.status )
			self.signal_emit( 'response', res )
			# cleanup module
			mod.signal_disconnect( 'closed', notifier.Callback( self._socket_died ) )
			mod.signal_disconnect( 'result', notifier.Callback( self._mod_result ) )
			mod.signal_disconnect( 'finished', notifier.Callback( self._mod_died ) )
			if mod.name in self.__processes:
				del self.__processes[ mod.name ]

		try:
			mod.connect()
		except NoSocketError:
			if mod._connect_retries > 200:
				CORE.info( 'Connection to module %s process failed' % mod.name )
				_send_error()
				return False
			if not mod._connect_retries % 50:
				CORE.info( 'No connection to module process yet' )
			mod._connect_retries += 1
			return True
		except Exception, e:
			CORE.process( 'Unknown error while trying to connect to module process: %s' % str( e ) )
			_send_error()
			return False
		else:
			CORE.info( 'Connected to new module process' )
			mod.running = True

			# send acls, commands, credentials, locale
			options = {
				'acls' : self.acls.json(),
				'commands' : self.__command_list[ mod.name ].json(),
				'credentials' : { 'username' : self.__username, 'password' : self.__password, 'user_dn' : self.__user_dn },
				}
			if str( self.i18n.locale ):
				options[ 'locale' ] = str( self.i18n.locale )

			# WARNING! This debug message contains credentials!!!
			# CORE.info( 'Initialize module process: %s' % options )

			req = Request( 'SET', options = options )
			mod.request( req )

			# send first command
			mod.request( msg )

			# send queued request that were received during start procedure
			for req in mod._queued_requests:
				mod.request( req )
			mod._queued_requests = []

			# watch the module's activity and kill it after X seconds inactivity
			self.reset_inactivity_timer( mod )

		return False

	def _mod_inactive( self, module ):
		CORE.info( 'The module %s is inactive for to long. Sending EXIT request to module' % module.name )
		if module.openRequests:
			CORE.info( 'There are unfinished requests. Waiting for %s' % ', '.join( module.openRequests ) )
			return True

		# mark as internal so the response will not be forwarded to the client
		req = Request( 'EXIT', arguments = [ module.name, 'internal' ] )
		self.handle_request_exit( req )

		return False

	def _mod_result( self, msg ):
		self.signal_emit( 'response', msg )

	def _socket_died( self, module_name ):
		CORE.warn( 'Socket died (module=%s)' % module_name )
		if module_name in self.__processes:
			self._mod_died( self.__processes[ module_name ].pid(), -1, module_name )

	def _mod_died( self, pid, status, module_name ):
		if status:
			if os.WIFSIGNALED( status ):
				signal = os.WTERMSIG( status )
				exitcode = -1
			elif os.WIFEXITED( status ):
				signal = -1
				exitcode = os.WEXITSTATUS( status )
			else:
				signal = -1
				exitcode = -1
			CORE.warn( 'Module process %s died (pid: %d, exit status: %d, signal: %d)' % ( module_name, pid, exitcode, signal ) )
		else:
			CORE.info( 'Module process %s died on purpose' % module_name )

		# if killtimer has been set then remove it
		CORE.info( 'Checking for kill timer (%s)' % ', '.join( self.__killtimer.keys() ) )
		if module_name in self.__killtimer:
			CORE.info( 'Stopping kill timer)' )
			notifier.timer_remove( self.__killtimer[ module_name ] )
			del self.__killtimer[ module_name ]
		if module_name in self.__processes:
			CORE.warn( 'Cleaning up requests' )
			self.__processes[ module_name ].invalidate_all_requests()
			if self.__processes[ module_name ]._inactivity_timer is not None:
				CORE.warn( 'Remove inactivity timer' )
				notifier.timer_remove( self.__processes[ module_name ]._inactivity_timer )
			del self.__processes[ module_name ]

	def handle_request_unknown( self, msg ):
		"""Handles an unknown or invalid request that is answered with a
		status code BAD_REQUEST_NOT_FOUND.

		:param Request msg: UMCP request
		"""
		res = Response( msg )
		res.status = BAD_REQUEST_NOT_FOUND
		res.message = status_description( res.status )

		self.signal_emit( 'response', res )

if __name__ == '__main__':
	processor = Processor( 'Administrator', 'univention' )
	processor.handle_request_get ( None )
