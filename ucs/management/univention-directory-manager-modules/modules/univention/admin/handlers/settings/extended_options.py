# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for extended options
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

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization
from univention.debug import debug, ADMIN, INFO

translation = univention.admin.localization.translation('univention.admin.handlers.settings')
_ = translation.translate

module = 'settings/extended_options'
operations = ['add', 'edit', 'remove', 'search', 'move']
superordinate = 'settings/cn'

childs = 0
short_description = _('Settings: extended options')
long_description = _('Options for extended attributes')

options = {
}

property_descriptions = {
		'name': univention.admin.property(
			short_description=_('Name'),
			long_description=_('Name'),
			syntax=univention.admin.syntax.string,
			multivalue=False,
			include_in_default_search=1,
			options=[],
			required=True,
			may_change=False,
			identifies=True,
		),
		'shortDescription': univention.admin.property(
			short_description=_('Default short description'),
			long_description=_('Short description for the option as shown on the Option tab.'),
			syntax=univention.admin.syntax.string,
			multivalue=False,
			include_in_default_search=1,
			options=[],
			required=True,
			may_change=True,
			identifies=False
		),
		'longDescription': univention.admin.property(
			short_description=_('Default Long Description'),
			long_description=_('Long description for the option as shown on the Option tab.'),
			syntax=univention.admin.syntax.string,
			multivalue=False,
			include_in_default_search=1,
			options=[],
			required=False,
			may_change=True,
			identifies=False
		),
		'translationShortDescription': univention.admin.property(
			short_description=_('Translation of short description '),
			long_description=_('Translation of the short description for the option as shown on the Option tab'),
			syntax=univention.admin.syntax.translationTupleShortDescription,
			multivalue=True,
			include_in_default_search=1,
			options=[],
			required=False,
			may_change=True,
			identifies=False
		),
		'translationLongDescription': univention.admin.property(
			short_description=_('Translation of long description '),
			long_description=_('Translation of the long description for the option as shown on the Option tab'),
			syntax=univention.admin.syntax.translationTupleLongDescription,
			multivalue=True,
			include_in_default_search=1,
			options=[],
			required=False,
			may_change=True,
			identifies=False
		),
		'default': univention.admin.property(
			short_description=_('Default'),
			long_description=_('Enable option by default.'),
			syntax=univention.admin.syntax.boolean,
			multivalue=False,
			options=[],
			required=False,
			may_change=True,
			identifies=False
		),
		'editable': univention.admin.property(
			short_description=_('Editable'),
			long_description=_('Option may be repeatly turned on and off.'),
			syntax=univention.admin.syntax.boolean,
			multivalue=False,
			options=[],
			required=False,
			may_change=True,
			identifies=False
		),
		'module': univention.admin.property(
			short_description=_('Needed Module'),
			long_description=_('List of modules this option applies to.'),
			syntax=univention.admin.syntax.univentionAdminModules,
			multivalue=True,
			options=[],
			required=True,
			may_change=True,
			identifies=False
		),
		'objectClass': univention.admin.property(
			short_description=_('Object Class'),
			long_description=_('Mapping to LDAP objectClasses'),
			syntax=univention.admin.syntax.string,
			multivalue=True,
			options=[],
			required=False,
			may_change=True,
			identifies=False
		),
}

layout = [
	Tab(_('General'), _('Basic Values'), layout = [
		Group( _( 'General' ), layout = [
			'name',
			[ "shortDescription", "longDescription" ],
			[ "translationShortDescription", "translationLongDescription" ],
			[ "default", "editable" ],
			[ 'module', "objectClass" ],
		] ),
	] ),
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('shortDescription', 'univentionUDMOptionShortDescription', None, univention.admin.mapping.ListToString)
mapping.register('longDescription', 'univentionUDMOptionLongDescription', None, univention.admin.mapping.ListToString)
mapping.register('default', 'univentionUDMOptionDefault', None, univention.admin.mapping.ListToString)
mapping.register('editable', 'univentionUDMOptionEditable', None, univention.admin.mapping.ListToString)
mapping.register('module', 'univentionUDMOptionModule')
mapping.register('objectClass', 'univentionUDMOptionObjectClass')

class object(univention.admin.handlers.simpleLdap):
	module = module

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes = [] ):
		global mapping
		global property_descriptions

		self.mapping = mapping
		self.descriptions = property_descriptions

		univention.admin.handlers.simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes = attributes )

	def _ldap_pre_create(self):
		"""Create DN."""
		self.dn = '%s=%s,%s' % (mapping.mapName('name'), mapping.mapValue('name', self.info['name']), self.position.getDn())

	def _ldap_addlist(self):
		"""Add initial objectClasses."""
		return [('objectClass', ['top', 'univentionUDMOption'])]

	def open(self):
		"""Load and parse translations."""
		univention.admin.handlers.simpleLdap.open(self)

		for transKey in ['ShortDescription', 'LongDescription']:
			translations = []
			keys = self.oldattr.keys()
			for key in self.oldattr.keys():
				if key.startswith('univentionUDMOptionTranslation%s;entry-' % transKey):
					lang = '%s_%s' % (key[-5:-3].lower(), key[-2:].upper())
					txt = self.oldattr.get(key)[0]
					translations.append( (lang, txt) )

			debug(ADMIN, INFO, 'extended_option: added translations for %s: %s' % (transKey, translations))
			self['translation%s' % transKey] = translations

		self.save()

	def _ldap_modlist(self):
		"""Save translations."""
		ml = univention.admin.handlers.simpleLdap._ldap_modlist(self)

		for transKey in ['ShortDescription', 'LongDescription']:
			if self.hasChanged('translation%s' % transKey):
				oldlist = {}
				newlist = {}

				for lang, txt in self.oldinfo.get('translation%s' % transKey, []):
					lang = lang.replace('_','-')
					oldlist[lang] = txt
					if not lang in newlist:
						newlist[lang] = ''

				# duplicate lang entries will be removed due to use of dictionary
				for lang, txt in self.info.get('translation%s' % transKey, []):
					lang = lang.replace('_','-')
					newlist[lang] = txt
					if not lang in oldlist:
						oldlist[lang] = ''

				# modlist for new items
				for lang, txt in oldlist.items():
					if txt != newlist[lang]:
						ml.append( ('univentionUDMOptionTranslation%s;entry-%s' % (transKey, lang), oldlist[lang], newlist[lang]) )

		return ml
	
def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):
	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionUDMOption')
		])

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = [object(co, lo, None, dn, attributes = attrs ) for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit)]
	return res

def identify(dn, attr, canonical=False):
	return 'univentionUDMOption' in attr.get('objectClass', [])
