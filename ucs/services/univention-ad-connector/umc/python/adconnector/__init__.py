#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: AD connector
#
# Copyright 2011-2012 Univention GmbH
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

import univention.config_registry
from univention.lib import Translation
from univention.management.console.modules import Base
from univention.management.console.log import MODULE
from univention.management.console.config import ucr

import notifier.popen

import fnmatch
import psutil
import os, stat, shutil

import subprocess, time, grp

import string, ldap

_ = Translation('univention-management-console-module-top').translate

FN_BINDPW = '/etc/univention/connector/ad/bindpw'
DIR_WEB_AD = '/var/www/univention-ad-connector'
DO_NOT_CHANGE_PWD = '********************'

class ConnectorError( Exception ):
	pass

class Instance( Base ):
	OPTION_MAPPING = ( ( 'LDAP_Host', 'connector/ad/ldap/host', '' ),
					   ( 'LDAP_Base', 'connector/ad/ldap/base', '' ),
					   ( 'LDAP_BindDN', 'connector/ad/ldap/binddn', '' ),
					   ( 'KerberosDomain', 'connector/ad/mapping/kerberosdomain', '' ),
					   ( 'PollSleep', 'connector/ad/poll/sleep', 5 ),
					   ( 'RetryRejected', 'connector/ad/retryrejected', 10 ),
					   ( 'DebugLevel', 'connector/debug/level', 1 ),
					   ( 'DebugFunction', 'connector/debug/function', False ),
					   ( 'MappingSyncMode', 'connector/ad/mapping/syncmode', 'sync' ),
					   ( 'MappingGroupLanguage', 'connector/ad/mapping/group/language', 'de' ) )

	def __init__( self ):
		Base.__init__( self )
		self.status_configured = False
		self.status_certificate = False
		self.status_running = False
		self.guessed_baseDN = None

		self.__update_status()

	def state( self, request ):
		"""Retrieve current status of the UCS Active Directory Connector configuration and the service

		options: {}

		return: { 'configured' : (True|False), 'certificate' : (True|False), 'running' : (True|False) }
		"""

		self.__update_status()
		self.finished( request.id, {
			'configured' : self.status_configured,
			'certificate' : self.status_certificate,
			'running' : self.status_running
			} )

	def load( self, request ):
		"""Retrieve current status of the UCS Active Directory Connector configuration and the service

		options: {}

		return: { <all AD connector UCR variables> }
		"""

		result = {}
		for option, var, default in Instance.OPTION_MAPPING:
			result[ option ] = ucr.get( var, default )

		pwd_file = ucr.get( 'connector/ad/ldap/bindpw' )
		result[ 'passwordExists' ] = bool( pwd_file and os.path.exists( pwd_file ) )

		self.finished( request.id, result )

	def save( self, request ):
		"""Saves the UCS Active Directory Connector configuration

		options:
			LDAP_Host: hostname of the AD server
			LDAP_Base: LDAP base of the AD server
			LDAP_BindDN: LDAP DN to use for authentication
			KerberosDomain: kerberos domain
			PollSleep: time in seconds between polls
			RetryRejected: how many time to retry a synchronisation
			MappingSyncMode: synchronisation mode
			MappingGroupLanguage: language of the AD server

		return: { 'success' : (True|False), 'message' : <details> }
		"""

		self.required_options( request, *map( lambda x: x[ 0 ], Instance.OPTION_MAPPING ) )
		self.guessed_baseDN = None

		try:
			fn = '%s/.htaccess' % DIR_WEB_AD
			fd = open( fn, 'w' )
			fd.write( 'require user %s\n' % self._username )
			fd.close()
			os.chmod( fn, 0644 )
			os.chown( fn, 0, 0 )
		except Exception, e:
			message = _( 'An error occured while saving .htaccess (filename=%(fn)s ; exception=%(exception)s)') % { 'fn': fn, 'exception': e.__class__.__name__ }
			MODULE.process( 'An error occured while saving .htaccess (filename=%(fn)s ; exception=%(exception)s)' % { 'fn': fn, 'exception': e.__class__.__name__ } )
			self.finished( request.id, { 'success' : False, 'message' : message } )
			return

		for umckey, ucrkey, default in Instance.OPTION_MAPPING:
			val = request.options[ umckey ]
			if val:
				if isinstance( val, bool ):
					val = val and 'yes' or 'no'
				MODULE.info( 'Setting %s=%s' % ( ucrkey, val ) )
				univention.config_registry.handler_set( [ u'%s=%s' % ( ucrkey, val ) ] )

		ucr.load()
		if ucr.get('connector/ad/ldap/ldaps' ):
			MODULE.info( 'Unsetting connector/ad/ldap/ldaps' )
			univention.config_registry.handler_unset( [ u'connector/ad/ldap/ldaps' ] )
		if ucr.get( 'connector/ad/ldap/port' ) == '636':
			MODULE.info( 'Setting ldap port to 389' )
			univention.config_registry.handler_set( [ u'connector/ad/ldap/port=389' ] )

		if not request.options.get( 'LDAP_Password' ) in ( None, '', DO_NOT_CHANGE_PWD ):
			fn = ucr.get( 'connector/ad/ldap/bindpw', FN_BINDPW )
			try:
				fd = open( fn ,'w')
				fd.write( request.options.get( 'LDAP_Password' ) )
				fd.close()
				os.chmod( fn, 0600 )
				os.chown( fn, 0, 0 )
				univention.config_registry.handler_set( [ u'connector/ad/ldap/bindpw=%s' % fn ] )
			except Exception, e:
				MODULE.info( 'Saving bind password failed (filename=%(fn)s ; exception=%(exception)s)' % { 'fn' : fn, 'exception' : str( e.__class__ ) } )
				self.finished( request.id, { 'success' : False, 'message' : _( 'Saving bind password failed (filename=%(fn)s ; exception=%(exception)s)' ) % { 'fn' : fn, 'exception' : str(e.__class__ ) } } )
				return

		if os.path.exists( '/etc/univention/ssl/%s' % request.options.get( 'LDAP_Host' ) ):
			try:
				self._copy_certificate( request )
				self.finished( request.id,  { 'success' : True, 'message' :  _('UCS Active Directory Connector settings have been saved and a new certificate for the Active Directory server has been created.') } )
			except ConnectorError, e:
				self.finished( request.id,  { 'success' : False, 'message' :  str( e ) } )
			return

		def _return(  pid, status, buffer, request ):
			try:
				self._copy_certificate( request, error_if_missing = True )
				self.finished( request.id, { 'success' : True, 'message' :  _('UCS Active Directory Connector settings have been saved.') } )
			except ConnectorError, e:
				self.finished( request.id, { 'success' : False, 'message' : str( e ) } )

		cmd = '/usr/sbin/univention-certificate new -name "%s"' % request.options.get( 'LDAP_Host' )
		MODULE.info( 'Creating new SSL certificate: %s' % cmd )
		proc = notifier.popen.Shell( cmd, stdout = True )
		cb = notifier.Callback( _return, request )
		proc.signal_connect( 'finished', cb )
		proc.start()

	def guess( self, request ):
		"""Tries to guess some values like the base DN of the AD server

		options: { 'LDAP_Host': <ad server fqdn> }

		return: { 'LDAP_Base' : <LDAP base>, 'success' : (True|False) }
		"""
		self.required_options( request, 'LDAP_Host' )

		def _return( pid, status, buffer, request ):
			# dn:
			# namingContexts: DC=ad,DC=univention,DC=de
			# namingContexts: CN=Configuration,DC=ad,DC=univention,DC=de
			# namingContexts: CN=Schema,CN=Configuration,DC=ad,DC=univention,DC=de
			# namingContexts: DC=DomainDnsZones,DC=ad,DC=univention,DC=de
			# namingContexts: DC=ForestDnsZones,DC=ad,DC=univention,DC=de

			self.guessed_baseDN = None
			for line in buffer:
				if line.startswith( 'namingContexts: ' ):
					dn = line.split(': ',1)[1].strip()
					if self.guessed_baseDN is None or len( dn ) < len( self.guessed_baseDN ):
						self.guessed_baseDN = dn

			if self.guessed_baseDN is None:
				self.finished( request.id, { 'success' : False, 'message' : _('The LDAP base of the given Active Directory server could not be determined. Maybe the full-qualified hostname is wrong or unresolvable.' ) } )
				MODULE.process( 'Could not determine baseDN of given ldap server. Maybe FQDN is wrong or unresolvable! FQDN=%s' % request.options[ 'baseDN' ] )
			else:
				self.finished( request.id, { 'success' : True, 'LDAP_Base' : self.guessed_baseDN } )

			MODULE.info( 'Guessed the LDAP base: %s' % self.guessed_baseDN )


		cmd = '/usr/bin/ldapsearch -x -s base -b "" namingContexts -LLL -h "%s"' % request.options[ 'LDAP_Host' ]
		MODULE.info( 'Determine LDAP base for AD server of specified system FQDN: %s' % cmd )
		proc = notifier.popen.Shell( cmd, stdout = True )
		cb = notifier.Callback( _return, request )
		proc.signal_connect( 'finished', cb )
		proc.start()

	def _copy_certificate( self, request, error_if_missing = False ):
		ssldir = '/etc/univention/ssl/%s' % request.options.get( 'LDAP_Host' )
		try:
			gid_wwwdata = grp.getgrnam('www-data')[2]
		except:
			gid_wwwdata = 0
		if os.path.exists( ssldir ):
			for fn in ( 'private.key', 'cert.pem' ):
				dst = '%s/%s' % (DIR_WEB_AD, fn)
				try:
					shutil.copy2( '%s/%s' % ( ssldir, fn ), dst )
					os.chmod( dst, 0440 )
					os.chown( dst, 0, gid_wwwdata )
				except Exception, e:
					MODULE.process( 'Copying of %s/%s to %s/%s failed (exception=%s)' % ( ssldir, fn, DIR_WEB_AD, fn, str( e.__class__ ) ) )
					raise ConnectorError(  _( 'Copying of %s/%s to %s/%s failed (exception=%s)') % ( ssldir, fn, DIR_WEB_AD, fn, e.__class__.__name__ ) )
		else:
			if error_if_missing:
				MODULE.error( 'Creation of certificate failed (%s)' % ssldir )
				raise ConnectorError( _('Creation of certificate failed (%s)') % ssldir )


	def upload_certificate( self, request ):
		def _return( pid, status, bufstdout, bufstderr, request, fn ):
			success = True
			if status == 0:
				univention.config_registry.handler_set( [ u'connector/ad/ldap/certificate=%s' % fn ] )
				message = _( 'Certificate has been uploaded successfully.' )
				MODULE.info( 'Certificate has been uploaded successfully. status=%s\nSTDOUT:\n%s\n\nSTDERR:\n%s' % ( status, '\n'.join( bufstdout ), '\n'.join( bufstderr ) ) )
			else:
				success = False
				message = _( 'Certificate upload or conversion failed.' )
				MODULE.process( 'Certificate upload or conversion failed. status=%s\nSTDOUT:\n%s\n\nSTDERR:\n%s' % ( status, '\n'.join( bufstdout ), '\n'.join( bufstderr ) ) )

			self.finished( request.id, [ { 'success' : success, 'message' : message } ] )

		upload = request.options[ 0 ][ 'tmpfile' ]
		now = time.strftime( '%Y%m%d_%H%M%S', time.localtime() )
		fn = '/etc/univention/connector/ad/ad_cert_%s.pem' % now
		cmd = '/usr/bin/openssl x509 -inform der -outform pem -in %s -out %s 2>&1' % ( upload, fn )

		MODULE.info( 'Converting certificate into correct format: %s' % cmd )
		proc = notifier.popen.Shell( cmd, stdout = True, stderr = True )
		cb = notifier.Callback( _return, request, fn )
		proc.signal_connect( 'finished', cb )
		proc.start()

	def service( self, request ):
		MODULE.info( 'State: options=%s' % request.options )
		self.required_options( request, 'action' )

		self.__update_status()
		action = request.options[ 'action' ]

		MODULE.info( 'State: action=%s  status_running=%s' % ( action, self.status_running ) )

		success = True
		message = None
		if self.status_running and action == 'start':
			message = _( 'Active Directory Connector is already running. Nothing to do.' )
		elif not self.status_running and action == 'stop':
			message =_( 'Active Directory Connector is already stopped. Nothing to do.' )
		elif action not in ( 'start', 'stop' ):
			MODULE.process( 'State: unknown command: action=%s' % action )
			message = _( 'Unknown command ("%s") Please report error to your local administrator' ) % action
			success = False

		if message is not None:
			self.finished( request.id, { 'success' : success, 'message' : message } )
			return

		def _run_it( action ):
			return subprocess.call( ( 'invoke-rc.d', 'univention-ad-connector', action ) )

		def _return( thread, result, request ):
			success = not result
			if result:
				message = _('Switching running state of Active Directory Connector failed.')
				MODULE.info( 'Switching running state of Active Directory Connector failed. exitcode=%s' % result )
			else:
				if request.options.get( 'action' ) == 'start':
					message = _( 'UCS Active Directory Connector has been started.' )
				else:
					message = _( 'UCS Active Directory Connector has been stopped.' )

			self.finished( request.id, { 'success' : success, 'message' : message } )

		cb = notifier.Callback( _return, request )
		func = notifier.Callback( _run_it, action )
		thread = notifier.threads.Simple( 'service', func, cb )
		thread.run()

	def __update_status( self ):
		ucr.load()
		self.status_configured = bool( ucr.get( 'connector/ad/ldap/host' ) and ucr.get( 'connector/ad/ldap/base' ) and ucr.get( 'connector/ad/ldap/binddn' ) and ucr.get( 'connector/ad/ldap/bindpw' ) )
		fn = ucr.get( 'connector/ad/ldap/certificate' )
		self.status_certificate = bool( fn and os.path.exists( fn ) )
		self.status_running = self.__is_process_running( '*python*univention/connector/ad/main.py*' )

	def __is_process_running( self, command ):
		for proc in psutil.process_iter():
			if proc.cmdline and fnmatch.fnmatch( ' '.join( proc.cmdline ), command ):
				return True
		return False
