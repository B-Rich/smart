# -*- coding: utf-8 -*-
#
# UCS Virtual Machine Manager Daemon
#  listener module
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
"""UVMM protocol."""
try:
	from cStringIO import StringIO
except ImportError:
	from StringIO import StringIO
try:
	import cPickle as pickle
except ImportError:
	import pickle
import struct
from helpers import TranslatableException, N_ as _

VERSION = (2, 0)
MAX_MSG_SIZE = 4096

class PacketError(TranslatableException):
	"""Packet framing error."""
	pass

class Packet(object):
	"""On-wire packet format."""
	def __init__(self, **kw):
		"""Create new packet."""
		self._default()
		for k, v in kw.items():
			if hasattr(self, k):
				setattr(self, k, v)
			else:
				raise AttributeError("Packet '%s' has no attribute '%s'" % (str(self.__class__)[len(self.__class__.__module__)+1:], k))
	def __str__(self):
		res = ['Packet:']
		for attr in dir(self):
			if not attr.startswith('_') and attr not in ('pack','parse'):
				res.append(' %s: %s' % (attr, str(getattr(self, attr))))
		return '\n'.join(res)
	def pack(self):
		"""Pack data for transfer."""
		s = StringIO()
		p = pickle.Pickler(s)
		p.dump(self)
		data = s.getvalue()
		return struct.pack('!HHI', VERSION[0], VERSION[1], len(data)) + data
	@staticmethod
	def parse(buffer, offset=0):
		"""Unpack packet from data."""
		FORMAT = '!HHI'
		SIZE = struct.calcsize(FORMAT)
		if len(buffer) < offset + SIZE:
			return None
		(v1, v2, length,) = struct.unpack(FORMAT, buffer[offset:offset + SIZE])
		if VERSION[0] != v1 or VERSION[1] > v2:
			raise PacketError(_('Incompatible version: %(major)d.%(minor)d'), major=v1, minor=v2)
		if len(buffer) < offset + SIZE + length:
			return None
		(data,) = struct.unpack('%ds' % length, buffer[offset + SIZE:offset + SIZE + length])
		try:
			s = StringIO(data)
			p = pickle.Unpickler(s)
			packet = p.load()
		except Exception, e:
			raise PacketError(_('Not a valid Packet: %(msg)s'), msg=str(e))
		if not isinstance(packet, Packet):
			raise PacketError(_('Not a Packet: %(type)s'), type=type(packet))
		else:
			return (SIZE + length, packet)

class Request(Packet):
	"""Super class of all requests to UVMM daemon."""
	def _default(self):
		"""Set default values. Called from __init__(self)."""
		self.command = None

class Request_NODE_ADD(Request):
	"""Add node to watch list."""
	def _default(self):
		self.command = 'NODE_ADD'
		self.uri = None # xen:/// xen+unix:/// xen+ssh://root@bs22.pmhahn22.qa/ qemu:///system qemu+unix:///system qemu+ssh://root@bs22.pmhahn22.qa/system
class Request_NODE_REMOVE(Request):
	"""Remove node to watch list."""
	def _default(self):
		self.command = 'NODE_REMOVE'
		self.uri = None # xen:/// xen+unix:/// xen+ssh://root@bs22.pmhahn22.qa/ qemu:///system qemu+unix:///system qemu+ssh://root@bs22.pmhahn22.qa/system
class Request_NODE_QUERY(Request):
	"""Query node on watch list."""
	def _default(self):
		self.command = 'NODE_QUERY'
		self.uri = None # xen:/// xen+unix:/// xen+ssh://root@bs22.pmhahn22.qa/ qemu:///system qemu+unix:///system qemu+ssh://root@bs22.pmhahn22.qa/system
class Request_NODE_FREQUENCY(Request):
	"""Set query frequency for nodes on watch list."""
	def _default(self):
		self.command = 'NODE_FREQUENCY'
		self.hz = None # 1/ms
		self.uri = None # xen:/// xen+unix:/// xen+ssh://root@bs22.pmhahn22.qa/ qemu:///system qemu+unix:///system qemu+ssh://root@bs22.pmhahn22.qa/system
class Request_NODE_LIST(Request):
	"""Query for list of watched nodes in specific group."""
	def _default(self):
		self.command = 'NODE_LIST'
		self.group = None
		self.pattern = '*' # wildcard pattern
class Request_GROUP_LIST(Request):
	"""Query for list of known groups."""
	def _default(self):
		self.command = 'GROUP_LIST'
class Request_BYE(Request):
	"""Disconnect client."""
	def _default(self):
		self.command = 'BYE'
class Request_DOMAIN_LIST(Request):
	"""List domains."""
	def _default(self):
		self.command = 'DOMAIN_LIST'
		self.uri = None
		self.pattern = '*' # wildcard pattern
class Request_DOMAIN_INFO(Request):
	"""Detailed information of a domain."""
	def _default(self):
		self.command = 'DOMAIN_INFO'
		self.uri = None
		self.domain = None
class Request_DOMAIN_DEFINE(Request):
	"""Define new or replace old domain."""
	def _default(self):
		self.command = 'DOMAIN_DEFINE'
		self.uri = None
		self.domain = None
class Request_DOMAIN_STATE(Request):
	"""Change running state of defined domain."""
	def _default(self):
		self.command = 'DOMAIN_STATE'
		self.uri = None
		self.domain = None
		self.state = None # RUN PAUSE SHUTDOWN RESTART
class Request_DOMAIN_SAVE(Request):
	"""Save defined domain."""
	def _default(self):
		self.command = 'DOMAIN_SAVE'
		self.uri = None
		self.domain = None
		self.statefile = None
class Request_DOMAIN_RESTORE(Request):
	"""Resume defined domain."""
	def _default(self):
		self.command = 'DOMAIN_RESTORE'
		self.uri = None
		self.domain = None
		self.statefile = None
class Request_DOMAIN_UNDEFINE(Request):
	"""Remove domain."""
	def _default(self):
		self.command = 'DOMAIN_UNDEFINE'
		self.uri = None
		self.domain = None
		self.volumes = []
class Request_DOMAIN_MIGRATE(Request):
	"""Migrate domain."""
	def _default(self):
		self.command = 'DOMAIN_MIGRATE'
		self.uri = None
		self.domain = None
		self.target_uri = None

class Request_DOMAIN_SNAPSHOT_CREATE(Request):
	"""Create new snapshot of domain."""
	def _default(self):
		self.command = 'DOMAIN_SNAPSHOT_CREATE'
		self.uri = None
		self.domain = None
		self.snapshot = None

class Request_DOMAIN_SNAPSHOT_REVERT(Request):
	"""Revert to snapshot of domain."""
	def _default(self):
		self.command = 'DOMAIN_SNAPSHOT_REVERT'
		self.uri = None
		self.domain = None
		self.snapshot = None

class Request_DOMAIN_SNAPSHOT_DELETE(Request):
	"""Delete snapshot of domain."""
	def _default(self):
		self.command = 'DOMAIN_SNAPSHOT_DELETE'
		self.uri = None
		self.domain = None
		self.snapshot = None

class Request_DOMAIN_UPDATE(Request):
	"""Trigger update of domain."""
	def _default(self):
		self.command = 'DOMAIN_UPDATE'
		self.domain = None

class Request_DOMAIN_CLONE(Request):
	"""Clone a domain."""
	def _default(self):
		self.command = 'DOMAIN_CLONE'
		self.uri = None
		self.domain = None
		self.name = None
		self.subst = {} # key -> value

class Request_STORAGE_POOLS(Request):
	"""List all pools."""
	def _default(self):
		self.command = 'STORAGE_POOLS'
		self.uri = None

class Request_STORAGE_VOLUMES(Request):
	"""List all volumes in pool."""
	def _default(self):
		self.command = 'STORAGE_VOLUMES'
		self.uri = None
		self.pool = None
		self.type = None # DISK CDROM

class Request_STORAGE_VOLUMES_DESTROY(Request):
	"""Destroy all given volumes in a pool."""
	def _default(self):
		self.command = 'STORAGE_VOLUMES_DESTROY'
		self.uri = None
		self.volumes = None

class Request_STORAGE_VOLUME_USEDBY(Request):
	"""Return list of domains using the given iamge."""
	def _default(self):
		self.command = 'STORAGE_VOLUME_USEDBY'
		self.volume = None

class Request_STORAGE_DEFINE(Request):
	"""Create new volume in pool."""
	def _default(self):
		self.command = 'STORAGE_DEFINE'
		self.uri = None
		self.pool = None
		self.name = None
		self.size = 0 # bytes

class Request_AUTHENTICATION(Request):
	"""Provide authentication data."""
	def _default(self):
		self.command = 'AUTHENTICATION'
		self.response = [] # (data, PAM.PAM_{SUCCESS|*_ERR|...})
class Response(Packet):
	"""Super class of all responses from UVMM daemon."""
	def _default(self):
		self.status = None
class Response_ERROR(Response):
	def _default(self):
		self.status = 'ERROR'
		self.translatable_text = None
		self.values = {}
	@property
	def msg(self):
		return self.translatable_text % self.values
class Response_OK(Response):
	def _default(self):
		self.status = 'OK'
class Response_DUMP(Response_OK):
	def _default(self):
		self.status = 'OK'
		self.data = {}
		self.messages = None

class Response_AUTHENTICATION(Response):
	"""Authentication required, contains PAM challanges."""
	def _default(self):
		self.status = 'AUTHENTICATION'
		self.challenge = [] # (PAM.PAM_{PROMPT_ECHO_{ON|OFF}|ERROR_MSG|PROMPT_TEXT}, query)
class Data_StoragePool(object):
	"""Container for storage pool statistics."""
	def __init__(self):
		self.uuid = None
		self.name = None
		self.capacity = None
		self.available = None
		self.path = None
		self.active = None # True False
		self.type = None # logical
class Data_Domain(object):
	"""Container for domain statistics."""
	def __init__(self):
		self.uuid = None
		self.name = None
		self.domain_type = None # xen, qemu, kvm
		self.arch = 'i686' # i686, x86_64
		self.os_type = None # linux(=Xen-PV), hvm(=Xen-FV)
		self.rtc_offset = None

		# Xen-PV
		self.kernel = None
		self.cmdline = None
		self.initrd = None
		self.bootloader = None
		self.bootloader_args = None

		# Xen-HVM, Qemu-HVM, Kvm-HVM
		self.boot = [] # (fd|hd|cdrom|network)+

		self.state = 0
		self.maxMem = 0L
		self.curMem = 0L
		self.vcpus = 1
		self.cputime = [0.0, 0.0, 0.0] # percentage in last 10s 60s 5m
		self.interfaces = [] # node.Interface
		self.disks = [] # node.Disk
		self.graphics = [] # node.Graphics
		self.annotations = {}
		self.snapshots = None # ID: Data_Snapshot
		self.suspended = None # True|False
		self.available = None # None: not set, (True|False) -> node availability
class Data_Node(object):
	"""Container for node statistics."""
	def __init__(self):
		self.name = None
		self.uri = None
		self.phyMem = None
		self.curMem = None
		self.maxMem = None
		self.cpu_usage = None
		self.cpus = None
		self.cores = (None, None, None, None)
		self.domains = [] # Data_Domain
		self.capabilities = [] # node.DomainTemplate
		self.last_try = 0.0
		self.last_update = 0.0
		self.supports_suspend = False
		self.supports_snapshot = False
class Data_Pool(object):
	"""Container for storage pool statistics."""
	def __init__(self):
		self.name = None
		self.uuid = None
		self.capacity = 0L
		self.available = 0L
		self.path = None # optional
		self.active = False
		self.type = None

class Data_Snapshot(object):
	"""Container for snapshot data."""
	def __init__(self):
		self.name = None
		self.ctime = 0 # UNIX time

def _map(dictionary, id=None, name=None):
	"""Map id to name or reverse using the dictionary."""
	if id is not None and id in dictionary:
		return dictionary[id]
	if name:
		for key, value in dictionary.items():
			if name == value:
				return key
	return ''

class Disk(object):
	'''Container for disk objects'''
	DEVICE_DISK = 'disk'
	DEVICE_CDROM = 'cdrom'
	DEVICE_FLOPPY = 'floppy'
	DEVICE_LUN = 'lun'

	TYPE_FILE = 'file'
	TYPE_BLOCK = 'block'
	TYPE_DIR = 'dir'
	TYPE_NETWORK = 'network'

	CACHE_DEFAULT = 'default'
	CACHE_NONE ='none' # off
	CACHE_WT ='writethrough'
	CACHE_WB ='writeback'
	CACHE_UNSAFE ='unsafe'
	CACHE_DIRECTSYNC ='directsync'

	def __init__(self):
		self.type = Disk.TYPE_FILE	# disk/@type
		self.device = Disk.DEVICE_DISK	# disk/@device
		self.driver = None	# disk/driver/@name
		self.driver_type = None	# disk/driver/@type
		self.driver_cache = Disk.CACHE_DEFAULT	# disk/driver/@cache
		self.source = ''	# disk/source/@file | disk/source/@dev | disk/source/@dir | disk/source/@protocol
		self.readonly = False	# disk/readonly
		self.target_dev = ''	# disk/target/@dev
		self.target_bus = None	# disk/target/@bus
		self.size = None # not defined
		self.pool = None

	def __str__(self):
		return 'Disk(device=%s, type=%s, driver=%s, source=%s, target=%s, size=%s)' % (self.device, self.type, self.driver, self.source, self.target_dev, self.size)

class Interface(object):
	'''Container for interface objects'''
	TYPE_BRIDGE ='bridge'
	TYPE_NETWORK ='network'
	TYPE_USER ='user'
	TYPE_ETHERNET ='ethernet'
	TYPE_DIRECT ='direct'

	def __init__(self):
		self.type = Interface.TYPE_BRIDGE
		self.mac_address = None
		self.source = None
		self.target = None
		self.script = None
		self.model = None

	def __str__(self):
		return 'Interface(type=%s, mac=%s, source=%s, target=%s, script=%s, model=%s)' % (self.type, self.mac_address, self.source, self.target, self.script, self.model)

class Graphic(object):
	'''Container for graphic objects'''
	TYPE_VNC ='vnc'
	TYPE_SDL ='sdl'
	TYPE_SPICE ='spice'
	TYPE_RDP ='rdp'
	TYPE_DESKTOP ='desktop'

	def __init__(self):
		self.type = Graphic.TYPE_VNC
		self.port = -1
		self.autoport = True
		self.keymap = 'de'
		self.listen = None
		self.passwd = None
		#self.passwdValidTo = None
		#self.socket = None
		# sdl | desktop:
		#self.display = None
		#self.xauth = None
		#self.fullscreen = None
		# spice:
		#self.channels = []
		# rdp:
		#self.replaceUser = None
		#self.multiUser = None

	def __str__(self):
		return 'Graphic(type=%s, port=%s, autoport=%s, keymap=%s, listen=%s, passwd=%s' % (self.type, self.port, self.autoport, self.keymap, self.listen, bool(self.passwd))

# TODO: this object definition is not complete!
class Network( object ):
	'''Container for Network objects.'''

	def __init__( self ):
		self.name = None
		self.uuid = None
		self.bridge = None


