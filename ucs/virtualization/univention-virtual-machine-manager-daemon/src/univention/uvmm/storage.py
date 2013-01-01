# -*- coding: utf-8 -*-
#
# UCS Virtual Machine Manager Daemon
#  storage handler
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
"""UVMM storage handler.

This module implements functions to handle storage on nodes. This is independent from the on-wire-format.
"""

import libvirt
import logging
from xml.dom.minidom import getDOMImplementation, parseString
from xml.parsers.expat import ExpatError
from helpers import TranslatableException, N_ as _, TimeoutError, timeout
from protocol import Disk, Data_Pool
import os.path
import univention.config_registry as ucr
import time
from xml.sax.saxutils import escape as xml_escape

configRegistry = ucr.ConfigRegistry()
configRegistry.load()

logger = logging.getLogger('uvmmd.storage')

class StorageError(TranslatableException):
	"""Error while handling storage."""
	pass

def create_storage_pool(conn, dir, pool_name='default'):
	"""Create directory pool."""
	# FIXME: support other types than dir
	xml = '''
	<pool type="dir">
		<name>%(pool)s</name>
		<target>
			<path>%(path)s</path>
		</target>
	</pool>
	''' % {
			'pool': xml_escape(pool_name),
			'path': xml_escape(dir),
			}
	try:
		p = conn.storagePoolDefineXML(xml, 0)
		p.setAutostart(True)
		p.create( 0 )
	except libvirt.libvirtError, e:
		logger.error(e)
		raise StorageError(_('Error creating storage pool "%(pool)s": %(error)s'), pool=pool_name, error=e.get_error_message())

def create_storage_volume(conn, domain, disk):
	"""Create disk for domain."""
	try:
		# BUG #19342: does not find volumes in sub-directories
		v = conn.storageVolLookupByPath(disk.source)
		logger.warning('Reusing existing volume "%s" for domain "%s"' % (disk.source, domain.name))
		return v
	except libvirt.libvirtError, e:
		logger.info( 'create_storage_volume: libvirt error (%d): %s' % ( e.get_error_code(), str( e ) ) )
		if not e.get_error_code() in ( libvirt.VIR_ERR_INVALID_STORAGE_VOL, libvirt.VIR_ERR_NO_STORAGE_VOL ):
			raise StorageError(_('Error locating storage volume "%(volume)s" for "%(domain)s": %(error)s'), volume=disk.source, domain=domain.name, error=e.get_error_message())

	pool = (0, None)
	for pool_name in conn.listStoragePools() + conn.listDefinedStoragePools():
		try:
			p = conn.storagePoolLookupByName(pool_name)
			xml = p.XMLDesc(0)
			doc = parseString(xml)
			path = doc.getElementsByTagName('path')[0].firstChild.nodeValue
			if '/' != path[-1]:
				path += '/'
			if disk.source.startswith(path):
				l = len(path)
				if l > pool[0]:
					pool = (l, p)
		except libvirt.libvirtError, e:
			if e.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_POOL:
				logger.error(e)
				raise StorageError(_('Error locating storage pool "%(pool)s" for "%(domain)s": %(error)s'), pool=pool_name, domain=domain.name, error=e.get_error_message())
		except IndexError, e:
			pass
	if not pool[0]:
		logger.warning('Volume "%(volume)s" for "%(domain)s" in not located in any storage pool.' % {'volume': disk.source, 'domain': domain.name})
		return None # FIXME
		#raise StorageError(_('Volume "%(volume)s" for "%(domain)s" in not located in any storage pool.'), volume=disk.source, domain=domain.name)
		#create_storage_pool(conn, path.dirname(disk.source))
	l, p = pool
	try:
		p.refresh(0)
		v = p.storageVolLookupByName(disk.source[l:])
		logger.warning('Reusing existing volume "%s" for domain "%s"' % (disk.source, domain.name))
		return v
	except libvirt.libvirtError, e:
		logger.info( 'create_storage_volume: libvirt error (%d): %s' % ( e.get_error_code(), str( e ) ) )
		if not e.get_error_code() in (libvirt.VIR_ERR_INVALID_STORAGE_VOL, libvirt.VIR_ERR_NO_STORAGE_VOL):
			raise StorageError(_('Error locating storage volume "%(volume)s" for "%(domain)s": %(error)s'), volume=disk.source, domain=domain.name, error=e.get_error_message())

	if hasattr(disk, 'size') and disk.size:
		size = disk.size
	else:
		size = 8 << 30 # GiB

	values = {
			'name': xml_escape(os.path.basename(disk.source)),
			'size': size,
			}

	# determin pool type
	xml = p.XMLDesc(0)
	doc = parseString(xml)
	pool_type = doc.firstChild.getAttribute('type')
	if pool_type in ('dir', 'fs', 'netfs'):
		if hasattr(disk, 'driver_type') and disk.driver_type not in (None, 'iso', 'aio'):
			values['type'] = xml_escape(disk.driver_type)
		else:
			values['type'] = 'raw'
		# permissions
		permissions = [(access, configRegistry.get('uvmm/volume/permissions/%s' % access, None))
				for access in ('owner', 'group', 'mode')]
		permissions = ['\t\t\t<%(tag)s>%(value)s</%(tag)s>' % {
			'tag': xml_escape(key),
			'value': xml_escape(value),
			} for (key, value) in permissions if value and value.isdigit()]
		if permissions:
			permissions = '\t\t<permissions>\n%s\n\t\t</permissions>' % ('\n'.join(permissions),)
		else:
			permissions = ''

		template = '''
<volume>
	<name>%%(name)s</name>
	<allocation>0</allocation>
	<capacity>%%(size)ld</capacity>
	<target>
		<format type="%%(type)s"/>
		%s
	</target>
</volume>
		''' % permissions
	elif pool_type == 'logical':
		template = '''
<volume>
	<name>%(name)s</name>
	<capacity>%(size)ld</capacity>
</volume>
		'''
	else:
		logger.error("Unsupported storage-pool-type %s for %s:%s" % (pool_type, domain.name, disk.source))
		raise StorageError(_('Unsupported storage-pool-type "%(pool_type)s" for "%(domain)s"'), pool_type=pool_type, domain=domain.name)

	xml = template % values
	try:
		logger.debug('XML DUMP: %s' % xml)
		v = p.createXML(xml, 0)
		logger.info('New disk "%s" for "%s"(%s) defined.' % (v.path(), domain.name, domain.uuid))
		return v
	except libvirt.libvirtError, e:
		if e.get_error_code() in (libvirt.VIR_ERR_NO_STORAGE_VOL,):
			logger.warning('Reusing existing volume "%s" for domain "%s"' % (disk.source, domain.name))
			return None
		logger.error(e)
		raise StorageError(_('Error creating storage volume "%(name)s" for "%(domain)s": %(error)s'), name=disk.source, domain=domain.name, error=e.get_error_message())

def get_storage_volumes(node, pool_name, type=None):
	"""Get 'protocol.Disk' instance for all Storage Volumes in named pool of given type."""
	if node.conn is None:
		raise StorageError(_('Error listing volumes at "%(uri)s": %(error)s'), uri=node.uri, error='no connection')
	volumes = []
	try:
		pool = timeout(node.conn.storagePoolLookupByName)(pool_name)
		pool.refresh(0)
	except TimeoutError, e:
		logger.warning('libvirt connection "%s" timeout: %s', node.pd.uri, e)
		node.pd.last_try = time.time()
		return volumes
	except libvirt.libvirtError, e:
		logger.error(e)
		raise StorageError(_('Error listing volumes at "%(uri)s": %(error)s'), uri=node.pd.uri, error=e.get_error_message())
	for name in pool.listVolumes():
		disk = Disk()
		vol = pool.storageVolLookupByName( name )
		xml = vol.XMLDesc( 0 )
		try:
			doc = parseString(xml)
		except ExpatError:
			continue
		disk.size = int( doc.getElementsByTagName( 'capacity' )[ 0 ].firstChild.nodeValue )
		target = doc.getElementsByTagName( 'target' )[ 0 ]
		disk.source = target.getElementsByTagName( 'path' )[ 0 ].firstChild.nodeValue
		try: # Only directory-based pools have /volume/format/@type
			disk.driver_type = target.getElementsByTagName('format')[0].getAttribute('type')
			disk.type = Disk.TYPE_FILE
			if disk.driver_type == 'iso':
				disk.device = Disk.DEVICE_CDROM
			else:
				disk.device = Disk.DEVICE_DISK
		except IndexError, e:
			disk.type = Disk.TYPE_BLOCK
			disk.device = Disk.DEVICE_DISK
			disk.driver_type = None # raw
		if not type or disk.device == type:
			volumes.append( disk )

	return volumes

def get_all_storage_volumes(domain):
	"""Retrieve all referenced storage volumes."""
	volumes = []
	try:
		doc = parseString(domain.XMLDesc(0))
	except ExpatError:
		return volumes
	devices = doc.getElementsByTagName('devices')
	try:
		devices = devices[0]
	except IndexError:
		return volumes
	disks = devices.getElementsByTagName('disk')
	for disk in disks:
		source = disk.getElementsByTagName('source')
		try:
			source = source[0]
			vol = source.getAttribute('file')
			if vol:
				volumes.append(vol)
		except LookupError:
			continue
	return volumes

def destroy_storage_volumes(conn, volumes, ignore_error=False):
	"""Destroy volumes."""
	# 1. translate names into references
	refs = []
	for name in volumes:
		try:
			ref = conn.storageVolLookupByPath(name)
			refs.append(ref)
		except libvirt.libvirtError, e:
			if ignore_error:
				logger.warning("Error translating '%s' to volume: %s" % (name, e.get_error_message()))
			else:
				logger.error("Error translating '%s' to volume: %s. Ignored." % (name, e.get_error_message()))
				raise
	# 2. delete them all
	for volume in refs:
		try:
			volume.delete(0)
		except libvirt.libvirtError, e:
			if ignore_error:
				logger.warning("Error deleting volume: %s" % e.get_error_message())
			else:
				logger.error("Error deleting volume: %s. Ignored." % e.get_error_message())
				raise

def __get_storage_pool_info(conn, name):
	"""Get 'protocol.Data_Pool' instance for named pool."""
	p = conn.storagePoolLookupByName( name )
	xml = p.XMLDesc( 0 )
	doc = parseString( xml )
	pool = Data_Pool()
	pool.name = name
	pool.uuid = doc.getElementsByTagName( 'uuid' )[ 0 ].firstChild.nodeValue
	pool.capacity = int( doc.getElementsByTagName( 'capacity' )[ 0 ].firstChild.nodeValue )
	pool.available = int( doc.getElementsByTagName( 'available' )[ 0 ].firstChild.nodeValue )
	pool.path = doc.getElementsByTagName( 'path' )[ 0 ].firstChild.nodeValue
	pool.active = p.isActive() == 1
	pool.type = doc.firstChild.getAttribute('type') # pool/@type
	return pool

def storage_pools(node):
	"""Get 'protocol.Data_Pool' instance for all pools."""
	if node.conn is None:
		raise StorageError(_('Error listing pools at "%(uri)s": %(error)s'), uri=node.pd.uri, error='no connection')
	try:
		pools = []
		for name in timeout(node.conn.listStoragePools)() + timeout(node.conn.listDefinedStoragePools)():
			pool = __get_storage_pool_info(node.conn, name)
			pools.append( pool )
		return pools
	except TimeoutError, e:
		logger.warning('libvirt connection "%s" timeout: %s', node.pd.uri, e)
		node.pd.last_try = time.time()
		return pools
	except libvirt.libvirtError, e:
		logger.error(e)
		raise StorageError(_('Error listing pools at "%(uri)s": %(error)s'), uri=node.uri, error=e.get_error_message())


def storage_volume_usedby( nodes, volume_path, ignore_cdrom = True ):
	"""Returns a list of tuples ( <node URI>, <domain UUID> ) of domains
	that use the given volume"""
	used_by = []
	for uir, node in nodes.items():
		for uuid, domain in node.domains.items():
			for device in domain.pd.disks:
				if ignore_cdrom and device.device == Disk.DEVICE_CDROM:
					continue
				if device.source == volume_path:
					used_by.append( ( node.pd.uri, domain.pd.uuid ) )

	return used_by
