# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  wrapper around univention.license that translates error codes to exceptions
#
# Copyright 2004-2012 Univention GmbH
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

import operator
import univention.license
import univention.debug
import univention.admin.modules
import univention.admin.uexceptions
import univention.admin.localization
import univention.admin.license_data as licenses
import univention.config_registry

translation=univention.admin.localization.translation('univention/admin')
_=translation.translate

_license = None

configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()

class License( object ):
	( ACCOUNT, CLIENT, DESKTOP, GROUPWARE ) = range( 4 )
	( USERS, SERVERS, MANAGEDCLIENTS, CORPORATECLIENTS, VIRTUALDESKTOPUSERS, VIRTUALDESKTOPCLIENTS ) = range(6)

	SYSACCOUNTS = 5
	def __init__( self ):
		if _license:
			raise 'never create this object directly'
		self.new_license = False
		self.disable_add = 0
		self._expired = False
		self.endDate = None
		self.oemProductTypes = []
		self.licenseBase = None
		self.types= []
		self.version = '1'
		self.sysAccountNames = (
			'Administrator',
			'join-backup',
			'join-slave',
			'spam',
			'oxadmin',
			'krbtgt',
			'Guest',
			'dns-*',
			'http-%s' % configRegistry.get('hostname'),
			'http-proxy-%s' % configRegistry.get('hostname'),
			'zarafa-%s' % configRegistry.get('hostname'),
			'SBSMonAcct',				## SBS account
			'Network Administrator',	## SBS role
			'Standard User',			## SBS role
			'WebWorkplaceTools',		## SBS role "Standard User with administration links"
			'IUSR_WIN-*',				## IIS account
		)
		self.sysAccountsFound = 0
		self.licenses = {
				'1': {
					# Version 1 till UCS 3.1
					License.ACCOUNT : None, License.CLIENT : None,
					License.DESKTOP : None, License.GROUPWARE : None,
				},
				'2': {
					# Version 2 since UCS 3.1
					License.USERS: None, License.SERVERS: None,
					License.MANAGEDCLIENTS: None, License.CORPORATECLIENTS: None,
					License.VIRTUALDESKTOPUSERS: None, License.VIRTUALDESKTOPCLIENTS: None,
				},
			}
		self.real = {
				'1': {
					# Version 1 till UCS 3.1
					License.ACCOUNT : 0, License.CLIENT : 0,
					License.DESKTOP : 0, License.GROUPWARE : 0,
				},
				'2': {
					# Version 2 since UCS 3.1
					License.USERS: 0, License.SERVERS: 0,
					License.VIRTUALDESKTOPUSERS: 0, License.VIRTUALDESKTOPCLIENTS: 0,
					License.MANAGEDCLIENTS: 0, License.CORPORATECLIENTS: 0,
				},
			}
		self.names = {
				'1': {
					# Version 1 till UCS 3.1
					License.ACCOUNT : 'Accounts', License.CLIENT : 'Clients',
					License.DESKTOP : 'Desktops', License.GROUPWARE : 'Groupware Accounts',
				},
				'2': {
					# Version 2 since UCS 3.1
					License.USERS: 'Users', License.SERVERS: 'Servers',
					License.MANAGEDCLIENTS: 'Managed Clients', License.CORPORATECLIENTS: 'Corporate Clients',
					License.VIRTUALDESKTOPUSERS: 'DVS Users', License.VIRTUALDESKTOPCLIENTS: 'DVS Clients',
				},
			}
		self.keys = {
				'1': {
					# Version 1 till UCS 3.1
					License.ACCOUNT:   'univentionLicenseAccounts',
					License.CLIENT:    'univentionLicenseClients',
					License.DESKTOP:   'univentionLicenseuniventionDesktops',
					License.GROUPWARE: 'univentionLicenseGroupwareAccounts'
				},
				'2': {
					# Version 1 till UCS 3.1
					License.USERS: 'univentionLicenseUsers',
					License.SERVERS: 'univentionLicenseServers',
					License.MANAGEDCLIENTS: 'univentionLicenseManagedClients',
					License.CORPORATECLIENTS: 'univentionLicenseCorporateClients',
					License.VIRTUALDESKTOPUSERS: 'univentionLicenseVirtualDesktopUsers',
					License.VIRTUALDESKTOPCLIENTS: 'univentionLicenseVirtualDesktopClients',
				},
			}
		self.filters = {
				'1': {
					# Version 1 till UCS 3.1
					License.ACCOUNT : '(&(|(&(objectClass=posixAccount)(objectClass=shadowAccount))(objectClass=sambaSamAccount))(!(uidNumber=0))(!(uid=*$))(!(&(shadowExpire=1)(krb5KDCFlags=254)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags=[ULD       ])))))',
					License.CLIENT : '(|(objectClass=univentionThinClient)(objectClass=univentionClient)(objectClass=univentionMobileClient)(objectClass=univentionWindows)(objectClass=univentionMacOSClient))',
					License.DESKTOP :'(|(objectClass=univentionThinClient)(&(objectClass=univentionClient)(objectClass=posixAccount))(objectClass=univentionMobileClient))',
					License.GROUPWARE : '(&(objectclass=kolabInetOrgPerson)(kolabHomeServer=*)(!(&(shadowExpire=1)(krb5KDCFlags=254)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags=[ULD       ])))))',
				},
				'2': {
					# Version 2 since UCS 3.1
					License.USERS : '(&(|(&(objectClass=posixAccount)(objectClass=shadowAccount))(objectClass=sambaSamAccount))(!(uidNumber=0))(!(uid=*$))(!(&(shadowExpire=1)(krb5KDCFlags=254)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags=[ULD       ])))))',
					License.SERVERS : '(|(objectClass=univentionDomainController)(objectClass=univentionMemberServer))',
					# Thin Clients, Managed Clients, Mobile Clients, Windows Clients, Ubuntu Clients, Linux Clients, UCC Clients, MaxOS X Clients
					License.MANAGEDCLIENTS :'(|(objectClass=univentionThinClient)(&(objectClass=univentionClient)(objectClass=posixAccount))(objectClass=univentionMobileClient)(objectClass=univentionWindows)(objectclass=univentionUbuntuClient)(objectClass=univentionLinuxClient)(objectClass=univentionCorporateClient)(objectClass=univentionMacOSClient))',
					License.CORPORATECLIENTS : '(&(objectclass=univentionCorporateClient))',
					License.VIRTUALDESKTOPUSERS : '(&(objectClass=univentionDVSUsers)(|(&(objectClass=posixAccount)(objectClass=shadowAccount))(objectClass=sambaSamAccount))(!(uidNumber=0))(!(uid=*$))(!(&(shadowExpire=1)(krb5KDCFlags=254)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags=[ULD       ])))))',
					License.VIRTUALDESKTOPCLIENTS : '(&(objectclass=univentionDVSComputers))',
				},
		}
		self.__selected = False

	def select( self, module, lo=None ):
		if not self.__selected:
			self.error = univention.license.select( module )
			if self.error != 0 and lo:
				# Try to set the version even if the license load was not successful
				searchResult = lo.search( filter='(&(objectClass=univentionLicense)(univentionLicenseModule=%s))' % module, attr=['univentionLicenseVersion'])
				if searchResult:
					self.version = searchResult[0][1].get('univentionLicenseVersion', ['1'])[0]
				
			self.__raiseException()
			self.__selected = True

	def isValidFor( self, module ):
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
				'LICENSE: check license for module %s, "%s"' % ( module, str( self.types ) ) )
		if licenses.modules.has_key( module ):
			mlics = licenses.modules[ module ]
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
					'LICENSE: module license: %s' % str( mlics ) )
			# empty list -> valid
			return mlics.valid( self.types )
		# unknown modules are always valid (e.g. customer modules)
		return True

	def modifyOptions( self, mod ):
		if licenses.modules.has_key( mod ):
			opts = licenses.modules[ mod ].options( self.types )
			if opts:
				module = univention.admin.modules.modules[ mod ]
				if module and hasattr( module, 'options' ):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
							'modifyOptions: %s' % str( opts ) )
					for opt, val in opts:
						if callable(val):
							val = val(self)
						if operator.isSequenceType(val):
							module.options[ opt ].disabled, module.options[ opt ].default = val
						else:
							default = val
						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
								'modifyOption: %s, %d, %d' % ( str( opt ), module.options[ opt ].disabled, module.options[ opt ].default ) )

	def checkModules( self ):
		deleted_mods = []
		for mod in univention.admin.modules.modules.keys():
			# remove module if valid license is missing
			if self.isValidFor( mod ):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
						'update: License is valid for module %s!!' % mod )
				# check module options according to given license type
				self.modifyOptions( mod )
			else:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
						'update: License is NOT valid for module %s!!' % mod )
				del univention.admin.modules.modules[ mod ]
				deleted_mods.append( mod )

		# remove child modules that were deleted because of an invalid license
		for name, mod in univention.admin.modules.modules.items():
			if hasattr( mod, 'childmodules' ):
				new = []
				for child in mod.childmodules:
					if child in deleted_mods: continue
					new.append( child )
				mod.childmodules = new

		# remove operations for adding or modifying if license is expired
		if self._expired:
			for name, mod in univention.admin.modules.modules.items():
				if hasattr( mod, 'operations' ):
					try:
						mod.operations.remove( 'add' )
						mod.operations.remove( 'edit' )
					except: pass


	def __cmp_gt( self, val1, val2 ):
		return self.compare(val1, val2) == 1

	def __cmp_eq( self, val1, val2 ):
		return self.compare(val1, val2) == 0

	def compare(self, val1, val2):
		if val1 == 'unlimited' and val2 == 'unlimited':
			return 0
		if val1 == 'unlimited':
			return 1
		if val2 == 'unlimited':
			return -1
		return cmp(int(val1), int(val2))

	def init_select( self, lo, module ):
		self.select( module, lo )
		self.__readLicense()
		disable_add = 0
		self.__countSysAccounts( lo )

		if self.new_license:
			if self.version == '1':
				self.__countObject( License.ACCOUNT, lo )
				self.__countObject( License.CLIENT, lo )
				self.__countObject( License.DESKTOP, lo )
				self.__countObject( License.GROUPWARE, lo )
				lic = ( self.licenses[self.version][License.ACCOUNT],
					self.licenses[self.version][License.CLIENT],
					self.licenses[self.version][License.DESKTOP],
					self.licenses[self.version][License.GROUPWARE] )
				real= ( self.real[self.version][License.ACCOUNT],
					self.real[self.version][License.CLIENT],
					self.real[self.version][License.DESKTOP],
					self.real[self.version][License.GROUPWARE] )
			elif self.version == '2':
				self.__countObject( License.USERS, lo)
				self.__countObject( License.SERVERS, lo)
				self.__countObject( License.MANAGEDCLIENTS, lo)
				self.__countObject( License.CORPORATECLIENTS, lo)
				self.__countObject( License.VIRTUALDESKTOPUSERS, lo)
				self.__countObject( License.VIRTUALDESKTOPCLIENTS, lo)

				lic = ( self.licenses[self.version][License.USERS],
					self.licenses[self.version][License.SERVERS],
					self.licenses[self.version][License.MANAGEDCLIENTS],
					self.licenses[self.version][License.CORPORATECLIENTS],
					self.licenses[self.version][License.VIRTUALDESKTOPUSERS],
					self.licenses[self.version][License.VIRTUALDESKTOPCLIENTS] )
				real= ( self.real[self.version][License.USERS],
					self.real[self.version][License.SERVERS],
					self.real[self.version][License.MANAGEDCLIENTS],
					self.real[self.version][License.CORPORATECLIENTS],
					self.real[self.version][License.VIRTUALDESKTOPUSERS ],
					self.real[self.version][License.VIRTUALDESKTOPCLIENTS] )
				self.licenseKeyID = self.__getValue ( 'univentionLicenseKeyID', '' )
				self.licenseSupport = self.__getValue ( 'univentionLicenseSupport', '0' )
				self.licensePremiumSupport = self.__getValue ( 'univentionLicensePremiumSupport', '0' )
			disable_add = self.checkObjectCounts(lic, real)
			self.licenseBase = univention.license.getValue ( 'univentionLicenseBaseDN' )
			if disable_add:
				self._expired = True
			elif not disable_add and self.licenseBase == 'Free for personal use edition':
				disable_add = 5

		# check modules list for validity and accepted operations
		self.checkModules()

		return disable_add

	def checkObjectCounts(self, lic, real):
		disable_add = 0
		if self.version == '1':
			lic_account, lic_client, lic_desktop, lic_groupware = lic
			real_account, real_client, real_desktop, real_groupware = real
			if lic_client and lic_account:
				if self.__cmp_gt( lic_account, lic_client ) and self.__cmp_gt( real_client, lic_client ):
					disable_add = 1
				elif self.__cmp_gt( lic_client, lic_account ) and self.__cmp_gt( int( real_account ) - max(License.SYSACCOUNTS, self.sysAccountsFound), lic_account ):
					disable_add = 2
				elif self.__cmp_eq(lic_client, lic_account):
					if self.__cmp_gt( real_client, lic_client ):
						disable_add = 1
					elif self.__cmp_gt( int( real_account ) - max(License.SYSACCOUNTS, self.sysAccountsFound), lic_account ):
						disable_add = 2
			else:
				if lic_client and self.__cmp_gt( real_client, lic_client ):
					disable_add = 1
				if lic_account and self.__cmp_gt( int( real_account ) - max(License.SYSACCOUNTS, self.sysAccountsFound) ,lic_account ):
					disable_add = 2
			if lic_desktop:
				if real_desktop and self.__cmp_gt( real_desktop, lic_desktop ):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'LICENSE: 3')
					disable_add = 3
			if lic_groupware:
				if real_groupware and self.__cmp_gt( real_groupware, lic_groupware ):
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'LICENSE: 4')
					disable_add = 4
		elif self.version == '2':
			lic_users, lic_servers, lic_managedclients, lic_corporateclients, lic_virtualdesktopusers, lic_virtualdesktopclients = lic
			real_users, real_servers, real_managedclients, real_corporateclients, real_virtualdesktopusers, real_virtualdesktopclients = real
			if lic_users and self.__cmp_gt( int( real_users ) - self.sysAccountsFound ,lic_users ):
				disable_add = 6
			# The license should be valid even if we have more servers than the license allowed
			#if lic_servers and self.__cmp_gt( real_servers, lic_servers ):
			#	disable_add = 7
			if lic_managedclients and self.__cmp_gt( real_managedclients, lic_managedclients ):
				disable_add = 8
			if lic_corporateclients and self.__cmp_gt( real_corporateclients, lic_corporateclients ):
				disable_add = 9
			if lic_virtualdesktopusers and self.__cmp_gt( real_virtualdesktopusers, lic_virtualdesktopusers ):
				disable_add = 10
			if lic_virtualdesktopclients and self.__cmp_gt( real_virtualdesktopclients, lic_virtualdesktopclients ):
				disable_add = 11
		return disable_add

	def __countSysAccounts( self, lo ):
		userfilter = [ univention.admin.filter.expression('uid', account) for account in self.sysAccountNames ]
                filter=univention.admin.filter.conjunction('&', [
                         univention.admin.filter.conjunction('|', userfilter),
                         self.filters[self.version][License.USERS] ])
		try:
			searchResult = lo.searchDn(filter=str(filter))
			self.sysAccountsFound = len(searchResult)
		except univention.admin.uexceptions.noObject:
			pass
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
				'LICENSE: Univention sysAccountsFound: %d' % self.sysAccountsFound )

	def __countObject( self, obj, lo ):
		if self.licenses[self.version][ obj ] and not self.licenses[self.version][ obj ] == 'unlimited':
			result = lo.searchDn( filter = self.filters[self.version][ obj ] )
			if result == None:
				self.real[self.version][ obj ] = 0
			else:
				self.real[self.version][ obj ] = len( result )
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
					'LICENSE: Univention %s real %d' % ( self.names[self.version][ obj ], self.real[self.version][ obj ] ) )
		else:
			self.real[self.version][ obj ] = 0


	def __raiseException( self ):
		if self.error != 0:
			if self.error == -1:
				raise univention.admin.uexceptions.licenseNotFound
			elif self.error == 2:
				raise univention.admin.uexceptions.licenseExpired
			elif self.error == 4:
				raise univention.admin.uexceptions.licenseWrongBaseDn
			else:
				raise univention.admin.uexceptions.licenseInvalid

	def __getValue( self, key, default, name= '', errormsg = '' ):
		try:
			value = univention.license.getValue( key )
			self.new_license = True
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO,
					'LICENSE: Univention %s allowed %s' % ( name, str( value ) ) )
		except:
			univention.debug.debug( univention.debug.ADMIN, univention.debug.INFO,
					'LICENSE: %s' % errormsg )
			value = default

		univention.debug.debug( univention.debug.ADMIN, univention.debug.INFO, 'LICENSE: %s = %s' % ( name, value ) )
		return value

	def __readLicense( self ):
		self.version = self.__getValue( 'univentionLicenseVersion', '1', 'Version', None)
		if self.version == '1':
			self.licenses[self.version][ License.ACCOUNT ] = self.__getValue( self.keys[self.version][License.ACCOUNT], None,
					'Accounts', 'Univention Accounts not found' )
			self.licenses[self.version][ License.CLIENT ] = self.__getValue( self.keys[self.version][License.CLIENT], None,
					'Clients', 'Univention Clients not found' )
			self.licenses[self.version][ License.DESKTOP ] = self.__getValue( self.keys[self.version][License.DESKTOP], 2,
					'Desktops', 'Univention Desktops not found' )
			self.licenses[self.version][ License.GROUPWARE ] = self.__getValue( self.keys[self.version][License.GROUPWARE], 2,
					'Groupware Accounts', 'Groupware not found' )
			# if no type field is found it must be an old UCS license (<=1.3-0)
			self.types = self.__getValue( 'univentionLicenseType', [ 'UCS' ],
					'License Type', 'Type attribute not found' )
			if not isinstance( self.types, ( list, tuple ) ):
				self.types = [ self.types ]
			self.types = list(self.types)
			# handle license type "OXAE" the same way as license type "UCS"
			if 'OXAE' in self.types and 'UCS' not in self.types:
				self.types.append('UCS')
		elif self.version == '2':
			self.licenses[self.version][ License.USERS ] = self.__getValue( self.keys[self.version][License.USERS], None, 
					'Users', 'Users not found' )
			self.licenses[self.version][ License.SERVERS ] = self.__getValue( self.keys[self.version][License.SERVERS], None, 
					'Servers', 'Servers not found' )
			self.licenses[self.version][ License.MANAGEDCLIENTS ] = self.__getValue( self.keys[self.version][License.MANAGEDCLIENTS], None, 
					'Managed Clients', 'Managed Clients not found' )
			self.licenses[self.version][ License.CORPORATECLIENTS ] = self.__getValue( self.keys[self.version][License.CORPORATECLIENTS], None, 
					'Corporate Clients', 'Corporate Clients not found' )
			self.licenses[self.version][ License.VIRTUALDESKTOPUSERS ] = self.__getValue( self.keys[self.version][License.VIRTUALDESKTOPUSERS], None, 
					'DVS Users', 'DVS Users not found' )
			self.licenses[self.version][ License.VIRTUALDESKTOPCLIENTS ] = self.__getValue( self.keys[self.version][License.VIRTUALDESKTOPCLIENTS], None, 
					'DVS Clients', 'DVS Clients not found' )
			self.types = self.__getValue( 'univentionLicenseProduct', [ 'Univention Corporate Server' ],
					'License Product', 'Product attribute not found' )
			if not isinstance( self.types, ( list, tuple ) ):
				self.types = [ self.types ]
			self.types = list(self.types)

		self.oemProductTypes = self.__getValue( 'univentionLicenseOEMProduct', [ ],
				'License Type', 'univentionLicenseOEMProduct attribute not found' )
		if not isinstance( self.oemProductTypes, ( list, tuple ) ):
			self.oemProductTypes = [ self.oemProductTypes ]
		self.types.extend(self.oemProductTypes)
		self.endDate = self.__getValue( 'univentionLicenseEndDate', None, 'License end date', 'univentionLicenseEndDate attribute not found' )

_license = License()

# for compatibility
select = _license.select
init_select = _license.init_select
is_valid_for = _license.isValidFor
