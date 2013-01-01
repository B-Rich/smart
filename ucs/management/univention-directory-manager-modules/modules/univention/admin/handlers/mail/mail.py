# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for mail objects
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
import univention.admin.filter
import univention.admin.localization

import univention.admin.handlers
import univention.admin.handlers.mail.domain
import univention.admin.handlers.mail.folder
import univention.admin.handlers.mail.lists


translation=univention.admin.localization.translation('univention.admin.handlers.mail')
_=translation.translate


module='mail/mail'

childs=0
short_description=_('Mail')
long_description=''
operations=['search']
usewizard=1
wizardmenustring=_("Mail")
wizarddescription=_("Add, edit and delete mail objects")
wizardoperations={"add":[_("Add"), _("Add mail object")],"find":[_("Search"), _("Search mail object(s)")]}

childmodules=["mail/folder","mail/domain", "mail/lists"]
wizardpath='univentionMailObject'
virtual=1
options={
}
property_descriptions={
	'name': univention.admin.property(
			short_description=_('Name'),
			long_description='',
			syntax=univention.admin.syntax.string,
			multivalue=0,
			include_in_default_search=1,
			options=[],
			required=1,
			may_change=1,
			identifies=1
		)
}
layout = [ Tab( _( 'General' ), _( 'Basic settings' ), [ "name" ] ) ]

mapping=univention.admin.mapping.mapping()


class object(univention.admin.handlers.simpleLdap):
	module=module

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes = [] ):
		global mapping
		global property_descriptions

		self.mapping=mapping
		self.descriptions=property_descriptions

		univention.admin.handlers.simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes = attributes )


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=0, required=0, timeout=-1, sizelimit=0):
	ret=[]
	ret+=univention.admin.handlers.mail.domain.lookup(co, lo, filter_s, base, superordinate, scope, unique, required, timeout, sizelimit)
	ret+=univention.admin.handlers.mail.folder.lookup(co, lo, filter_s, base, superordinate, scope, unique, required, timeout, sizelimit)
	ret+=univention.admin.handlers.mail.lists.lookup(co, lo, filter_s, base, superordinate, scope, unique, required, timeout, sizelimit)
	return ret

def identify(dn, attr, canonical=0):
	pass


