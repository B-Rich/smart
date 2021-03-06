# -*- coding: utf-8 -*-
#
# UCS Virtual Machine Manager Daemon
#  ldap integration
#
# Copyright 2010-2012 Univention GmbH
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
"""UVMM LDAP integration."""

import os
import errno
try:
	import cPickle as pickle
except ImportError:
	import pickle
import univention.config_registry as ucr
import univention.uldap
from ldap import LDAPError, SERVER_DOWN
import ldapurl
import univention.admin.uldap
import univention.admin.modules
import univention.admin.handlers.uvmm.info as uvmm_info
from helpers import TranslatableException, N_ as _, FQDN as HOST_FQDN
import logging

configRegistry = ucr.ConfigRegistry()
configRegistry.load()

logger = logging.getLogger('uvmmd.ldap')

# Mapping from service name to libvirt-uri
SERVICES = {
		"XEN Host": "xen://%s/",
		"KVM Host": "qemu://%s/system",
		}

LDAP_UVMM_RDN = "cn=Virtual Machine Manager"
LDAP_INFO_RDN = "cn=Information,%s" % LDAP_UVMM_RDN
LDAP_PROFILES_RDN = "cn=Profiles,%s" % LDAP_UVMM_RDN

class LdapError(TranslatableException):
	"""LDAP error."""
	pass

class LdapConfigurationError(LdapError):
	"""LDAP configuration error."""
	pass

class LdapConnectionError(LdapError):
	"""LDAP connection error."""
	pass

def ldap2fqdn(ldap_result):
	"""Convert LDAP result to fqdn."""
	if not 'associatedDomain' in ldap_result:
		domain = configRegistry.get( 'domainname', '' )
	else:
		domain = ldap_result[ 'associatedDomain' ][ 0 ]
	return "%s.%s" % (ldap_result['cn'][0], domain)

def cached(cachefile, func, exception=LdapConnectionError):
	"""Cache result of function or return cached result on LdapConnectionException."""
	try:
		result = func()

		file = open("%s.new" % (cachefile,), "w")
		try:
			p = pickle.Pickler(file)
			p.dump(result)
		finally:
			file.close()
		try:
			os.remove("%s.old" % (cachefile,))
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise LdapError(_('Error removing %(file)s.old: %(msg)s'), file=cachefile, msg=e)
		try:
			os.rename("%s" % (cachefile,), "%s.old" % (cachefile,))
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise LdapError(_('Error renaming %(file)s: %(msg)s'), file=cachefile, msg=e)
		try:
			os.rename("%s.new" % (cachefile,), "%s" % (cachefile,))
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise LdapError(_('Error renaming %(file)s.new: %(msg)s'), file=cachefile, msg=e)
	except IOError, e:
		# LdapError("Error writing %(file)s: %(msg)e", file=cachefile, msg=e)
		pass
	except exception, msg:
		logger.info('Using cached data "%s"' % (cachefile,))
		try:
			file = open("%s" % (cachefile,), "r")
			try:
				p = pickle.Unpickler(file)
				result = p.load()
			finally:
				file.close()
		except IOError, e:
			if e.errno != errno.ENOENT:
				raise exception(_('Error reading %(file)s: %(msg)s'), file=cachefile, msg=e)
			raise msg
		except EOFError:
			raise exception(_('Error reading incomplete %(file)s.'), file=cachefile)

	return result

def ldap_uris(ldap_uri=None):
	"""Return all nodes registered in LDAP."""
	if len(SERVICES) == 0:
		raise LdapConfigurationError(_('No SERVICES defined.'))

	# Build filter to find all Virtualization nodes
	filter_list = ["(univentionService=%s)" % service for service in SERVICES]
	if len(filter_list) > 1:
		filter = "(|%s)" % "".join(filter_list)
	else:
		filter = filter_list[0]

	# ensure that we should manage the host
	filter = '(&%s(|(!(univentionVirtualMachineManageableBy=*))(univentionVirtualMachineManageableBy=%s)))' % ( filter, HOST_FQDN )
	logger.debug('Find servers to manage "%s"' % filter)
	lo, position = univention.admin.uldap.getMachineConnection(ldap_master=False)
	try:
		nodes = []
		res = lo.search(filter)
		for dn, data in res:
			fqdn = ldap2fqdn(data)
			for service in SERVICES:
				if service in data['univentionService']:
					uri = SERVICES[service] % fqdn
					nodes.append(uri)
		logger.debug('Registered URIs: %s' % ', '.join(nodes))
		return nodes
	except LDAPError, e:
		raise LdapConnectionError(_('Could not query "%(uri)s"'), uri=ldap_uri)

def ldap_annotation(uuid):
	"""Load annotations for domain from LDAP."""
	try:
		lo, position = univention.admin.uldap.getMachineConnection(ldap_master=False)
		base = "%s,%s" % (LDAP_INFO_RDN, position.getDn())
	except ( SERVER_DOWN, IOError ), e:
		raise LdapConnectionError(_('Could not open LDAP-Machine connection'))
	co = None
	dn = "%s=%s,%s" % (uvmm_info.mapping.mapName('uuid'), uuid, base)
	filter = "(objectclass=*)"
	logger.debug('Querying domain infos "%s"' % dn)
	try:
		res = univention.admin.modules.lookup(uvmm_info, co, lo, scope='base', base=dn, filter=filter, required=True, unique=True)
		record = res[0]
		return dict(record)
	except univention.admin.uexceptions.base:
		return {}

def ldap_modify(uuid):
	"""Modify annotations for domain from LDAP."""
	try:
		lo, position = univention.admin.uldap.getMachineConnection(ldap_master=True)
		base = "%s,%s" % (LDAP_INFO_RDN, position.getDn())
	except (SERVER_DOWN, IOError ), e:
		raise LdapConnectionError(_('Could not open LDAP-Admin connection'))
	co = None
	dn = "%s=%s,%s" % (uvmm_info.mapping.mapName('uuid'), uuid, base)
	filter = "(objectclass=*)"
	logger.debug('Updating domain infos "%s"' % dn)
	try:
		res = univention.admin.modules.lookup(uvmm_info, co, lo, scope='base', base=dn, filter=filter, required=True, unique=True)
		record = res[0]
		record.open()
		record.commit = record.modify
	except univention.admin.uexceptions.base:
		position.setDn(base)
		record = uvmm_info.object(co, lo, position)
		record['uuid'] = uuid
		record['description'] = None
		record['contact'] = None
		record['profile'] = None
		record.commit = record.create
	return record
