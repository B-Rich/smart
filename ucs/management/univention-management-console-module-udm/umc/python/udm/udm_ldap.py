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

import copy
import re
import threading
import gc

from univention.management.console import Translation
from univention.management.console.modules import UMC_OptionTypeError, UMC_OptionMissing, UMC_CommandError

import univention.admin as udm
import univention.admin.layout as udm_layout
import univention.admin.modules as udm_modules
import univention.admin.objects as udm_objects
import univention.admin.uldap as udm_uldap
import univention.admin.syntax as udm_syntax
import univention.admin.uexceptions as udm_errors

from ...config import ucr
from ...log import MODULE

from .syntax import widget, default_value

from ldap import LDAPError

try:
    import univention.admin.license
    GPLversion=False
except:
    GPLversion=True


_ = Translation( 'univention-management-console-module-udm' ).translate

udm_modules.update()

# current user
_user_dn = None
_password = None


def get_exception_msg(e):
	msg = getattr(e, 'message', '')
	if getattr(e, 'args', False):
		if e.args[0] != msg or len(e.args) != 1:
			for arg in e.args:
				msg += ' ' + arg
	return msg

def set_credentials( dn, passwd ):
	global _user_dn, _password
	_user_dn = dn
	_password = passwd
	MODULE.info( 'Saved LDAP DN for user %s' % _user_dn )

# decorator for LDAP connections
_ldap_connection = None
_ldap_position = None
_licenseCheck = 0

class LDAP_ConnectionError( Exception ):
	pass

def LDAP_Connection( func ):
	"""This decorator function provides an open LDAP connection that can
	be accessed via the variable ldap_connection and a vaild position
	within the LDAP directory in the viariable ldap_position. It reuses
	an already open connection or creates a new one. If the function
	fails with an LDAP error the decorators tries to reopen the LDAP
	connection and invokes the function again. if it still fails an
	LDAP_ConnectionError is raised.

	When using the decorator the method get to additional keyword arguments.

	example:
	  @LDAP_Connection
	  def do_ldap_stuff(, arg1, arg2, ldap_connection = None, ldap_positio = None ):
		  ...
		  ldap_connection.searchDn( ..., position = ldap_position )
		  ...
	"""
	def wrapper_func( *args, **kwargs ):
		global _ldap_connection, _ldap_position, _user_dn, _password, _licenseCheck

		if _ldap_connection is not None:
			MODULE.info( 'Using open LDAP connection for user %s' % _user_dn )
			lo = _ldap_connection
			po = _ldap_position
		else:
			MODULE.info( 'Opening LDAP connection for user %s' % _user_dn )
			try:
				lo = udm_uldap.access( host = ucr.get( 'ldap/master' ), base = ucr.get( 'ldap/base' ), binddn = _user_dn, bindpw = _password )

				# license check (see also univention.admin.uldap.access.bind())
				if not GPLversion:
					try:
						_licenseCheck = univention.admin.license.init_select(lo, 'admin')
						if _licenseCheck in range(1, 5) or _licenseCheck in range(6,12):
							lo.allow_modify = 0
						if _licenseCheck is not None:
							lo.requireLicense()
					except univention.admin.uexceptions.licenseInvalid:
						lo.allow_modify = 0
						lo.requireLicense()
					except univention.admin.uexceptions.licenseNotFound:
						lo.allow_modify = 0
						lo.requireLicense()
					except univention.admin.uexceptions.licenseExpired:
						lo.allow_modify = 0
						lo.requireLicense()
					except univention.admin.uexceptions.licenseWrongBaseDn:
						lo.allow_modify = 0
						lo.requireLicense()

				po = udm_uldap.position( lo.base )
			except udm_errors.noObject, e:
				raise e
			except LDAPError, e:
				raise LDAP_ConnectionError( 'Opening LDAP connection failed: %s' % str( e ) )

		kwargs[ 'ldap_connection' ] = lo
		kwargs[ 'ldap_position' ] = po
		try:
			ret = func( *args, **kwargs )
			_ldap_connection = lo
			_ldap_position = po
			return ret
		except (udm_errors.ldapSizelimitExceeded, udm_errors.ldapTimeout), e:
			raise e
		except ( LDAPError, udm_errors.base ), e:
			MODULE.info( 'LDAP operation for user %s has failed' % _user_dn )
			try:
				lo = udm_uldap.access( host = ucr.get( 'ldap/master' ), base = ucr.get( 'ldap/base' ), binddn= _user_dn, bindpw = _password )
				lo.requireLicense()
				po = udm_uldap.position( lo.base )
			except udm_errors.noObject, e:
				raise e
			except ( LDAPError, udm_errors.base ), e:
				raise LDAP_ConnectionError( 'Opening LDAP connection failed: %s' % str( e ) )

			kwargs[ 'ldap_connection' ] = lo
			kwargs[ 'ldap_position' ] = po
			try:
				ret = func( *args, **kwargs )
				_ldap_connection = lo
				_ldap_position = po
				return ret
			except (udm_errors.ldapSizelimitExceeded, udm_errors.ldapTimeout), e:
				raise e
			except udm_errors.base, e:
				raise LDAP_ConnectionError( str( e ) )

		return []

	return wrapper_func

# exceptions
class UDM_Error( Exception ):
	pass

# module cache
class UDM_ModuleCache( dict ):
	lock = threading.Lock()

	@LDAP_Connection
	def get( self, name, template_object = None, force_reload = False, ldap_connection = None, ldap_position = None ):
		UDM_ModuleCache.lock.acquire()
		try:
			if name in self and not force_reload:
				return self[ name ]

			self[ name ] = udm_modules.get( name )
			if self[ name ] is None:
				return None

			udm_modules.init( ldap_connection, ldap_position, self[ name ], template_object, force_reload=force_reload )

			return self[ name ]
		finally:
			UDM_ModuleCache.lock.release()

_module_cache = UDM_ModuleCache()

class UDM_Module( object ):
	"""Wraps UDM modules to provie a simple access to the properties and functions"""

	def __init__( self, module, force_reload = False ):
		"""Initializes the object"""
		self._initialized_with_module = module
		self.load( force_reload=force_reload )
		self.settings = UDM_Settings()

	def load( self, module = None, template_object = None, force_reload = False ):
		"""Tries to load an UDM module with the given name. Optional a
		template object is passed to the init function of the module. As
		the initialisation of a module is expensive the function uses a
		cache to ensure that each module is just initialized once."""
		global _module_cache

		if module is None:
			module = self._initialized_with_module
		self.module = _module_cache.get( module, force_reload=force_reload )

	def __getitem__( self, key ):
		props = getattr( self.module, 'property_descriptions', {} )
		return props[ key ]

	def get_default_values( self, property_name ):
		"""Depending on the syntax of the given property a default
		search pattern/value is returned"""
		MODULE.info( 'Searching for property %s' % property_name )
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if key == property_name:
				value = default_value( prop.syntax )
				if isinstance( value, ( list, tuple ) ):
					value = read_syntax_choices( prop.syntax.name )
				return value

	def _map_properties( self, obj, properties ):
		# FIXME: for the automatic IP address assignment, we need to make sure that
		#        the network is set before the IP address (see Bug #24077, comment 6)
		#        The following code is a workaround to make sure that this is the
		#        case, however, this should be fixed correctly.
		#        This workaround has been documented as Bug #25163.
		def _tmp_cmp(i, j):
			if i[0] == 'network': 
				return -1
			return 0

		for property_name, value in sorted(properties.items(), _tmp_cmp):
			MODULE.info( 'Setting property %s to %s' % ( property_name, value ) )

			property_obj = self.get_property( property_name )
			if property_obj is None:
				raise UMC_OptionMissing( _( 'Property %s not found' ) % property_name )

			# check each element if 'value' is a list
			if isinstance(value, (tuple, list)) and property_obj.multivalue:
				if not value and not property_obj.required:
					MODULE.info( 'Setting of property ignored (is empty)' )
					if property_name in obj.info:
						del obj.info[ property_name ]
					continue
				subResults = []
				for ival in value:
					try:
						subResults.append( property_obj.syntax.parse( ival ) )
					except TypeError as e:
						raise UMC_OptionTypeError( _( 'The property %s has an invalid value: %s' ) % ( property_obj.short_description, str( e ) ) )
				if subResults: # empty list represents removing of the attribute (handlers/__init__.py def diff)
					MODULE.info( 'Setting of property ignored (is empty)' )
					obj[ property_name ] = subResults
			# otherwise we have a single value
			else:
				# None and empty string represents removing of the attribute (handlers/__init__.py def diff)
				if ( value is None or value == '' ) and not property_obj.required:
					if property_name in obj.info:
						del obj.info[ property_name ]
					continue
				try:
					obj[ property_name ] = property_obj.syntax.parse( value )
				except TypeError as e:
					raise UMC_OptionTypeError( _( 'The property %s has an invalid value: %s' ) % ( property_obj.short_description, str( e ) ) )

		return obj

	@LDAP_Connection
	def create( self, ldap_object, container = None, superordinate = None, ldap_connection = None, ldap_position = None ):
		"""Creates a LDAP object"""
		if superordinate not in ( None, 'None' ):
			try:
				ldap_position.setDn( superordinate )
			except udm_errors.noObject, e:
				raise UMC_CommandError( str( e ) )
		elif container is not None:
			try:
				ldap_position.setDn( container )
			except udm_errors.noObject, e:
				raise UMC_CommandError( str( e ) )
		else:
			if hasattr( self.module, 'policy_position_dn_prefix' ):
				container = '%s,cn=policies,%s' % ( self.module.policy_position_dn_prefix, ldap_position.getBase() )
			elif hasattr( self.module, 'default_containers' ) and self.module.default_containers:
				container = '%s,%s' % ( self.module.default_containers[ 0 ], ldap_position.getBase() )
			else:
				container = ldap_position.getBase()

			ldap_position.setDn( container )

		if superordinate not in ( None, 'None' ):
			mod = get_module( self.name, superordinate )
			if mod is not None:
				MODULE.info( 'Found UDM module for superordinate' )
				superordinate = mod.get( superordinate )
			else:
				raise UMC_OptionTypeError( _( 'Could not find an UDM module for the superordinate object %s' ) % superordinate )
		else:
			superordinate = udm_objects.get_superordinate( self.module, None, ldap_connection, container )

		obj = self.module.object( None, ldap_connection, ldap_position, superordinate = superordinate )
		try:
			obj.open()
			MODULE.info( 'Creating LDAP object' )
			if '$options$' in ldap_object:
				obj.options = filter( lambda option: ldap_object[ '$options$' ][ option ] == True, ldap_object[ '$options$' ].keys() )
				del ldap_object[ '$options$' ]
			if '$policies$' in ldap_object:
				obj.policies = ldap_object[ '$policies$' ].values()
				del ldap_object[ '$policies$' ]

			self._map_properties( obj, ldap_object )

			obj.create()
		except udm_errors.base, e:
			MODULE.warn( 'Failed to create LDAP object: %s: %s' % ( e.__class__.__name__, str( e ) ) )
			raise UDM_Error( get_exception_msg(e), obj.dn )

		return obj.dn

	@LDAP_Connection
	def move( self, ldap_dn, container, ldap_connection = None, ldap_position = None ):
		"""Moves an LDAP object"""
		superordinate = udm_objects.get_superordinate( self.module, None, ldap_connection, ldap_dn )
		obj = self.module.object( None, ldap_connection, ldap_position, dn = ldap_dn, superordinate = superordinate )
		try:
			obj.open()
			# build new dn
			rdn = udm.uldap.explodeDn( ldap_dn )[ 0 ]
			dest = '%s,%s' % ( rdn, container )
			MODULE.info( 'Moving LDAP object %s to %s' % ( ldap_dn, dest ) )
			obj.move( dest )
			return dest
		except udm_errors.base, e:
			MODULE.warn( 'Failed to move LDAP object %s: %s: %s' % ( ldap_dn, e.__class__.__name__, str( e ) ) )
			raise UDM_Error( get_exception_msg( e ) )

	@LDAP_Connection
	def remove( self, ldap_dn, cleanup = False, recursive = False, ldap_connection = None, ldap_position = None ):
		"""Removes an LDAP object"""
		superordinate = udm_objects.get_superordinate( self.module, None, ldap_connection, ldap_dn )
		obj = self.module.object( None, ldap_connection, ldap_position, dn = ldap_dn, superordinate = superordinate )
		try:
			obj.open()
			MODULE.info( 'Removing LDAP object %s' % ldap_dn )
			obj.remove( remove_childs = recursive )
			if cleanup:
				udm_objects.performCleanup( obj )
		except udm_errors.base, e:
			MODULE.warn( 'Failed to remove LDAP object %s: %s: %s' % ( ldap_dn, e.__class__.__name__, str( e ) ) )
			raise UDM_Error( get_exception_msg( e ) )

	@LDAP_Connection
	def modify( self, ldap_object, ldap_connection = None, ldap_position = None ):
		"""Modifies a LDAP object"""
		superordinate = udm_objects.get_superordinate( self.module, None, ldap_connection, ldap_object[ '$dn$' ] )
		MODULE.info( 'Modifying object %s with superordinate %s' % ( ldap_object[ '$dn$' ], superordinate ) )
		obj = self.module.object( None, ldap_connection, ldap_position, dn = ldap_object.get( '$dn$' ), superordinate = superordinate )
		del ldap_object[ '$dn$' ]

		try:
			obj.open()
			if '$options$' in ldap_object:
				obj.options = filter( lambda option: ldap_object[ '$options$' ][ option ] == True, ldap_object[ '$options$' ].keys() )
				MODULE.info( 'Setting new options to %s' % str( obj.options ) )
				del ldap_object[ '$options$' ]
			MODULE.info( 'Modifying LDAP object %s' % obj.dn )
			if '$policies$' in ldap_object:
				obj.policies = ldap_object[ '$policies$' ].values()
				del ldap_object[ '$policies$' ]

			self._map_properties( obj, ldap_object )

			obj.modify()
		except udm_errors.base, e:
			MODULE.warn( 'Failed to modify LDAP object %s: %s: %s' % ( obj.dn, e.__class__.__name__, str( e ) ) )
			raise UDM_Error( get_exception_msg(e) )

	@LDAP_Connection
	def search( self, container = None, attribute = None, value = None, superordinate = None, scope = 'sub', filter = '', ldap_connection = None, ldap_position = None ):
		"""Searches for LDAP objects based on a search pattern"""
		if container == 'all':
			container = ldap_position.getBase()
		elif container is None:
			container = ''
		filter_s = _object_property_filter( self, attribute, value )
		if attribute in [None, 'None'] and filter:
			filter_s = str( filter )

		MODULE.info( 'Searching for LDAP objects: container = %s, filter = %s, superordinate = %s' % ( container, filter_s, superordinate ) )
		result = None
		try:
			sizelimit = int(ucr.get('directory/manager/web/sizelimit', '2000'))
			result = self.module.lookup( None, ldap_connection, filter_s, base = container, superordinate = superordinate, scope = scope, sizelimit = sizelimit )
		except udm_errors.insufficientInformation, e:
			return []
		except udm_errors.ldapTimeout, e:
			raise udm_errors.ldapTimeout( _('The query you have entered timed out. Please narrow down your search by specifiying more query parameters') )
		except udm_errors.ldapSizelimitExceeded, e:
			raise udm_errors.ldapSizelimitExceeded( _('The query you have entered yields too many matching entries. Please narrow down your search by specifiying more query parameters. The current size limit of %s can be configured with the UCR variable directory/manager/web/sizelimit.') % ucr.get('directory/manager/web/sizelimit', '2000') )
		except ( LDAPError, udm_errors.ldapError ), e:
			raise e
		except udm_errors.base, e:
			raise UDM_Error( get_exception_msg( e ) )

		# call the garbage collector manually as many parallel request may cause the
		# process to use too much memory
		MODULE.info('Triggering garbage collection')
		gc.collect()

		return result

	@LDAP_Connection
	def get( self, ldap_dn = None, superordinate = None, attributes = [], ldap_connection = None, ldap_position = None ):
		"""Retrieves details for a given LDAP object"""
		try:
			if ldap_dn is not None:
				if superordinate is None:
					superordinate = udm_objects.get_superordinate( self.module, None, ldap_connection, ldap_dn )
				obj = self.module.object( None, ldap_connection, None, ldap_dn, superordinate, attributes = attributes )
				MODULE.info( 'Found LDAP object %s' % obj.dn )
				obj.open()
			else:
				obj = self.module.object( None, ldap_connection, None, '', superordinate, attributes = attributes )
		except ( LDAPError, udm_errors.ldapError ), e:
			raise e
		except Exception, e:
			MODULE.info( 'Failed to retrieve LDAP object: %s' % str( e ) )
			raise UDM_Error( get_exception_msg( e ) )
		return obj

	def get_property( self, property_name ):
		"""Returns details for a given property"""
		return getattr( self.module, 'property_descriptions', {} ).get( property_name, None )

	@property
	def name( self ):
		"""Internal name of the UDM module"""
		return self.module is not None and self.module.module

	@property
	def subtitle( self ):
		"""Returns the descriptive name of the UDM module without the part for the module group"""
		descr = getattr( self.module, 'short_description', self.module.module )
		colon = descr.find( ':' )
		if colon > 0:
			return descr[ colon + 1 : ].strip()
		return descr

	@property
	def title( self ):
		"""Descriptive name of the UDM module"""
		return getattr( self.module, 'short_description', self.module.module )

	@property
	def description( self ):
		"""Descriptive text of the UDM module"""
		return getattr( self.module, 'long_description', '' )

	@property
	def identifies( self ):
		"""Property of the UDM module that identifies objects of this type"""
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if prop.identifies:
				MODULE.info( 'The property %s identifies to module objects %s' % ( key, self.name ) )
				return key
		return None

	@property
	def childs( self ):
		return bool( getattr( self.module, 'childs', False ) )

	@property
	def child_modules( self ):
		"""List of child modules"""
		if self.module is None:
			return None
		MODULE.info( 'Collecting child modules ...' )
		children = getattr( self.module, 'childmodules', None )
		if children is None:
			MODULE.info( 'No child modules were found' )
			return []
		modules = []
		for child in children:
			mod = udm_modules.get( child )
			if not mod:
				continue
			MODULE.info( 'Found module %s' % str( mod ) )
			modules.append( { 'id' : child, 'label' : getattr( mod, 'short_description', child ) } )
		return modules

	@property
	def default_search_attrs( self ):
		ret = []
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if prop.include_in_default_search:
				ret.append( key )
		return ret

	def is_policy_module( self ):
		return self.name.startswith('policies/') and self.name != 'policies/policy'

	def get_layout( self, ldap_dn = None ):
		"""Layout information"""
		layout = getattr( self.module, 'layout', [] )
		if ldap_dn is not None:
			mod = get_module( None, ldap_dn )
			if self.name == mod.name and self.is_policy_module():
				layout = copy.copy( layout )
				tab = udm_layout.Tab( _( 'Referencing objects' ), _( 'Objects referencing this policy object' ),
					layout = [ '_view_referencing_objects' ]
				)
				layout.append(tab)

		if layout and isinstance( layout[ 0 ], udm.tab ):
			return self._parse_old_layout( layout )

		return layout

	def _parse_old_layout( self, layout ):
		"""Parses old layout information"""
		tabs = []
		for tab in layout:
			data = { 'name' : tab.short_description, 'description' : tab.long_description, 'advanced' : tab.advanced, 'layout' : [ { 'name' : 'General', 'description' : 'General settings', 'layout' : [] } ] }
			for item in tab.fields:
				line = []
				for field in item:
					if isinstance( field, ( list, tuple ) ):
						elem = [ x.property for x in field ]
					else:
						elem = field.property
					line.append( elem )
				data[ 'layout' ][ 0 ][ 'layout' ].append( line )
			tabs.append( data )
		return tabs

	@property
	def password_properties( self ):
		"""All properties with the syntax class passwd or userPasswd"""
		passwords = []
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if prop.syntax in ( udm_syntax.passwd, udm_syntax.userPasswd ):
				passwords.append( key )

		return passwords

	def get_properties( self, ldap_dn=None ):
		properties = self.properties
		if ldap_dn:
			# hack reference list for policies into items
			if self.is_policy_module():
				# create syntax object
				syntax = udm_syntax.LDAP_Search(
					filter = '(&(objectClass=univentionPolicyReference)(univentionPolicyReference=%s))' % ldap_dn,
					viewonly = True )

				# create item
				item = {
					'id' : '_view_referencing_objects',
					'label' : '',
					'description' : '',
					'syntax' : syntax.name,
					'size' : syntax.size,
					'required' : False,
					'editable' : False,
					'options' : [],
					'readonly' : False,
					'searchable' : False,
					'multivalue' : True,
					'identifies' : False,
					}

				# read UCR configuration
				item.update( widget( syntax, item ) )
				properties.append(item)

		return properties

	@property
	@LDAP_Connection
	def properties( self, ldap_connection=None, ldap_position=None ):
		"""All properties of the UDM module"""
		props = [ { 'id' : '$dn$', 'type' : 'HiddenInput', 'label' : '', 'searchable' : False } ]
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if key == 'filler': continue # FIXME: should be removed from all UDM modules
			item = { 'id' : key, 'label' : prop.short_description, 'description' : prop.long_description, 'syntax' : prop.syntax.name, 'size' : prop.syntax.size,
					 'required' : bool( prop.required ), 'editable' : bool( prop.may_change ), 'options' : prop.options, 'readonly' : not bool( prop.editable ),
					 'searchable' : not prop.dontsearch, 'multivalue' : bool( prop.multivalue ), 'identifies' : bool( prop.identifies ),
					 'threshold' : prop.threshold }

			# default value
			if prop.base_default is not None:
				if isinstance( prop.base_default, ( list, tuple ) ):
					if prop.multivalue and prop.base_default and isinstance( prop.base_default[ 0 ], ( list, tuple ) ):
						item[ 'default' ] = prop.base_default
					else:
						item[ 'default' ] = prop.base_default[ 0 ]
				else:
					item[ 'default' ] = str( prop.base_default )
			elif key == 'primaryGroup': # set default for primaryGroup
					obj = self.module.object(None, ldap_connection, ldap_position, None)
					obj.open()
					default_group = obj.get('primaryGroup', None)
					if default_group is not None:
						item[ 'default' ] = default_group

			# read UCR configuration
			item.update( widget( prop.syntax, item ) )
			props.append( item )
		props.append( {	'id' : '$options$', 'type' : 'WidgetGroup', 'widgets' : self.get_options() } )

		return props

	def get_options( self, object_dn = None, udm_object = None ):
		"""Returns the options of the module. If an LDAP DN or an UDM
		object instance is given the values of the options are set"""
		if object_dn is None and udm_object is None:
			obj_options = None
		else:
			if udm_object is None:
				obj = self.get( object_dn )
			else:
				obj = udm_object
			obj_options = getattr( obj, 'options', {} )

		options = []
		for name, opt in self.options.items():
			if obj_options is None:
				value = bool( opt.default )
			else:
				value = name in obj_options
			options.append( {
				'id'	: name,
				'type'  : 'CheckBox',
				'label'	: opt.short_description,
				'value'	: value,
				'editable' : bool( opt.editable )
				} )

		return options

	@property
	def options( self ):
		"""List of defined options"""
		return getattr( self.module, 'options', {} )

	@property
	def operations( self ):
		"""Allowed operations of the UDM module"""
		return getattr( self.module, 'operations', [] )

	@property
	def template( self ):
		"""List of UDM module names of templates"""
		return getattr( self.module, 'template', None )

	@property
	def containers( self ):
		"""List of LDAP DNs of default containers"""
		containers = getattr( self.module, 'default_containers', [] )
		ldap_base = ucr.get( 'ldap/base' )

		return map( lambda x: { 'id' : '%s,%s' % ( x, ldap_base ), 'label' : ldap_dn2path( '%s,%s' % ( x, ldap_base ) ) }, containers )

	@property
	def superordinate( self ):
		return udm_modules.superordinate_name( self.module )

	@property
	def superordinates( self ):
		"""List of superordinates"""
		modules = getattr( self.module, 'wizardsuperordinates', [] )
		superordinates = []
		for mod in modules:
			if mod == 'None':
				superordinates.append( { 'id' : mod, 'label' : _( 'None' ) } )
			else:
				module = UDM_Module( mod )
				if module:
					so = module.superordinate
					if so == '':
						so = None
					objects = module.search( superordinate = so )
					for obj in objects:
						superordinates.append( { 'id' : obj.dn, 'label' : '%s: %s' % ( module.title, obj[ module.identifies ] ) } )

		return superordinates

	@property
	def policies( self ):
		"""Searches in all policy objects for the given object type and
		returns a list of all matching policy types"""

		policyTypes = udm_modules.policyTypes( self.name )
		if not policyTypes and self.childs:
			# allow all policies for containers
			policyTypes = filter( lambda x: x.startswith( 'policies/' ) and x != 'policies/policy', udm_modules.modules )


		policies = []
		for policy in policyTypes:
			module = UDM_Module( policy )
			policies.append( { 'objectType' : policy, 'label' : module.title, 'description' : module.description } )

		return policies

	def types4superordinate( self, flavor, superordinate ):
		"""List of object types for the given superordinate"""
		types = getattr( self.module, 'wizardtypesforsuper' )
		typelist = []

		if superordinate == 'None':
			module_name = superordinate
		else:
			module = get_module( flavor, superordinate )
			if not module:
				return typelist
			module_name = module.name

		if isinstance( types, dict ) and module_name in types:
			for mod in types[ module_name ]:
				module = UDM_Module( mod )
				if module:
					typelist.append( { 'id' : mod, 'label' : module.title } )

		return typelist

	@property
	def flavor( self ):
		"""Tries to guess the flavor for a given module"""
		if self.name.startswith( 'container/' ):
			return 'navigation'
		base, name = split_module_name( self.name )
		for module in filter( lambda x: x.startswith( base ), udm_modules.modules.keys() ):
			mod = UDM_Module( module )
			children = getattr( mod.module, 'childmodules', [] )
			if self.name in children:
				return mod.name
		return None

class UDM_Settings( object ):
	"""Provides access to different kinds of settings regarding UDM"""
	Singleton = None

	@staticmethod
	def __new__ ( cls ):
		if UDM_Settings.Singleton is None:
			UDM_Settings.Singleton = super( UDM_Settings, cls ).__new__( cls )

		return UDM_Settings.Singleton

	def __init__( self ):
		"""Reads the policies for the current user"""
		if hasattr( self, 'initialized' ):
			return
		self.initialized = True
		self.user_dn = None
		self.policies = None
		self.read()

	def read( self ):
		self._read_directories()
		self._read_groups()

	@LDAP_Connection
	def _read_directories( self, ldap_connection = None, ldap_position = None ):
		try:
			directories = udm_modules.lookup( 'settings/directory', None, ldap_connection, scope = 'sub' )
		except ( LDAPError, udm_errors.ldapError ), e:
			raise e
		except udm_errors.noObject:
			directories = None
		if not directories:
			self.directory = None
		else:
			self.directory = directories[ 0 ]

	@LDAP_Connection
	def _read_groups( self, ldap_connection = None, ldap_position = None ):
		try:
			groups = udm_modules.lookup( 'settings/default', None, ldap_connection, scope = 'sub' )
		except ( LDAPError, udm_errors.ldapError ), e:
			raise e
		except udm_errors.noObject:
			groups = None
		if not groups:
			self.groups = None
		else:
			self.groups = groups[ 0 ]

	@LDAP_Connection
	def user( self, user_dn, ldap_connection = None, ldap_position = None ):
		self.user_dn = user_dn
		self.policies = ldap_connection.getPolicies( self.user_dn )

	def containers( self, module_name ):
		"""Returns list of default containers for a given UDM module"""
		base, name = split_module_name( module_name )

		# the printer modules does not have the same name scheme
		if module_name == 'shares/print':
			base = 'printers'

		self._read_directories()

		return map( lambda x: { 'id' : x, 'label' : ldap_dn2path( x ) }, self.directory.info.get( base, [] ) )

	def resultColumns( self, module_name ):
		pass

def check_license(ldap_connection = None, ldap_position = None ):
	"""Checks the license cases and throws exceptions accordingly"""
	global GPLversion
	if GPLversion:
		raise udm_errors.licenseGPLversion
	ldap_connection._validateLicense()  # throws more exceptions in case the license could not be found
	MODULE.info('_validateLicense result=%s' % _licenseCheck)
	if _licenseCheck == 1:
		raise udm_errors.licenseClients
	elif _licenseCheck == 2:
		raise udm_errors.licenseAccounts
	elif _licenseCheck == 3:
		raise udm_errors.licenseDesktops
	elif _licenseCheck == 4:
		raise udm_errors.licenseGroupware
	#elif _licenseCheck == 5:
	#	# Free for personal use edition
	#	raise udm_errors.freeForPersonalUse
	elif _licenseCheck == 6:
		raise udm_errors.licenseUsers
	elif _licenseCheck == 7:
		raise udm_errors.licenseServers
	elif _licenseCheck == 8:
		raise udm_errors.licenseManagedClients
	elif _licenseCheck == 9:
		raise udm_errors.licenseCorporateClients
	elif _licenseCheck == 10:
		raise udm_errors.licenseDVSUsers
	elif _licenseCheck == 11:
		raise udm_errors.licenseDVSClients


def container_modules():
	containers = []
	for name, mod in udm_modules.modules.items():
		if getattr( mod, 'childs', None ):
			containers.append( name )

	return containers

def split_module_name( module_name ):
	"""Splits a module name into category and internal name"""

	if '/' in module_name:
		parts = module_name.split( '/', 1 )
		if len( parts ) == 2:
			return parts

	return ( None, None )

def ldap_dn2path( ldap_dn, include_rdn = True ):
	"""Returns a path representation of an LDAP DN. If include_rdn is
	false just the container of the given object is returned in a path
	representation"""

	ldap_base = ucr.get( 'ldap/base' )
	if ldap_base is None or not ldap_dn.endswith( ldap_base ):
		return ldap_dn
	rel_path = ldap_dn[ : -1 * len( ldap_base ) ]
	path = []
	for item in ldap_base.split( ',' ):
		if not item: continue
		dummy, value = item.split( '=', 1 )
		path.insert( 0, value )
	path = [ '.'.join( path ) + ':', ]
	if rel_path:
		if not include_rdn:
			lst = rel_path.split( ',' )[ 1 : -1 ]
		else:
			lst = rel_path.split( ',' )[ : -1 ]
		for item in lst:
			if not item: continue
			dummy, value = item.split( '=', 1 )
			path.insert( 1, value )
		if not lst:
			path.insert( 1, '' )
	else:
		path.append('')
	return '/'.join( path )

@LDAP_Connection
def get_module( flavor, ldap_dn, ldap_connection = None, ldap_position = None ):
	"""Determines an UDM module handling the LDAP object identified by the given LDAP DN"""
	if flavor is None or flavor == 'navigation':
		base = None
	else:
		base, name = split_module_name( flavor )
	modules = udm_modules.objectType( None, ldap_connection, ldap_dn, module_base = base )

	if not modules:
		return None

	return UDM_Module( modules[ 0 ] )

@LDAP_Connection
def list_objects( container, object_type = None, ldap_connection = None, ldap_position = None ):
	"""Returns a list of UDM objects"""
	try:
		result = ldap_connection.search( base = container, scope = 'one' )
	except ( LDAPError, udm_errors.ldapError ), e:
		raise e
	except udm_errors.base, e:
		raise UDM_Error( get_exception_msg( e ) )
	objects = []
	for dn, attrs in result:
		modules = udm_modules.objectType( None, ldap_connection, dn, attrs )
		if not modules:
			MODULE.warn( 'Could not identify LDAP object %s' % dn )
			continue
		if object_type == '$containers$' and not udm_modules.childs( modules[ 0 ] ):
			continue
		module = UDM_Module( modules[ 0 ] )

		if not module.module:
			MODULE.process( 'The UDM module %s could not be found. Ignoring LDAP object %s' % ( modules[ 0 ], dn ) )
			continue
		if module.superordinate:
			so_module = UDM_Module( module.superordinate )
			so_obj = so_module.get( container )
			try:
				objects.append( ( module, module.get( dn, so_obj, attributes = attrs ) ) )
			except:
				objects.append( ( module, module.get( dn, so_obj ) ) )
		else:
			try:
				objects.append( ( module, module.get( dn, attributes = attrs ) ) )
			except:
				objects.append( ( module, module.get( dn ) ) )

	return objects

def split_module_attr( value ):
	if value.find( ':' ) > 0:
		return value.split( ': ', 1 )
	return ( None, value )

def _object_property_filter( module, object_property, object_property_value ):
	if object_property in [None, 'None'] and module is not None:
		default_search_attrs = module.default_search_attrs
		if default_search_attrs and object_property_value not in [None, '*']:
			return '(|%s)' % ''.join( '(%s=%s)' % ( attr, object_property_value ) for attr in default_search_attrs )
		else:
			return ''
	else:
		return '%s=%s' % (object_property, object_property_value)

def _create_ldap_filter( syn, options, module=None ):
	if syn.depends and not syn.depends in options:
		return None
	if callable( syn.udm_filter ):
		filter_s = syn.udm_filter( options )
	else:
		filter_s = syn.udm_filter % options
	if options.get('objectProperty') and options.get('objectPropertyValue'):
		if filter_s and not filter_s.startswith('('):
			# make sure that the LDAP filter is wrapped in brackets
			filter_s = '(%s)' % filter_s
		object_property = options.get('objectProperty')
		object_property_value = options.get('objectPropertyValue')
		property_filter_s = _object_property_filter(module, object_property, object_property_value)
		if property_filter_s and not property_filter_s.startswith('('):
			# make sure that the LDAP filter is wrapped in brackets
			property_filter_s = '(%s)' % property_filter_s
		filter_s = '(&%s%s)' % (property_filter_s, filter_s)
	return filter_s

LDAP_ATTR_RE = re.compile(r'^%\(([^(]*)\)s$') # '%(username)s' -> 'username'
def _get_syntax( syntax_name ):
	if syntax_name not in udm_syntax.__dict__:
		return None
	return udm_syntax.__dict__[ syntax_name ]()

def search_syntax_choices_by_key( syntax_name, key ):
	syn = _get_syntax( syntax_name )
	if syn is None:
		return None

	if issubclass( syn.__class__, udm_syntax.UDM_Objects ):
		if syn.key == 'dn':
			module_search_options = {'scope' : 'base', 'container' : key}
			try:
				return read_syntax_choices( syntax_name, {}, module_search_options )
			except LDAP_ConnectionError:
				# invalid DN
				return []
		if syn.key is not None:
			match = LDAP_ATTR_RE.match(syn.key)
			if match:
				attr = match.groups()[0]
				options = {'objectProperty' : attr, 'objectPropertyValue' : key}
				return read_syntax_choices( syntax_name, options )

	MODULE.warn('Syntax "%s": No fast search function' % syntax_name)
	# return them all, as there is no reason to filter after everything has loaded
	# frontend will cache it.
	return read_syntax_choices( syntax_name )

def info_syntax_choices( syntax_name, options = {} ):
	syn = _get_syntax( syntax_name )
	if syn is None:
		return None

	if issubclass( syn.__class__, udm_syntax.UDM_Objects ):
		size = 0
		if syn.static_values is not None:
			size += len(syn.static_values)
		for udm_module in syn.udm_modules:
			module = UDM_Module( udm_module )
			if module is None:
				continue
			filter_s = _create_ldap_filter( syn, options, module )
			if filter_s is not None:
				try:
					size += len( module.search( filter = filter_s ) )
				except udm_errors.ldapSizelimitExceeded:
					return {'performs_well' : True, 'size_limit_exceeded' : True}
		return {'size' : size, 'performs_well' : True }
	return {'size' : 0, 'performs_well' : False}

@LDAP_Connection
def read_syntax_choices( syntax_name, options = {}, module_search_options = {}, ldap_connection = None, ldap_position = None ):
	syn = _get_syntax(syntax_name)
	if syn is None:
		return None

	if issubclass( syn.__class__, udm_syntax.UDM_Objects ):
		syn.choices = []
		def map_choices( obj_list ):
			result = []
			for obj in obj_list:
				obj.open()

				if syn.key == 'dn':
					key = obj.dn
				else:
					try:
						key = syn.key % obj.info
					except KeyError:
						# ignore the entry as the key is important for a selection, there
						# is no sensible fallback for the key (Bug #26994)
						continue
				if syn.label is None:
					label = udm_objects.description( obj )
				elif syn.label == 'dn':
					label = obj.dn
				else:
					try:
						label = syn.label % obj.info
					except KeyError:
						# fallback to the default description as this is just what displayed
						# to the user (Bug #26994)
						label = udm_objects.description( obj )

				result.append( (key, label) )
			return result

		for udm_module in syn.udm_modules:
			module = UDM_Module( udm_module )
			if module is None:
				continue
			filter_s = _create_ldap_filter( syn, options, module )
			if filter_s is None:
				syn.choices = []
			else:
				search_options = {'filter' : filter_s}
				search_options.update(module_search_options)
				syn.choices.extend( map_choices( module.search( **search_options ) ) )
		if isinstance( syn.static_values, ( tuple, list ) ):
			for value in syn.static_values:
				syn.choices.insert( 0, value )
		if syn.empty_value:
			syn.choices.insert( 0, ( '', '' ) )
	elif issubclass( syn.__class__, udm_syntax.UDM_Attribute ):
		syn.choices = []
		def filter_choice( obj ):
			# if attributes does not exist or is empty
			return syn.attribute in obj.info and obj.info[ syn.attribute ]

		def map_choice( obj ):
			obj.open()
			MODULE.info( 'Loading choices from %s: %s' % ( obj.dn, obj.info ) )
			if syn.is_complex:
				try:
					return map( lambda x: ( x[ syn.key_index ], x[ syn.label_index ] ), obj.info[ syn.attribute ] )
				except KeyError:
					# probably syn.attribute not in obj.info
					# this happens for example in PrinterDriverList
					# if the ldap schema is not installed
					# and thus no 'printmodel' attribute is known.
					return []
			if syn.label_format is not None:
				choices = []
				for value in obj.info[ syn.attribute ]:
					obj.info[ '$attribute$' ] = value
					choices.append( ( value, syn.label_format % obj.info ) )
				return choices
			try:
				return map( lambda x: ( x, x ), obj.info[ syn.attribute ] )
			except KeyError:
				return []

		module = UDM_Module( syn.udm_module )
		if module is None:
			return
		MODULE.info( 'Found syntax %s with udm_module property' % syntax_name )
		if syn.udm_filter == 'dn':
			syn.choices = map_choice( module.get( options[ syn.depends ] ) )
		else:
			filter_s = _create_ldap_filter( syn, options )
			if filter_s is None:
				syn.choices = []
			else:
				for element in map( map_choice, filter( filter_choice, module.search( filter = filter_s ) ) ):
					for item in element:
						syn.choices.append( item )
		if isinstance( syn.static_values, ( tuple, list ) ):
			for value in syn.static_values:
				syn.choices.insert( 0, value )
		if syn.empty_value:
			syn.choices.insert( 0, ( '', '' ) )
	elif issubclass( syn.__class__, udm_syntax.ldapDn ) and hasattr( syn, 'searchFilter' ):
		try:
			result = ldap_connection.searchDn( filter = syn.searchFilter )
		except udm_errors.base:
			MODULE.process( 'Failed to initialize syntax class %s' % syntax_name )
			return
		syn.choices = []
		for dn in result:
			dn_list = ldap_connection.explodeDn( dn )
			syn.choices.append( ( dn, dn_list[ 0 ].split( '=', 1 )[ 1 ] ) )
	elif issubclass( syn.__class__, udm_syntax.LDAP_Search ):
		options = options.get( 'options', {} )
		syntax = udm_syntax.LDAP_Search( options[ 'syntax' ], options[ 'filter' ], options[ 'attributes' ], options[ 'base' ], options[ 'value' ], options[ 'viewonly' ], options[ 'empty' ] )

		if '$dn$' in options:
			filter_mod = get_module( None, options[ '$dn$' ] )
			if filter_mod:
				obj = filter_mod.get( options[ '$dn$' ] )
				syntax.filter = udm.pattern_replace( syntax.filter, obj )

		syntax._prepare( ldap_connection, syntax.filter )

		syntax.choices = []
		for item in syntax.values:
			if syntax.viewonly:
				dn, display_attr = item
			else:
				dn, store_pattern, display_attr = item

			if display_attr:
				# currently we just support one display attribute
				mod_display, display = split_module_attr( display_attr[ 0 ] )
				module = get_module( mod_display, dn ) # mod_display might be None
			else:
				module = get_module( None, dn )
				display = None
			if not module:
				continue
			obj = module.get( dn )
			if not obj:
				continue

			# find the value to store
			if not syntax.viewonly:
				mod_store, store = split_module_attr( store_pattern )
				if store == 'dn':
					id = dn
				elif store in obj:
					id = obj[ store ]
				elif store in obj.oldattr and obj.oldattr[ store ]:
					id = obj.oldattr[ store ][ 0 ]
				else:
					# no valid store object, ignore
					MODULE.warn('LDAP_Search syntax "%s": "%s" is no valid property for object "%s" - ignoring entry.' % (options['syntax'], store, dn))
					continue

			# find the value to display
			if display == 'dn':
				label = dn
			elif display is None: # if view-only and in case of error
				label = '%s: %s' % ( module.title, obj[ module.identifies ] )
			else:
				if display in obj:
					label = obj[ display ]
				elif display in obj.oldattr and obj.oldattr[ display ]:
					label = obj.oldattr[ display ][ 0 ]
				else:
					label = 'Unknown attribute %s' % display

			# create list entry
			if syntax.viewonly:
				syntax.choices.append( { 'module' : 'udm', 'flavor' : module.flavor, 'objectType' : module.name, 'id' : dn, 'label' : label, 'icon' : 'udm-%s' % module.name.replace( '/', '-' ) } )
			else:
				syntax.choices.append( { 'module' : 'udm', 'flavor' : module.flavor, 'objectType' : module.name, 'id' : id, 'label' : label, 'icon' : 'udm-%s' % module.name.replace( '/', '-' ) } )
		if syntax.addEmptyValue:
			syntax.choices.insert( 0, { 'id': '', 'label': '' } )
		return syntax.choices

	return map( lambda x: { 'id' : x[ 0 ], 'label' : x[ 1 ] }, getattr( syn, 'choices', [] ) )

