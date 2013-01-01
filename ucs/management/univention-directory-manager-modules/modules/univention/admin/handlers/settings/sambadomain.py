# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for samba domain configuration
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

import os

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.password
import univention.admin.allocators
import univention.admin.localization

translation=univention.admin.localization.translation('univention.admin.handlers.settings')
_=translation.translate

# see also container/dc.py
def logonToChangePWMap(val):
	"""
	'User must logon to change PW' behaves like an integer (at least
	to us), but must be stored as either 0 (allow) or 2 (disallow)
	"""
	
	if (val=="1"):
		return "2"
	else:
		return "0"

# see also container/dc.py
def logonToChangePWUnmap(val):
	
	if (val[0]=="2"):
		return "1"
	else:
		return "2"

module='settings/sambadomain'
childs=0
operations=['add','edit','remove','search','move']
short_description=_('Settings: Samba Domain')
long_description=''
options={}
property_descriptions={
	'name': univention.admin.property(
	        short_description=_('Samba domain name'),
			long_description='',
			syntax=univention.admin.syntax.string,
			multivalue=0,
			include_in_default_search=1,
			options=[],
			required=1,
			may_change=1,
			identifies=1
			),
	'SID': univention.admin.property(
			short_description=_('Samba SID'),
			long_description='',
			syntax=univention.admin.syntax.string,
			multivalue=0,
			options=[],
			required=0,
			may_change=0,
			default = '',
			identifies=0
			),
	'NextUserRid': univention.admin.property(
			short_description=_('Next user RID'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			default= '1000',
			identifies=0
		),
	'NextGroupRid': univention.admin.property(
			short_description=_('Next group RID'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			default = '1000',
			identifies=0
			),
	'NextRid': univention.admin.property(
			short_description=_('Next RID'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			default = '1000',
			identifies=0
			),
	'passwordLength': univention.admin.property(
			short_description=_('Password length'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
			),
	'passwordHistory': univention.admin.property(
			short_description=_('Password history'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'minPasswordAge': univention.admin.property(
			short_description=_('Minimum password age'),
			long_description='',
			syntax=univention.admin.syntax.UNIX_TimeInterval,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'badLockoutAttempts': univention.admin.property(
			short_description=_('Bad lockout attempts'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'logonToChangePW': univention.admin.property(
			short_description=_('User must logon to change password'),
			long_description='',
			syntax=univention.admin.syntax.boolean,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'maxPasswordAge': univention.admin.property(
			short_description=_('Maximum password age'),
			long_description='',
			syntax=univention.admin.syntax.UNIX_TimeInterval,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'lockoutDuration': univention.admin.property(
			short_description=_('Lockout duration minutes'),
			long_description='',
			syntax=univention.admin.syntax.UNIX_TimeInterval,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'resetCountMinutes': univention.admin.property(
			short_description=_('Reset count minutes'),
			long_description='',
			syntax=univention.admin.syntax.integer,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'disconnectTime': univention.admin.property(
			short_description=_('Disconnect time'),
			long_description='',
			syntax=univention.admin.syntax.UNIX_TimeInterval,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'refuseMachinePWChange': univention.admin.property(
			short_description=_('Refuse machine password change'),
			long_description='',
			syntax=univention.admin.syntax.boolean,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	}

layout = [
	Tab(_('General'),_('Basic Values'), layout = [
		Group( _( 'General' ), layout = [
			["name", "SID"],
			["NextRid", "NextUserRid", "NextGroupRid"],
		] ),
		Group(_( 'Password' ), layout = [
			["passwordLength", "passwordHistory"],
			["minPasswordAge"],
			["maxPasswordAge"],
			["logonToChangePW", "refuseMachinePWChange"],
		] ),
		Group( _('Connection'), layout = [
			["badLockoutAttempts"],
			["resetCountMinutes"],
			["lockoutDuration"],
			["disconnectTime"],
		] ),
	] ),
]


mapping=univention.admin.mapping.mapping()
mapping.register('name', 'sambaDomainName', None, univention.admin.mapping.ListToString)
mapping.register('SID', 'sambaSID', None, univention.admin.mapping.ListToString)
mapping.register('NextUserRid', 'sambaNextUserRid', None, univention.admin.mapping.ListToString)
mapping.register('NextGroupRid', 'sambaNextGroupRid', None, univention.admin.mapping.ListToString)
mapping.register('NextRid', 'sambaNextRid', None, univention.admin.mapping.ListToString)
mapping.register('passwordLength', 'sambaMinPwdLength', None, univention.admin.mapping.ListToString)
mapping.register('passwordHistory', 'sambaPwdHistoryLength', None, univention.admin.mapping.ListToString)
mapping.register('minPasswordAge', 'sambaMinPwdAge', univention.admin.mapping.mapUNIX_TimeInterval, univention.admin.mapping.unmapUNIX_TimeInterval )
mapping.register('maxPasswordAge', 'sambaMaxPwdAge', univention.admin.mapping.mapUNIX_TimeInterval, univention.admin.mapping.unmapUNIX_TimeInterval )
mapping.register('badLockoutAttempts', 'sambaLockoutThreshold', None, univention.admin.mapping.ListToString)
mapping.register('logonToChangePW', 'sambaLogonToChgPwd', logonToChangePWMap, logonToChangePWUnmap)
mapping.register('lockoutDuration', 'sambaLockoutDuration', univention.admin.mapping.mapUNIX_TimeInterval, univention.admin.mapping.unmapUNIX_TimeInterval )
mapping.register('resetCountMinutes', 'sambaLockoutObservationWindow', None, univention.admin.mapping.ListToString)
mapping.register('disconnectTime', 'sambaForceLogoff', univention.admin.mapping.mapUNIX_TimeInterval, univention.admin.mapping.unmapUNIX_TimeInterval )
mapping.register('refuseMachinePWChange', 'sambaRefuseMachinePwdChange', None, univention.admin.mapping.ListToString)

class object(univention.admin.handlers.simpleLdap):
	module=module

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes = [] ):
		global mapping
		global property_descriptions

		self.mapping=mapping
		self.descriptions=property_descriptions
 		self.options=[]

		self.alloc=[]

		univention.admin.handlers.simpleLdap.__init__(self, co, lo,  position, dn, superordinate, attributes = attributes )

	def open(self):
		univention.admin.handlers.simpleLdap.open(self)

	def _ldap_pre_create(self):		
		self.dn='sambaDomainName=%s,%s' % ( mapping.mapValue('name', self.info['name']), self.position.getDn())

	def _ldap_addlist(self):
		ocs=['sambaDomain']		

		return [
			('objectClass', ocs),
		]

	
def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=0, required=0, timeout=-1, sizelimit=0):

	filter=univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'sambaDomain'),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('objectClass', 'univentionDomain')]),
		])

	if filter_s:
		filter_p=univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res=[]
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append( object( co, lo, None, dn, attributes = attrs ) )
	return res

def identify(dn, attr, canonical=0):
	
	return 'sambaDomain' in attr.get('objectClass', []) and not 'univentionDomain' in attr.get('objectClass', [])

