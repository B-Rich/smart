# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  unit tests: container/[cn|ou] tests
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


from GenericTest import GenericTestCase, TestError


class PathRegisteredError(TestError):
	def __init__(self, test, dn, type):
		e1 = 'Object %s at DN %s (module %s)' \
		     % (test.name, dn, test.modname)
		e2 = ' erroneously registered as a default %s container' % type
		error = e1 + e2
		TestError.__init__(self, error, test)

class PathNotRegisteredError(TestError):
	def __init__(self, test, dn, type):
		e1 = 'Object %s at DN %s (module %s)' \
		     % (test.name, dn, test.modname)
		e2 = ' not registered as a default %s container' % type
		error = e1 + e2
		TestError.__init__(self, error, test)


# TODO: Find a way to use umlauts in container names so we can test them.
class ContainerBaseCase(GenericTestCase):
	def __init__(self, *args, **kwargs):
		self.modname = 'container/%s' % self.type
		super(ContainerBaseCase, self).__init__(*args, **kwargs)
		self.types = ['dns', 'dhcp', 'users', 'groups',
			      'computers', 'license', 'policy']

	def __checkDefaultContainers(self, dn, type):
		container = self.rdn('cn=default containers,cn=univention')
		attribute = 'univention%sObject' % type.capitalize()
		attr = self.ldap.get(dn = container, attr = [attribute])
		return dn in attr.get(attribute, [])

	# Ensure container object is not registered as a default container.
	def hookAfterCreated(self, dn):
		for type in self.types:
			if self.__checkDefaultContainers(dn, type):
				raise PathRegisteredError(self, dn, type)

	# Ensure container object is registered as a default container.
	def hookAfterModified(self, dn):
		for type in self.types:
			if not self.__checkDefaultContainers(dn, type):
				raise PathNotRegisteredError(self, dn, type)

	# Ensure container object is not registered as a default container.
	def hookAfterRemoved(self, dn):
		for type in self.types:
			if self.__checkDefaultContainers(dn, type):
				raise PathRegisteredError(self, dn, type)

	def setUp(self):
		super(ContainerBaseCase, self).setUp()
		self.name = 'test%s' % self.type
		self.createProperties = {
			'dnsPath': '0',
			'dhcpPath': '0',
			'userPath': '0',
			'groupPath': '0',
			'computerPath': '0',
			'licensePath': '0',
			'policyPath': '0',
			'description': 'some test %s container' % self.type,
			}
		self.modifyProperties = {
			'dnsPath': '1',
			'dhcpPath': '1',
			'groupPath': '1',
			'userPath': '1',
			'computerPath': '1',
			'licensePath': '1',
			'policyPath': '1',
			'description': 'Some Tested %s Container' \
			% self.type.upper(),
			}


class ContainerCNTestCase(ContainerBaseCase):
	def __init__(self, *args, **kwargs):
		self.type = 'cn'
		super(ContainerCNTestCase, self).__init__(*args, **kwargs)

class ContainerOUTestCase(ContainerBaseCase):
	def __init__(self, *args, **kwargs):
		self.type = 'ou' 
		super(ContainerOUTestCase, self).__init__(*args, **kwargs)


def suite():
	import sys, unittest
	suite = unittest.TestSuite()
	suite.addTest(ContainerCNTestCase())
	suite.addTest(ContainerOUTestCase())
	return suite


if __name__ == '__main__':
	import unittest
	unittest.TextTestRunner().run(suite())
