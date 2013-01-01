# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for dns reverse records
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

from univention.admin.layout import Tab, Group
import univention.admin
import univention.admin.handlers
import univention.admin.localization

translation=univention.admin.localization.translation('univention.admin.handlers.dns')
_=translation.translate

module='dns/ptr_record'
operations=['add','edit','remove','search']
superordinate='dns/reverse_zone'
usewizard=1
childs=0
short_description=_('DNS: Pointer')
long_description=''
options={
}
property_descriptions={
	'address': univention.admin.property(
			short_description=_('Address'),
			long_description='',
			syntax=univention.admin.syntax.string,
			multivalue=0,
			include_in_default_search=1,
			options=[],
			required=1,
			may_change=1,
		identifies = True
		),
	'ptr_record': univention.admin.property(
			short_description=_('Pointer'),
			long_description=_("FQDNs must end with '.'"),
			syntax=univention.admin.syntax.dnsName,
			multivalue=0,
			include_in_default_search=1,
			options=[],
			required=0,
			may_change=1
		),
}

layout = [
	Tab( _( 'General' ), _( 'Basic settings' ), layout = [
		Group( _( 'General' ), layout = [
			[ 'address', 'ptr_record' ],
		] ),
	] ),
]

mapping=univention.admin.mapping.mapping()
mapping.register('address', 'relativeDomainName', None, univention.admin.mapping.ListToString)
mapping.register('ptr_record', 'pTRRecord', None, univention.admin.mapping.ListToString)

class object(univention.admin.handlers.simpleLdap):
	module=module

	def _updateZone(self):
		if self.update_zone:
			self.superordinate.open()
			self.superordinate.modify()

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes = [], update_zone = True  ):
		self.mapping=mapping
		self.descriptions=property_descriptions
		self.update_zone = update_zone

		if not superordinate:
			raise univention.admin.uexceptions.insufficientInformation, _( 'superordinate object not present' )
		if not dn and not position:
			raise univention.admin.uexceptions.insufficientInformation, _( 'neither DN nor position present' )

		univention.admin.handlers.simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes = attributes )

	def _ldap_pre_create(self):
		self.dn='%s=%s,%s' % (mapping.mapName('address'), mapping.mapValue('address', self['address']), self.position.getDn())

	def _ldap_addlist(self):
		return [
			('objectClass', ['top', 'dNSZone']),
			(self.superordinate.mapping.mapName('subnet'), self.superordinate.mapping.mapValue('subnet', self.superordinate['subnet'])),
		]

	def _ldap_post_modify(self):
		if self.hasChanged(self.descriptions.keys()):
			self._updateZone()

	def _ldap_post_create(self):
		self._updateZone()

	def _ldap_post_remove(self):
		self._updateZone()

def lookup(co, lo, filter_s, base='', superordinate=None,scope="sub", unique=0, required=0, timeout=-1, sizelimit=0):

	filter=univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'dNSZone'),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('relativeDomainName', '@')]),
		univention.admin.filter.conjunction('|', [
			univention.admin.filter.expression('zoneName', '*.in-addr.arpa'),
			univention.admin.filter.expression('zoneName', '*.ip6.arpa'),
			]),
		])

	if superordinate:
		filter.expressions.append(univention.admin.filter.expression('zoneName', superordinate.mapping.mapValue('subnet', superordinate['subnet'])))

	if filter_s:
		filter_p=univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res=[]
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append((object(co, lo, None, dn=dn, superordinate=superordinate, attributes = attrs )))
	return res

def identify(dn, attr):

	return 'dNSZone' in attr.get('objectClass', []) and\
		'@' not in attr.get('relativeDomainName', []) and\
		(attr['zoneName'][0].endswith('.in-addr.arpa') or attr['zoneName'][0].endswith('.ip6.arpa'))
