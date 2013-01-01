# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: management of virtualization servers
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

import os
from datetime import datetime

from univention.lib.i18n import Translation

from univention.management.console.config import ucr
from univention.management.console.modules import Base, UMC_OptionTypeError, UMC_OptionMissing, UMC_CommandError
from univention.management.console.log import MODULE
from univention.management.console.protocol.definitions import MODULE_ERR_COMMAND_FAILED

from univention.uvmm.protocol import Data_Domain, Disk, Graphic, Interface
# for urlparse extensions
from univention.uvmm import helpers
import urlparse

from notifier import Callback

_ = Translation( 'univention-management-console-modules-uvmm' ).translate

class Snapshots( object ):
	def snapshot_query( self, request ):
		"""Returns a list of snapshots of a domain

		options: { 'domainURI': <domain URI> }

		return: [ { 'id' : <snapshot name>, 'label' : <snapshot name>, 'time' : <creation time> }, ... ]
		"""
		self.required_options( request, 'domainURI' )

		def _finished( thread, result, request ):
			if self._check_thread_error( thread, result, request ):
				return

			node_uri, domain_uuid = urlparse.urldefrag( request.options[ 'domainURI' ] )
			success, data = result

			if success:
				snapshot_list = []
				if success and data.snapshots is not None:
					for name, info in data.snapshots.items():
						creation = datetime.fromtimestamp( info.ctime )
						snapshot = { 'id' : name, 'label' : name, 'time' : creation.strftime( "%x %X" )  }
						snapshot_list.append( snapshot )

				self.finished( request.id, snapshot_list )
			else:
				self.finished( request.id, None, message = str( data ), status = MODULE_ERR_COMMAND_FAILED )

		node_uri, domain_uuid = urlparse.urldefrag( request.options[ 'domainURI' ] )
		self.uvmm.send( 'DOMAIN_INFO', Callback( _finished, request ), uri = node_uri, domain = domain_uuid )


	def snapshot_create( self, request ):
		"""Create a snapshot for a domain

		options: { 'domainURI': <domain URI>. 'snapshotName' : <snapshot name> }

		return: { 'success' : (True|False), 'data' : <details> }
		"""
		self.required_options( request, 'domainURI', 'snapshotName' )

		node_uri, domain_uuid = urlparse.urldefrag( request.options[ 'domainURI' ] )
		self.uvmm.send( 'DOMAIN_SNAPSHOT_CREATE', Callback( self._thread_finish, request ), uri = node_uri, domain = domain_uuid, snapshot = request.options[ 'snapshotName' ] )

	def snapshot_remove( self, request ):
		"""Returns a list of snapshots of a domain

		options: { 'domainURI': <domain URI>. 'name' : <snapshot name> }

		return: { 'success' : (True|False), 'data' : <details> }
		"""
		self.required_options( request, 'domainURI', 'snapshotName' )

		node_uri, domain_uuid = urlparse.urldefrag( request.options[ 'domainURI' ] )
		self.uvmm.send( 'DOMAIN_SNAPSHOT_DELETE', Callback( self._thread_finish, request ), uri = node_uri, domain = domain_uuid, snapshot = request.options[ 'snapshotName' ] )

	def snapshot_revert( self, request ):
		"""Returns a list of snapshots of a domain

		options: { 'domainURI': <domain URI>. 'snapshotName' : <snapshot name> }

		return:
		"""
		self.required_options( request, 'domainURI', 'snapshotName' )

		node_uri, domain_uuid = urlparse.urldefrag( request.options[ 'domainURI' ] )
		self.uvmm.send( 'DOMAIN_SNAPSHOT_REVERT', Callback( self._thread_finish, request ), uri = node_uri, domain = domain_uuid, snapshot = request.options[ 'snapshotName' ] )

