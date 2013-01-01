#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
# pylint: disable-msg=C0103,W0622,W0312
"""
Univention Bind listener script

During the update period, only create the configuration snippets for named and
the proxy.
During the quiet period check the cache directory (is-state) against the
configuration directory (should-state) and reload/restart as appropriate.
"""
# Copyright 2001-2012 Univention GmbH
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

__package__ = '' 	# workaround for PEP 366
import listener
import os
import univention.debug as ud  # pylint: disable-msg=E0611
import time
import errno
import signal

name = 'bind'
description = 'Update BIND zones'
filter = '(&(objectClass=dNSZone)(relativeDomainName=@)(zoneName=*))'
attributes = []

NAMED_CONF_FILE = "/etc/bind/univention.conf"
NAMED_CONF_DIR  = "/etc/bind/univention.conf.d"
PROXY_CONF_FILE = "/etc/bind/univention.conf.proxy"
NAMED_CACHE_DIR = "/var/cache/bind"
PROXY_CACHE_DIR = "/var/cache/univention-bind-proxy"
RNDC_BIN = "/usr/sbin/rndc"

SIGNAL = dict([(getattr(signal, _), _) for _ in dir(signal) if
	_.startswith('SIG') and not _.startswith('SIG_')])

__zone_created_or_removed = False

def initialize():
	"""Initialize module on first run."""
	pass


def prerun():
	"""Called before busy period."""
	listener.configRegistry.load()


def handler(dn, new, old):
	"""Handle LDAP changes."""
	base = listener.configRegistry.get('dns/ldap/base')
	if base and not dn.endswith(base):
		return

	listener.setuid(0)
	try:
		if new and not old:
			# Add
			_new_zone(listener.configRegistry, new['zoneName'][0], dn)
		elif old and not new:
			# Remove
			_remove_zone(old['zoneName'][0])
		if new.get('zoneName'):
			# Change
			# Create an empty file to trigger the postrun()
			zonefile = os.path.join(PROXY_CACHE_DIR, "%s.zone" % (new['zoneName'][0],))
			proxy_cache = open(zonefile, 'w')
			proxy_cache.close()
			os.chmod(zonefile, 0640)
	finally:
		listener.unsetuid()


def _ldap_auth_string(ucr):
	"""Build extended LDAP query URI part containing bind credentials."""
	account = ucr.get('bind/binddn', ucr.get('ldap/hostdn')).replace(',', '%2c')

	pwdfile = ucr.get('bind/bindpw', '/etc/machine.secret')
	pwd = open(pwdfile).readlines()

	return '????!bindname=%s,!x-bindpw=%s,x-tls' % (account, pwd[0])


def _new_zone(ucr, zonename, dn):
	"""Handle addition of zone."""
	ud.debug(ud.LISTENER, ud.INFO, 'DNS: Creating zone %s' % (zonename,))
	if not os.path.exists(NAMED_CONF_DIR):
		os.mkdir(NAMED_CONF_DIR)

	zonefile = os.path.join(NAMED_CONF_DIR, zonename)

	# Create empty file and restrict permission
	named_zone = open(zonefile, 'w')
	named_zone.close()
	os.chmod(zonefile, 0640)

	# Now fill zone file
	ldap_uri = "ldap://%s:%s/%s%s" % (
			ucr.get('bind/ldap/server/ip', '127.0.0.1'),
			ucr.get('ldap/server/port', '7389'),
			dn,
			_ldap_auth_string(ucr)
			)
	named_zone = open(zonefile, 'w+')
	named_zone.write('zone "%s" {\n' % (zonename,))
	named_zone.write('\ttype master;\n')
	named_zone.write('\tnotify yes;\n')
	named_zone.write('\tdatabase "ldap %s 172800";\n' % (ldap_uri,))
	named_zone.write('};\n')
	named_zone.close()

	# Create proxy configuration file
	proxy_zone = open(os.path.join(NAMED_CONF_DIR, zonename+'.proxy'), 'w')
	proxy_zone.write('zone "%s" {\n' % (zonename,))
	proxy_zone.write('\ttype slave;\n')
	proxy_zone.write('\tfile "%s.zone";\n' % (zonename,))
	proxy_zone.write('\tmasters port 7777 { 127.0.0.1; };\n')
	proxy_zone.write('};\n')
	proxy_zone.close()
	global __zone_created_or_removed
	__zone_created_or_removed = True


def _remove_zone(zonename):
	"""Handle removal of zone."""
	ud.debug(ud.LISTENER, ud.INFO, 'DNS: Removing zone %s' % (zonename,))
	zonefile = os.path.join(NAMED_CONF_DIR, zonename)
	# Remove zone file
	if os.path.exists(zonefile):
		os.unlink(zonefile)
	# Remove proxy configuration file
	if os.path.exists(zonefile + '.proxy'):
		os.unlink(zonefile + '.proxy')
	global __zone_created_or_removed
	__zone_created_or_removed = True


def clean():
	"""Reset listener state."""
	listener.setuid(0)
	try:
		if os.path.exists(NAMED_CONF_FILE):
			os.unlink(NAMED_CONF_FILE)
		open(NAMED_CONF_FILE, 'w').close()

		if os.path.isdir(NAMED_CONF_DIR):
			for f in os.listdir(NAMED_CONF_DIR):
				os.unlink(os.path.join(NAMED_CONF_DIR, f))
			os.rmdir(NAMED_CONF_DIR)
	finally:
		listener.unsetuid()


def _reload(zones, restart=False):
	"""Force reload of zones; might restart daemon; returns pids."""
	pids = {}
	if zones:
		# Try to only reload the zones if rndc is available
		if os.path.exists(RNDC_BIN):
			for zone in zones:
				ud.debug(ud.LISTENER, ud.INFO, 'DNS: Reloading zone %s' % (zone,))
				cmd = ['rndc', '-p', '55555', 'reload', zone]
				pid = os.spawnv(os.P_NOWAIT, RNDC_BIN, cmd)
				pids[pid] = cmd
				cmd = ['rndc', '-p', '953', 'reload', zone]
				pid = os.spawnv(os.P_NOWAIT, RNDC_BIN, cmd)
				pids[pid] = cmd
		else:
			restart = True
	# Fall back to restart, which will temporarily interrupt the service
	if restart:
		ud.debug(ud.LISTENER, ud.INFO, 'DNS: Restarting BIND')
		cmd = ['invoke-rc.d', 'bind9', 'restart']
		pid = os.spawnv(os.P_NOWAIT, '/usr/sbin/invoke-rc.d', cmd)
		pids[pid] = cmd
	return pids


def _wait_children(pids, timeout=15):
	"""Wait for child termination."""
	# Wait max 15 seconds for forked children
	timeout += time.time()
	while pids:
		try:
			pid, status = os.waitpid(0, os.WNOHANG)  # non-blocking
		except OSError, ex:
			if ex.errno == errno.ECHILD:
				break  # no more own children
			else:
				ud.debug(ud.LISTENER, ud.WARN, 'DNS: Unexpected error: %s' % (ex,))
		else:
			if pid:  # only when waitpid() found one child
				# Ignore unexpected child from other listener modules (Bug #21363)
				cmd = pids.pop(pid, '')
				if os.WIFSIGNALED(status):
					sig = os.WTERMSIG(status)
					sig = SIGNAL.get(sig, sig)
					ud.debug(ud.LISTENER, ud.WARN, 'DNS: %d="%s" exited by signal %s' % \
							(pid, ' '.join(cmd), sig))
				elif os.WIFEXITED(status):
					ret = os.WEXITSTATUS(status)
					if ret:
						ud.debug(ud.LISTENER, ud.WARN, 'DNS: %d="%s" exited with %d' % \
								(pid, ' '.join(cmd), ret))
				else:
					ud.debug(ud.LISTENER, ud.WARN, 'DNS: %d="%s" exited status %d' % \
							(pid, ' '.join(cmd), status))
				continue

		if time.time() > timeout:
			ud.debug(ud.LISTENER, ud.WARN, 'DNS: Pending children: %s' % \
					(' '.join([str(pid) for pid in pids]),))
			break
		time.sleep(1)


def _kill_children(pids, timeout=5):
	"""Kill children."""
	for pid in pids:
		try:
			os.kill(pid, signal.SIGTERM)
		except OSError, ex:
			if ex.errno != errno.ESRCH:
				ud.debug(ud.LISTENER, ud.WARN, 'DNS: Unexpected error: %s' % (ex,))
	_wait_children(pids, timeout)
	for pid in pids:
		try:
			os.kill(pid, signal.SIGKILL)
		except OSError, ex:
			if ex.errno != errno.ESRCH:
				ud.debug(ud.LISTENER, ud.WARN, 'DNS: Unexpected error: %s' % (ex,))
	_wait_children(pids, timeout)


def postrun():
	"""Run pending updates."""
	global __zone_created_or_removed

	listener.setuid(0)
	try:
		# Re-create named and proxy inclusion file
		named_conf = open(NAMED_CONF_FILE, 'w')
		proxy_conf = open(PROXY_CONF_FILE, 'w')
		if os.path.isdir(NAMED_CONF_DIR):
			for f in os.listdir(NAMED_CONF_DIR):
				if not f.endswith('.proxy'):
					named_conf.write('include "%s";\n' % os.path.join(NAMED_CONF_DIR, f))
				else:
					proxy_conf.write('include "%s";\n' % os.path.join(NAMED_CONF_DIR, f))
		named_conf.close()
		proxy_conf.close()

		do_reload = True
		dns_backend = listener.configRegistry.get('dns/backend')
		if dns_backend == 'samba4':
			if not __zone_created_or_removed:
				do_reload = False
			else:	## reset flag and continue with reload
				__zone_created_or_removed = False
		elif dns_backend == 'none':
				do_reload = False

		if do_reload:
			ud.debug(ud.LISTENER, ud.INFO, 'DNS: Doing reload')
		else:
			ud.debug(ud.LISTENER, ud.INFO, 'DNS: Skip zone reload')
			return

		# Restart is needed when new zones are added or old zones removed.
		restart = False
		zones = []
		for filename in os.listdir(PROXY_CACHE_DIR):
			os.remove(os.path.join(PROXY_CACHE_DIR, filename))
			if not os.path.exists(os.path.join(NAMED_CACHE_DIR, filename)):
				restart = True
			else:
				zone = filename.replace(".zone", "")
				zones.append(zone)

		ud.debug(ud.LISTENER, ud.INFO, 'DNS: Zones: %s' % (zones,))
		pids = _reload(zones, restart)
		_wait_children(pids)
		_kill_children(pids)
	finally:
		listener.unsetuid()
