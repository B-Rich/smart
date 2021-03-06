# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  unit tests: locking tests
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


from BaseTest import BaseCase, TestError


class LeftoverLocks(TestError):
	def __init__(self, dns, test):
		error = '''There were leftover locks in:
%s''' % ('\n'.join(dns))
		TestError.__init__(self, error, test)


class LockingTestCase(BaseCase):
	def __removeLocks(self, dns):
		for dn in dns:
			self.ldap.delete(dn)

	def testLocks(self, remove = False):
		results = self.ldap.search(filter = '(objectClass=lock)',
					   attr = ['dn'])
		dns = [dn for (dn, _) in results]
		if remove:
			self.__removeLocks(dns)
		elif dns:		# or rather `if'?
			raise LeftoverLocks(dns, self)

	def removeLocks(self):
		self.testLocks(remove = True)

	def shortDescription(self):
		return 'searching remaining locks'


def suite():
	import sys, unittest
	suite = unittest.TestSuite()
	suite.addTest(LockingTestCase(methodName = 'testLocks'))
	return suite


if __name__ == '__main__':
	import unittest
	unittest.TextTestRunner().run(suite())
