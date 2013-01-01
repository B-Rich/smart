# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: UVMM client
#
# Copyright 2010-2012 Univention GmbH
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

import copy
import fnmatch
import os
import socket
import time

from univention.management.console.log import MODULE

from notifier import Callback
from notifier.signals import Provider
from notifier.popen import CountDown
from notifier.threads import Simple

from univention.lib.i18n import Translation

from univention.uvmm import protocol, node, client

import univention.debug as ud
import traceback

_ = Translation( 'univention-management-console-module-uvmm' ).translate
_uvmm_locale = Translation( 'univention-virtual-machine-manager' ).translate

class UVMM_Error( Exception ):
	"""UVMM-request was not successful."""
	pass

class UVMM_Request( object ):
	def request( self, command, **kwargs ):
		MODULE.info( 'Sending request %s to UVMM daemon ...' % command )
		try:
			request = eval( 'protocol.Request_%s()' % command )
		except NameError, AttributeError:
			MODULE.error( 'Failed to create request %s' % command )
			raise UVMM_Error( _( 'The given UVMM command is not known' ) )
		MODULE.info( 'Setting request arguments ...' )
		for key, value in kwargs.items():
			setattr( request, key, value )
		try:
			MODULE.info( 'Creating UVMM daemon connection' )
			uvmm_client = client.UVMM_ClientUnixSocket( UVMM_ConnectionThread.SOCKET_PATH )
			MODULE.info( 'Sending request: %s' % str( request ) )
			data = uvmm_client.send( request )
			MODULE.info( 'Received response: %s' % str( data ) )
			uvmm_client.close()
			MODULE.info( 'Connection to UVMMd is closed' )
		except client.ClientError, e:
			MODULE.info( 'The UVMM client raised an exception: %s' % str( e ) )
			raise UVMM_Error( str( e ) )

		MODULE.info( 'Returning result from UVMMd' )
		return self.response( data )

	def response( self, result ):
		data = None
		success = result.status == 'OK'
		if isinstance( result, protocol.Response_DUMP ):
			data = result.data
		elif isinstance( result, protocol.Response_ERROR ):
			data = _uvmm_locale( result.translatable_text ) % result.values
		elif isinstance( result, protocol.Response_OK ):
			pass # no further data available
		return ( success, data )

class UVMM_ConnectionThread( Simple, UVMM_Request ):
	SOCKET_PATH = '/var/run/uvmm.socket'

	counter = 0
	def __init__( self ):
		Simple.__init__( self, 'UVMM_Connection-%d' % UVMM_ConnectionThread.counter, None, Callback( self._finished ) )
		UVMM_ConnectionThread.counter += 1
		self.busy = False

	def __call__( self, callback, command, **kwargs ):
		MODULE.info( 'Starting request thread ...' )
		if self.busy:
			MODULE.info( 'Thread is already busy' )
			return False
		self._user_callback = callback
		self._function = Callback( self.request, command, **kwargs )
		self.busy = True
		MODULE.info( 'Thread is working on a request' )
		self.run()
		return True

	def _finished( self, thread, result ):
		MODULE.info( 'Thread returned result: %s' % str( result ) )
		if not isinstance( result, BaseException ):
			self._user_callback( thread, result )
		else:
			MODULE.info( 'Passing exception to user callback' )
			self._user_callback( thread, result )
		self.busy = False
		MODULE.info( 'Thread is free for another request' )

class UVMM_RequestBroker( list ):
	def __init__( self ):
		list.__init__( self )

	def send( self, request, callback, **kwargs ):
		MODULE.info( 'Sending request %s to UVMMd' % request )

		if callback is None: # synchron call
			request_obj = UVMM_Request()
			return request_obj.request( request, **kwargs )

		# cleanup ...
		for thread in copy.copy( self ):
			if not thread.busy:
				self.remove( thread )

		# asynchron call
		free_thread = UVMM_ConnectionThread()
		self.append( free_thread )


		MODULE.info( 'There are currently %d threads running' % len( self ) )
		free_thread( callback, request, **kwargs )
