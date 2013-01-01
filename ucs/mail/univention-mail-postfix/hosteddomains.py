# -*- coding: utf-8 -*-
#
# Univention Mail Stack
#  listener module: mail domain configuration
#
# Copyright 2005-2012 Univention GmbH
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

__package__='' 	# workaround for PEP 366
import listener
import univention.config_registry
import os, re
import univention.debug

name='hosteddomains'
description='update mail/hosteddomains'
filter='(objectClass=univentionMailDomainname)'
attributes=[]

reload = False

def initialize():
	pass

def handler(dn, new, old):
	global reload
	configRegistry = univention.config_registry.ConfigRegistry()
	configRegistry.load()

	old_hosteddomains = set(re.split('[ ]+', configRegistry.get('mail/hosteddomains','')))
	hosteddomains = old_hosteddomains.copy()

	# remove old add new
	if old.get('cn'):
		hosteddomains.discard(old.get('cn')[0])
		univention.debug.debug(univention.debug.LISTENER, univention.debug.INFO, "hosteddomains: removed %s" % old.get('cn')[0])
	if new.get('cn'):
		hosteddomains.add(new.get('cn')[0])
		univention.debug.debug(univention.debug.LISTENER, univention.debug.INFO, "hosteddomains: added %s" % new.get('cn')[0])

	# if something changed then set UCR variable
	if old_hosteddomains != hosteddomains:
		try:
			listener.setuid(0)
			univention.debug.debug(univention.debug.LISTENER, univention.debug.INFO, "hosteddomains: %s" % u'mail/hosteddomains=%s' % ' '.join(hosteddomains) )
			univention.config_registry.handler_set( [ u'mail/hosteddomains=%s' % ' '.join(hosteddomains) ] )
			reload = True
		finally:
			listener.unsetuid()

def postrun():
	global reload
	if reload:
		# reload cyrus-imapd if UCR variable changed
		listener.setuid(0)
		try:
			for fn in [ '/etc/init.d/cyrus-imapd', '/etc/init.d/cyrus2.2' ]:
				if os.path.isfile(fn):
					listener.run(fn, [os.path.basename(fn), 'reload'], uid=0)
		finally:
			listener.unsetuid()
		reload = False
