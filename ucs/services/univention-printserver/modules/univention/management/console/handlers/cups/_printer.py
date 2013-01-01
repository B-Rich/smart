#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  cups module: helper functions for print job management
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

import univention.management.console as umc
import univention.management.console.tools as umct
import univention.management.console.dialog as umcd
import univention.management.console.protocol as umcp

import univention.debug as ud

import notifier.popen

import tools
import pykota

import subprocess

_ = umc.Translation( 'univention.management.console.handlers.cups' ).translate

class Commands( object ):
	def cups_printer_show( self, object ):
		if object.incomplete:
			self.finished( object.id(), [] )
			return

		cmd = '/usr/bin/lpstat -o %s' % object.options[ 'printer' ]
		ud.debug( ud.ADMIN, ud.INFO, 'CUPS.show: command: %s' % cmd )
		processresult = umct.run_process( cmd, timeout = 10000, shell = True, output = True )
		lpstat_o_stdout = processresult['stdout'].readlines()
		ud.debug( ud.ADMIN, ud.INFO, 'CUPS.show: lpstat_o_stdout: %s' % lpstat_o_stdout )
		lpstat_o_stdout = tools.parse_lpstat_o( lpstat_o_stdout )

		cmd = '/usr/bin/lpstat -l -p %s' % object.options[ 'printer' ]
		ud.debug( ud.ADMIN, ud.INFO, 'CUPS.show: command: %s' % cmd )
		processresult = umct.run_process( cmd, timeout = 10000, shell = True, output = True )
		buffer = processresult['stdout'].readlines()
		ud.debug( ud.ADMIN, ud.INFO, 'CUPS.show: lpstat: %s' % buffer )
		self.finished( object.id(), ( lpstat_o_stdout, tools.parse_lpstat_l( buffer ) ) )
		return

	def cups_printer_enable( self, object ):
		cmd = '/usr/bin/univention-cups-enable %s' % ' '.join( object.options[ 'printers' ] )
		ud.debug( ud.ADMIN, ud.INFO, 'CUPS.enable: command: %s' % cmd )
		proc = notifier.popen.Shell( cmd, stdout = False )
		cb = notifier.Callback( self._cups_printer_enable_return, object )
		proc.signal_connect( 'finished', cb )
		proc.start()

	def _cups_printer_enable_return( self, pid, status, object ):
		self.finished( object.id(), [] )

	def cups_printer_disable( self, object ):
		cmd = '/usr/bin/univention-cups-disable %s' % \
			  ' '.join( object.options[ 'printers' ] )
		ud.debug( ud.ADMIN, ud.INFO, 'CUPS.enable: command: %s' % cmd )
		proc = notifier.popen.Shell( cmd, stdout = False )
		cb = notifier.Callback( self._cups_printer_disable_return, object )
		proc.signal_connect( 'finished', cb )
		proc.start()

	def _cups_printer_disable_return( self, pid, status, object ):
		self.finished( object.id(), [] )

	def cups_printer_quota_list( self, object ):
		cmd = '/usr/bin/lpstat -l -p %s' % object.options[ 'printer' ]
		proc = notifier.popen.Shell( cmd, stdout = True )
		cb = notifier.Callback( self._cups_printer_quota_list_return, object )
		proc.signal_connect( 'finished', cb )
		proc.start()

	def _cups_printer_quota_list_return( self, pid, status, buffer, object ):
		cb = notifier.Callback( self._cups_printer_quota_list_return2, object, buffer )
		pykota._pykota_get_quota_users( [ object.options[ 'printer' ] ], cb )

	def _cups_printer_quota_list_return2( self, status, res_pykota, object, printerdata ):
		self.finished( object.id(), ( printerdata, res_pykota ) )

	def cups_quota_user_show( self, object ):
		if object.options.get('printer') and object.options.get('user'):
			cb = notifier.Callback( self._cups_quota_user_show_return, object )
			pykota._pykota_get_quota_users( [ object.options[ 'printer' ] ], cb )
		else:
			self._cups_quota_user_show_return( 0, None, object )
			ud.debug( ud.ADMIN, ud.WARN, 'CUPS.quota_user_show: no printer or no user turned over' )

	def _cups_quota_user_show_return( self, status, res_pykota, object ):
		quota = { 'user': '',
					'printer': '',
					'softlimit': 0,
					'hardlimit': 0 }

		if object.options.get('printer'):
			quota['printer'] = object.options[ 'printer' ]

		if object.options.get('printer') and object.options.get('user'):
			quota['user'] = object.options[ 'user' ]

			if res_pykota:
				# iterate over all printers
				for prn in res_pykota:
					if prn.printername == object.options[ 'printer' ]:
						# correct printer found - interate over all user quotas of that printer
						for uquota in prn.userlist:
							if uquota.user == object.options[ 'user' ]:
								quota['softlimit'] = uquota.softlimit
								quota['hardlimit'] = uquota.hardlimit

		self.finished( object.id(), quota )



	def cups_quota_user_set( self, object ):
		ud.debug( ud.ADMIN, ud.INFO, "cups_quota_user_set: %s" % str( object.options ) )
		if ',' in object.options['user']:
			userlist = object.options['user'].split(',')
		else:
			userlist = [ object.options['user'] ]
		ud.debug( ud.ADMIN, ud.INFO, "cups_quota_user_set: userlist=%s" % str( userlist ) )
		pykota._pykota_set_quota( notifier.Callback( self._cups_quota_user_set_return, object ),
								  printers = [ object.options['printer'] ],
								  userlist = userlist,
								  softlimit = object.options[ 'softlimit' ],
								  hardlimit = object.options[ 'hardlimit' ],
								   add = True )

	def _cups_quota_user_set_return( self, pid, status, result, object ):
		if not status:
			text = _( 'Successfully set print quota settings' )
			self.finished( object.id(), [], report = text, success = True )
		else:
			text = _( 'Failed to modify print quota settings for user %(user)s on printer %(printer)s' ) % object.options
			self.finished( object.id(), [], report = text, success = False )


	def cups_quota_user_reset( self, object ):
		ud.debug( ud.ADMIN, ud.INFO, "cups_quota_user_reset: %s" % str( object.options ) )
		pykota._pykota_set_quota( notifier.Callback( self._cups_quota_user_reset_return, object ),
									printers = [ object.options['printer'] ],
									userlist = object.options['user'],
									reset = True )

	def _cups_quota_user_reset_return( self, pid, status, result, object ):
		if not status:
			text = _( 'Successfully reset print quota' )
			self.finished( object.id(), [], report = text, success = True )
		else:
			text = _( 'Failed to reset print quota for user %(user)s on printer %(printer)s' ) % object.options
			self.finished( object.id(), [], report = text, success = False )
