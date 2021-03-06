# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for the user himself
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

from univention.admin.layout import Tab
import univention.admin.handlers
import univention.admin.localization

import univention.admin.handlers.users.user as udm_user

translation=univention.admin.localization.translation('univention.admin.handlers.users')
_=translation.translate

module = 'users/self'
operations = [ 'edit','search' ]
options = {}

mapping = udm_user.mapping

property_descriptions = {
	'password' : udm_user.property_descriptions[ 'password' ]
	}

layout = [ Tab( _( 'General' ), layout = [ 'password' ] ) ]

uid_umlauts=0
childs=0
short_description=_('User: Self')
long_description=''

class object( univention.admin.handlers.users.user.object ):
	module=module

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes = [] ):
		univention.admin.handlers.users.user.object.__init__( self, co, lo, position, dn, superordinate, attributes )

