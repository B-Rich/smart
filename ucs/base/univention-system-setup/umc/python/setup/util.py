#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: system setup
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

import copy
import ipaddr
import os
import tempfile
import subprocess
import threading
import univention.config_registry
from univention.config_registry.interfaces import RE_IFACE
import time
import re
import sys
import apt
import psutil
import csv

from univention.lib.i18n import Translation
from univention.management.console.log import MODULE

installer_i18n = Translation( 'installer', localedir = '/lib/univention-installer/locale' )

if not '/lib/univention-installer/' in sys.path:
	sys.path.append('/lib/univention-installer/')
import package_list
import imp

ucr=univention.config_registry.ConfigRegistry()
ucr.load()

PATH_SYS_CLASS_NET = '/sys/class/net'
PATH_SETUP_SCRIPTS = '/usr/lib/univention-system-setup/scripts/'
PATH_JOIN_SCRIPT = '/usr/lib/univention-system-setup/scripts/setup-join.sh'
PATH_PROFILE = '/var/cache/univention-system-setup/profile'
LOG_FILE = '/var/log/univention/setup.log'
PATH_BROWSER_PID = '/var/cache/univention-system-setup/browser.pid'
PATH_PASSWORD_FILE = '/var/cache/univention-system-setup/secret'
CMD_ENABLE_EXEC = ['/usr/share/univention-updater/enable-apache2-umc', '--no-restart']
CMD_ENABLE_EXEC_WITH_RESTART = '/usr/share/univention-updater/enable-apache2-umc'
CMD_DISABLE_EXEC = '/usr/share/univention-updater/disable-apache2-umc'

RE_IPV4_DEVICE = re.compile(r'interfaces/(?P<device>[^/]+)/(?P<type>.*)')
RE_IPV4_TYPE = re.compile('interfaces/[^/]*/type')
RE_LOCALE = re.compile(r'([^.@ ]+).*')

# list of all needed UCR variables
UCR_VARIABLES = [
	# common
	'server/role',
	# language
	'locale', 'locale/default',
	# keyboard
	'locale/keymap',
	# basis
	'hostname', 'domainname', 'ldap/base', 'windows/domain',
	# net: ipv4
	'gateway',
	'nameserver1', 'nameserver2', 'nameserver3',
	'dns/forwarder1', 'dns/forwarder2', 'dns/forwarder3',
	'proxy/http',
	# net: ipv6
	'ipv6/gateway',
	# ssl
	'ssl/common', 'ssl/locality', 'ssl/country', 'ssl/state',
	'ssl/organization', 'ssl/organizationalunit', 'ssl/email',
]

def timestamp():
	return time.strftime('%Y-%m-%d %H:%M:%S')

def load_values():
	# load UCR variables
	ucr.load()
	values = dict([ (ikey, ucr[ikey]) for ikey in UCR_VARIABLES ])

	# net
	net_values = {}
	link_locals = []
	for k, v in ucr.items():
		match = RE_IFACE.match(k)
		if match:
			iface, attr, ipv6 = match.groups()
			if attr == 'address' and v.startswith('169.254.'):
				link_locals.append(iface)
			net_values[k] = v
	for k, v in net_values.items():
		if 'ipv6' not in k:
			if any(link_local in k for link_local in link_locals):
				net_values.pop(k)
	for link_local in link_locals:
		net_values['interfaces/%s/type' % link_local] = 'dhcp'
	values.update(net_values)

	# see whether the system has been joined or not
	values['joined'] = os.path.exists('/var/univention-join/joined')

	# root password
	values['root_password'] = ''

	# get timezone
	if os.path.exists('/etc/timezone'):
		f=open('/etc/timezone')
		values['timezone']=f.readline().strip()
		f.close()
	else:
		values['timezone']=''

#	if values['locale']:
#		locales = values['locale'].split()
#		pattern = re.compile(r'^(?:%s)$' % ('|'.join(map(lambda s: re.escape(s.replace(':UTF-8', '')), locales)))) # fallbacklocale
#		pattern = re.compile(r'^(?:%s)$' % ('|'.join(map(lambda s: re.escape(s[:2]), locales)))) # langcode
#		values['locale'] = list(filter(lambda d: d['id'] in locales, get_available_locales(pattern, 'langcode')))
#	else:
#		values['locale'] = []

	# get installed components
	values['components'] = ' '.join([icomp['id'] for icomp in get_installed_components()])

	return values


def _xkeymap(keymap):
	'''Determine the x-keymap which belongs to 'keymap' by
	parsing /lib/univention-installer/locale/all-kmaps'''
	
	xkeymap = {'layout' : '', 'variant' : ''}
	fp = open('/lib/univention-installer/locale/all-kmaps', 'r')
	for line in fp:
		line_split = line.strip('\n').split(':')
		if line_split[1] == keymap:
			xkeymap['layout'] = line_split[2].split(' ')[0]
			if len(line_split[2].split(' ')) == 2:
				xkeymap['variant'] = line_split[2].split(' ')[1]
			break
	fp.close()
	return xkeymap


def pre_save(newValues, oldValues):
	'''Modify the final dict before saving it to the profile file.'''

	# add broadcast addresses for ipv4 addresses using the ipaddr library
	for ikey, ival in copy.copy( newValues ).iteritems():
		m = RE_IPV4_DEVICE.match(ikey)
		if m:
			vals = m.groupdict()
			if vals['type'] == 'address' or vals['type'] == 'netmask':
				# new value might already exist
				broadcastKey = 'interfaces/%(device)s/broadcast' % vals
				networkKey = 'interfaces/%(device)s/network' % vals
				maskKey = 'interfaces/%(device)s/netmask' % vals
				addressKey = 'interfaces/%(device)s/address' % vals

				# try to compute the broadcast address
				address = newValues.get(addressKey, oldValues.get(addressKey, ''))
				mask = newValues.get(maskKey, oldValues.get(maskKey, ''))
				broadcast = get_broadcast(address, mask)
				network = get_network(address, mask)
				if broadcast:
					# we could compute a broadcast address
					newValues[broadcastKey] = broadcast
				if network:
					# we could compute a network address
					newValues[networkKey] = network

	# use new system role (or as fallback the current system role)
	role = newValues.get('server/role', ucr.get('server/role'))

	# add lists with all packages that should be removed/installed on the system
	if 'components' in newValues:
		regSpaces = re.compile(r'\s+')
		selectedComponents = set(regSpaces.split(newValues.get('components', '')))
		currentComponents = set([icomp['id'] for icomp in get_installed_components()])
		allComponents = set([ icomp['id'] for icomp in get_components() ])

		# get all packages that shall be removed
		removeComponents = list(allComponents & (currentComponents - selectedComponents))
		newValues['packages_remove'] = ' '.join([ i.replace(':', ' ') for i in removeComponents ])

		allComponents = set([ icomp['id'] for icomp in get_components(role=role) ])

		# get all packages that shall be installed
		installComponents = list(allComponents & (selectedComponents - currentComponents))
		newValues['packages_install'] = ' '.join([ i.replace(':', ' ') for i in installComponents ])

#	if 'locale' in newValues:
#		# js returns locale as list
#		newValues['locale'] = ' '.join(newValues['locale'])

	if 'locale/keymap' in newValues:
		xkeymap = _xkeymap(newValues['locale/keymap'])
		if xkeymap:
			newValues['xorg/keyboard/options/XkbLayout'] = xkeymap['layout']
			newValues['xorg/keyboard/options/XkbVariant'] = xkeymap['variant']


def write_profile(values):
	cache_file=open(PATH_PROFILE,"w+")
	for ikey, ival in values.iteritems():
		newVal = ival
		if ival is None:
			newVal = ''
		cache_file.write('%s="%s"\n\n' % (ikey, newVal))
	cache_file.close()

class ProgressState( object ):
	def __init__( self ):
		self.reset()

	def reset( self ):
		self.name = ''
		self.message = ''
		self._percentage = 0.0
		self.fraction = 0.0
		self.fractionName = ''
		self.steps = 1
		self.step = 0
		self.max = 100
		self.errors = []
		self.critical = False

	@property
	def percentage( self ):
		return ( self._percentage + self.fraction * ( self.step / float( self.steps ) ) ) / self.max * 100

	def __eq__( self, other ):
		return self.name == other.name and self.message == other.message and self.percentage == other.percentage and self.fraction == other.fraction and self.steps == other.steps and self.step == other.step and self.errors == other.errors and self.critical == other.critical

	def __ne__( self, other ):
		return not self.__eq__( other )

	def __nonzero__( self ):
		return bool( self.name or self.message or self.percentage or self._join_error or self._misc_error )

class ProgressParser( object ):
	# regular expressions
	NAME = re.compile( '^__NAME__: *(?P<key>[^ ]*) (?P<name>.*)\n$' )
	MSG = re.compile( '^__MSG__: *(?P<message>.*)\n$' )
	STEPS = re.compile( '^__STEPS__: *(?P<steps>.*)\n$' )
	STEP = re.compile( '^__STEP__: *(?P<step>.*)\n$' )
	JOINERROR = re.compile( '^__JOINERR__: *(?P<error_message>.*)\n$' )
	ERROR = re.compile( '^__ERR__: *(?P<error_message>.*)\n$' )

	# fractions of setup scripts
	FRACTIONS = {
		'basis/12domainname'	:  5,
		'basis/14ldap_basis'	: 10,
		'net/10interfaces'	:  5,
		'net/11ipv6interfaces'	:  5,
		'software/10software'	: 50,
		}

	# current status
	def __init__( self ):
		self.current = ProgressState()
		self.old = ProgressState()
		self.reset()

	def reset( self ):
		self.current.reset()
		self.old.reset()
		self.fractions = copy.copy( ProgressParser.FRACTIONS )
		self.calculateFractions()

	def calculateFractions( self ):
		MODULE.info( 'Calculating maximum value for fractions ...' )
		for category in filter( lambda x: os.path.isdir( os.path.join( PATH_SETUP_SCRIPTS, x ) ), os.listdir( PATH_SETUP_SCRIPTS ) ):
			cat_path = os.path.join( PATH_SETUP_SCRIPTS, category )
			for script in filter( lambda x: os.path.isfile( os.path.join( cat_path, x ) ), os.listdir( cat_path ) ):
				name = '%s/%s' % ( category, script )
				if not name in self.fractions:
					self.fractions[ name ] = 1

		self.current.max = sum( self.fractions.values() )
		MODULE.info( 'Calculated a maximum value of %d' % self.current.max )

	@property
	def changed( self ):
		if self.current != self.old:
			MODULE.info( 'Progress state has changed!' )
			self.old = copy.copy( self.current )
			return True
		return False

	def parse( self, line ):
		# start new component name
		match = ProgressParser.NAME.match( line )
		if match is not None:
			self.current.name, self.current.fractionName = match.groups()
			self.current.message = ''
			self.current._percentage += self.current.fraction
			self.current.fraction = self.fractions.get( self.current.name, 1.0 )
			self.current.step = 0 # reset current step
			self.current.steps = 1
			return True

		# new status message
		match = ProgressParser.MSG.match( line )
		if match is not None:
			self.current.message = match.groups()[ 0 ]
			return True

		# number of steps
		match = ProgressParser.STEPS.match( line )
		if match is not None:
			try:
				self.current.steps = int( match.groups()[ 0 ] )
				self.current.step = 0
				return True
			except ValueError:
				pass

		# current step
		match = ProgressParser.STEP.match( line )
		if match is not None:
			try:
				self.current.step = int( match.groups()[ 0 ] )
				if self.current.step > self.current.steps:
					self.current.step = self.current.steps
				return True
			except ValueError:
				pass

		# error message: why did the join fail?
		match = ProgressParser.JOINERROR.match( line )
		if match is not None:
			error = '%s: %s' % (self.current.fractionName, match.groups()[ 0 ])
			self.current.errors.append( error )
			self.current.critical = True
			return True

		# error message: why did the script fail?
		match = ProgressParser.ERROR.match( line )
		if match is not None:
			error = '%s: %s' % (self.current.fractionName, match.groups()[ 0 ])
			self.current.errors.append( error )
			return True

		return False

def run_scripts( progressParser, restartServer = False ):
	# write header before executing scripts
	f = open(LOG_FILE, 'a')
	f.write('\n\n=== RUNNING SETUP SCRIPTS (%s) ===\n\n' % timestamp())
	f.flush()

	# make sure that UMC servers and apache will not be restartet
	subprocess.call( CMD_DISABLE_EXEC, stdout = f, stderr = f )

	for root, dirs, files in os.walk(PATH_SETUP_SCRIPTS): 
		# ignore the root
		if root == PATH_SETUP_SCRIPTS:
			continue

		# execute all scripts in subdirectories
		files.sort()
		for ifile in files:
			# get the full script path
			ipath = os.path.join(root, ifile)

			# launch script
			pipe = subprocess.Popen( ipath, stdout = subprocess.PIPE, stderr = f ).stdout
			while True:
				line = pipe.readline()
				if not line:
					break
				progressParser.parse( line )
				f.write( line )

	# enable execution of servers again
	subprocess.call(CMD_ENABLE_EXEC, stdout=f, stderr=f)

	if restartServer:
		f.write('=== Restart of UMC server and web server (%s) ===\n' % timestamp())
		f.flush()
		subprocess.call(['/etc/init.d/univention-management-console-server', 'restart'], stdout=f, stderr=f)
		subprocess.call(['/etc/init.d/univention-management-console-web-server', 'restart'], stdout=f, stderr=f)

	f.write('\n=== DONE (%s) ===\n\n' % timestamp())
	f.close()

def run_joinscript( progressParser, _username, password ):
	# write header before executing join script
	f = open(LOG_FILE, 'a')
	f.write('\n\n=== RUNNING SETUP JOIN SCRIPT (%s) ===\n\n' % timestamp())
	f.flush()

	progressParser.fractions[ 'setup-join.sh' ] = 50
	progressParser.current.max = sum( progressParser.fractions.values() )
	def runit( command ):
		pipe = subprocess.Popen( command, stdout = subprocess.PIPE, stderr = f ).stdout
		while True:
			line = pipe.readline()
			if not line:
				break
			progressParser.parse( line )
			f.write( line )

	cmd = [ PATH_JOIN_SCRIPT ]
	if _username and password:
		# write password file
		fp = open(PATH_PASSWORD_FILE, 'w')
		fp.write('%s' % password)
		fp.close()
		os.chmod(PATH_PASSWORD_FILE, 0600)

		# sanitize username
		reg = re.compile('[^ a-zA-Z_1-9-]')
		username = reg.sub('_', _username)

		# run join scripts
		runit( cmd + [ '--dcaccount', username, '--password_file', PATH_PASSWORD_FILE ] )

		# remove password file
		os.remove(PATH_PASSWORD_FILE)
	else:
		# run join scripts
		runit( cmd )

	f.write('\n=== DONE (%s) ===\n\n' % timestamp())
	f.close()

def cleanup():
	# write header before executing scripts
	f = open(LOG_FILE, 'a')
	f.write('\n\n=== Cleanup (%s) ===\n\n' % timestamp())
	f.flush()

	ucr = univention.config_registry.ConfigRegistry()
	ucr.load()

	# The browser was only started, if system/setup/boot/start is true
	if ucr.is_true('system/setup/boot/start', False):
		MODULE.info('Appliance mode: try to shut down the browser')
		try:
			fpid = open(PATH_BROWSER_PID)
			strpid = fpid.readline().strip()
			pid = int(strpid)
			p = psutil.Process(pid)
			p.kill()
		except IOError:
			MODULE.warn('cannot open browser PID file: %s' % PATH_BROWSER_PID)
		except ValueError:
			MODULE.error('browser PID is not a number: "%s"' % strpid)
		except psutil.NoSuchProcess:
			MODULE.error('cannot kill process with PID: %s' % pid)

		# Maybe the system-setup CMD tool was started
		for p in psutil.process_iter():
			if p.name == 'python2.6' and '/usr/share/univention-system-setup/univention-system-setup' in p.cmdline:
				p.kill()

	# unset the temporary interface if set
	for var in ucr.keys():
		if RE_IPV4_TYPE.match(var) and ucr.get(var) == 'appliance-mode-temporary':
			f.write('unset %s' % var)
			keys = [var]
			for k in ['netmask', 'address', 'broadcast', 'network']:
				keys.append(var.replace('/type', '/%s' % k))
			univention.config_registry.handler_unset(keys)
			# Shut down temporary interface
			subprocess.call(['ifconfig', var.split('/')[1].replace('_', ':'), 'down'])

	# force a restart of UMC servers and apache
	subprocess.call( CMD_DISABLE_EXEC, stdout = f, stderr = f )
	subprocess.call( CMD_ENABLE_EXEC_WITH_RESTART, stdout = f, stderr = f )

	f.write('\n=== DONE (%s) ===\n\n' % timestamp())
	f.flush()
	f.close()

	return True

def detect_interfaces():
	"""
	Function to detect network interfaces in local sysfs.
	The loopback interface "lo" will be filtered out.
	Returns a list of dicts with the entries 'name' and 'mac'.
	"""
	interfaces = []

	dirnames = os.listdir(PATH_SYS_CLASS_NET)
	for dirname in dirnames:
		if os.path.isdir( os.path.join(PATH_SYS_CLASS_NET, dirname) ) and dirname.startswith('eth'):
			idev = { 'name': dirname }
			# try to read mac address of interface
			try:
				idev['mac'] = open(os.path.join(PATH_SYS_CLASS_NET, dirname, 'address'),'r').read().strip()
			except:
				pass
			interfaces.append(idev)

	return interfaces

def get_broadcast(ip, netmask):
	try:
		ip = ipaddr.IPv4Network('%s/%s' % ( ip, netmask ) )
		return ip.broadcast
	except ValueError:
		pass
	return None

def get_network(ip, netmask):
	try:
		ip = ipaddr.IPv4Network('%s/%s' % ( ip, netmask ) )
		return ip.network
	except ValueError:
		pass
	return None

def dhclient(interface, timeout=None):
	"""
	perform DHCP request for specified interface. If succesful, returns a dict
	similar to the following:
	{
		'address': '10.200.26.51',
		'broadcast': '10.200.26.255',
		'domainname': 'univention.qa',
		'gateway': '',
		'nameserver_1': '10.200.26.27',
		'nameserver_2': '',
		'nameserver_3': '',
		'netmask': '255.255.255.0'
	}
	"""
	tempfilename = tempfile.mkstemp( '.out', 'dhclient.', '/tmp' )[1]
	pidfilename = tempfile.mkstemp( '.pid', 'dhclient.', '/tmp' )[1]
	cmd = ('/sbin/dhclient',
			'-1',
			'-lf', '/tmp/dhclient.leases',
			'-pf', pidfilename,
			'-sf', '/lib/univention-installer/dhclient-script-wrapper',
			'-e', 'dhclientscript_outputfile=%s' % (tempfilename,),
			interface)
	p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

	# read from stderr until timeout, following recipe of subprocess.communicate()
	def _readerthread(fh, stringbufferlist):
		stringbufferlist.append(fh.read())

	stderr = []
	stderr_thread = threading.Thread(target=_readerthread, args=(p.stderr, stderr))
	stderr_thread.setDaemon(True)
	stderr_thread.start()
	stderr_thread.join(timeout)
	if stderr:
		stderr=stderr[0]
	# note: despite '-1' background dhclient never seems to terminate
	try:
		dhclientpid = int(open(pidfilename,'r').read().strip('\n\r\t '))
		os.kill(dhclientpid, 15)
		time.sleep(1.0) # sleep 1s
		os.kill(dhclientpid, 9)
	except:
		pass
	try:
		os.unlink(pidfilename)
	except:
		pass

	dhcp_dict={}
	with open(tempfilename) as file:
		for line in file.readlines():
			key, value = line.strip().split('=', 1)
			dhcp_dict[key]=value[1:-1]
	os.unlink(tempfilename)
	return dhcp_dict

def get_components(role=None):
	'''Returns a list of components that may be installed on the current system.'''

	# get all package sets that are available for the current system role
	if not role:
		role = ucr.get('server/role')

	# reload for correct locale
	imp.reload(package_list)
	pkglist = [ jpackage for icategory in package_list.PackageList 
			for jpackage in icategory['Packages']
			if 'all' in jpackage['Possible'] or role in jpackage['Possible'] ]

	# filter whitelisted packages
	whitelist = ucr.get('system/setup/packages/whitelist')
	if whitelist:
		whitelist = whitelist.split(' ')
		pkglist = [ipkg for ipkg in pkglist if all(jpkg in whitelist for jpkg in ipkg['Packages'])]

	# filter blacklisted packages
	blacklist = ucr.get('system/setup/packages/blacklist')
	if blacklist:
		blacklist = blacklist.split(' ')
		pkglist = [ipkg for ipkg in pkglist if not any(jpkg in blacklist for jpkg in ipkg['Packages'])]

	# generate a unique ID for each component
	for ipkg in pkglist:
		ipkg['Packages'].sort()
		ipkg['id'] = ':'.join(ipkg['Packages'])
		ipkg[ 'Description' ] = installer_i18n.translate( ipkg[ 'Description' ] )
		ipkg[ 'Name' ] = installer_i18n.translate( ipkg[ 'Name' ] )

	return pkglist

def get_installed_packages():
	'''Returns a list of all installed packages on the system.'''
	cache = apt.Cache()
	return [ p.name for p in cache if p.is_installed ]

def get_installed_components():
	'''Returns a list of components that are currently fully installed on the system.'''
	allPackages = set(get_installed_packages())
	allComponents = get_components()
	return [ icomp for icomp in allComponents if not len(set(icomp['Packages']) - allPackages) ]

# from univention-installer/installer/modules/70_net.py
def is_proxy(proxy):
	if proxy and proxy != 'http://' and proxy != 'https://':
		if not proxy.startswith('http://') and not proxy.startswith('https://'):
			return False
	return True

def is_ipaddr(addr):
	try:
		ipaddr.IPAddress(addr)
	except ValueError:
		return False
	return True

def is_ipv4addr(addr):
	try:
		ipaddr.IPv4Address(addr)
	except ValueError:
		return False
	return True

def is_ipv4netmask(addr_netmask):
	try:
		ipaddr.IPv4Network(addr_netmask)
	except (ValueError, ipaddr.NetmaskValueError, ipaddr.AddressValueError):
		return False
	return True

def is_ipv6addr(addr):
	try:
		ipaddr.IPv6Address(addr)
	except ValueError:
		return False
	return True

def is_ipv6netmask(addr_netmask):
	try:
		ipaddr.IPv6Network(addr_netmask)
	except (ValueError, ipaddr.NetmaskValueError, ipaddr.AddressValueError):
		return False
	return True

# from univention-installer/installer/objects.py
def is_hostname(hostname):
	if is_hostname.RE.match(hostname):
		return True
	return False
is_hostname.RE = re.compile("^[a-z]([a-z0-9-]*[a-z0-9])*$")

def is_domainname(domainname):
	if is_domainname.RE.match(domainname):
		return True
	return False
is_domainname.RE = re.compile("^([a-z0-9]([a-z0-9-]*[a-z0-9])*[.])*[a-z0-9]([a-z0-9-]*[a-z0-9])*$")

def is_windowsdomainname(domainname):
	if is_windowsdomainname.RE.match(domainname):
		return True
	return False
is_windowsdomainname.RE = re.compile("^([A-Z]([A-Z0-9-]*[A-Z0-9])*[.])*[A-Z]([A-Z0-9-]*[A-Z0-9])*$")

def is_domaincontroller(domaincontroller):
	if is_domaincontroller.RE.match(domaincontroller):
		return True
	return False
is_domaincontroller.RE = re.compile("^[a-zA-Z].*\..*$")

# new defined methods
def is_ascii(str):
	try:
		str.decode("ascii")
		return True
	except:
		return False

def get_available_locales(pattern, category='language_en'):
	'''Return a list of all available locales.'''
	try:
		fsupported = open('/usr/share/i18n/SUPPORTED')
		flanguages = open('/lib/univention-installer/locale/languagelist')
	except:
		MODULE.error( 'Cannot find locale data for languages in /lib/univention-installer/locale' )
		return

	# get all locales that are supported
	rsupported = csv.reader(fsupported, delimiter=' ')
	supportedLocales = { 'C': True }
	for ilocale in rsupported:
		# we only support UTF-8
		if ilocale[1] != 'UTF-8':
			continue

		# get the locale
		m = RE_LOCALE.match(ilocale[0])
		if m:
			supportedLocales[m.groups()[0]] = True

	category = {'langcode': 0, 'language_en': 1, 'language': 2, 'countrycode': 4, 'fallbacklocale': 5}.get(category, 1)

	# open all languages
	rlanguages = csv.reader(flanguages, delimiter=';')
	locales = []
	for ilang in rlanguages:
		if ilang[0].startswith('#'):
			continue

		if not pattern.match(ilang[category]):
			continue

		# each language might be spoken in several countries
		ipath = '/lib/univention-installer/locale/short-list/%s.short' % ilang[0]
		if os.path.exists(ipath):
			try:
				# open the short list with countries belonging to the language
				fshort = open(ipath)
				rshort = csv.reader(fshort, delimiter='\t')

				# create for each country a locale entry
				for jcountry in rshort:
					code = '%s_%s' % (ilang[0], jcountry[0])
					if code in supportedLocales:
						locales.append({
							'id': '%s.UTF-8:UTF-8' % code,
							'label': '%s (%s)' % (ilang[1], jcountry[2])
						})
				continue
			except Exception:
				pass

		# get the locale code
		code = ilang[0]
		if code.find('_') < 0 and code != 'C':
			# no underscore -> we need to build the locale ourself
			code = '%s_%s' % (ilang[0], ilang[4])

		# final entry
		if code in supportedLocales:
			locales.append({
				'id': '%s.UTF-8:UTF-8' % code,
				'label': ilang[1]
			})

	return locales

