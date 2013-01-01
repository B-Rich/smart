#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: manages UDM modules
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

import ldap
import ldap.modlist
import ldif
import binascii

from univention.lib.i18n import Translation

from univention.management.console.config import ucr

_ = Translation( 'univention-management-console-module-udm' ).translate

class LicenseError( Exception ):
	pass

class LicenseImport( ldif.LDIFParser ):
	dn = None
	mod_list = []
	dncount = 0
	base = None

	def check( self, base ):
		# call parse from ldif.LDIFParser
		try:
			self.parse()
		except binascii.Error:
			raise LicenseError( _( "No license has been found." ) )

		# there should exactly one object in the the ldif file
		if self.dncount == 0:
			raise LicenseError( _( "No license has been found." ) )
		elif self.dncount > 1:
			raise LicenseError( _( "More than one object has been found." ) )

		# check LDAP base
		if self.base.lower() not in [base.lower(), 'free for personal use edition']:
			raise LicenseError( _( "The license can not be applied. The LDAP base does not match (expected %s, found: %s)." ) % ( base, self.base ) )

	def handle( self, dn, entry ):
		"""This method is invoked bei LDIFParser.parse for each object
		in the ldif file"""

		if dn is None or dn == "":
			return

		self.dn = dn
		self.dncount += 1

		if 'univentionLicenseBaseDN' in entry:
			self.base = str( entry[ 'univentionLicenseBaseDN' ][ 0 ] )
		else:
			return

		#create modification list
		self.addlist = ldap.modlist.addModlist( entry )
		# for atr in entry:
		# 	self.mod_list.insert( 0, ( ldap.MOD_REPLACE, atr, entry[ atr ] ) )

	def write( self, user_dn, passwd ):
		ldap_con = ldap.open( "localhost", port = int( ucr.get( 'ldap/server/port', 7389 ) ) )
		ldap_con.simple_bind_s( user_dn, passwd )
		try:
			ldap_con.add_s( self.dn, self.addlist )
		except ldap.ALREADY_EXISTS:
			ldap_con.delete_s( self.dn )
			ldap_con.add_s( self.dn, self.addlist )
		ldap_con.unbind_s()
