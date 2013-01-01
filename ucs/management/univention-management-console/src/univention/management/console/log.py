# -*- coding: utf-8 -*-
#
# Univention Management Console
#  logging module for UMC
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

"""
Logging
=======

This module provides a wrapper for univention.debug
"""

import univention.debug as ud
import logging
import grp
import os

# no exceptions from logging
# otherwise shutdown the server will raise an exception that the logging stream could not be closed
logging.raiseExceptions = 0

#: list of available debugging components
COMPONENTS = ( ud.MAIN, ud.NETWORK, ud.SSL, ud.ADMIN, ud.MODULE, ud.AUTH, ud.PARSER, ud.LOCALE, ud.ACL, ud.RESOURCES, ud.PROTOCOL )

def log_init( filename, log_level = 2 ):
	"""Initializes Univention debug.

	:param str filename: The filename just needs to be a relative name. The directory /var/log/univention/ is prepended and the suffix '.log' is appended.
	:param int log_level: log level to use (1-4)
	"""

	if filename[ 0 ] != '/':
		filename = '/var/log/univention/%s.log' % filename
	fd = ud.init( filename, ud.FLUSH, ud.FUNCTION )
	adm = grp.getgrnam( 'adm' )
	os.chown( filename, 0, adm.gr_gid )
	os.chmod( filename, 0640 )
	log_set_level( log_level )

	return fd

def log_set_level( level = 0 ):
	"""Sets the log level for all components.

	:param int level: log level to set
	"""
	for component in COMPONENTS:
		ud.set_level( component, level )

class ILogger( object ):
	"""This class provides a simple interface to access the univention
	debug function for the given component.

	:param int id: id of the component to use
	"""
	def __init__( self, id ):
		self._id = id

	def error( self, message ):
		"""Write a debug message with level ERROR"""
		ud.debug( self._id, ud.ERROR, message )

	def warn( self, message ):
		"""Write a debug message with level WARN"""
		ud.debug( self._id, ud.WARN, message )

	def process( self, message ):
		"""Write a debug message with level PROCESS"""
		ud.debug( self._id, ud.PROCESS, message )

	def info( self, message ):
		"""Write a debug message with level INFO"""
		ud.debug( self._id, ud.INFO, message )

CORE = ILogger( ud.MAIN )
NETWORK = ILogger( ud.NETWORK )
CRYPT = ILogger( ud.SSL )
UDM = ILogger( ud.ADMIN )
MODULE = ILogger( ud.MODULE )
AUTH = ILogger( ud.AUTH )
PARSER = ILogger( ud.PARSER )
LOCALE = ILogger( ud.LOCALE )
ACL = ILogger( ud.ACL )
RESOURCES = ILogger( ud.RESOURCES )
PROTOCOL = ILogger( ud.PROTOCOL )
