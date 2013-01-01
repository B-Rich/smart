#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Updater
#  Common commands to manage Debian packages
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

from univention.config_registry import ConfigRegistry
configRegistry = ConfigRegistry()
configRegistry.load()

# Update package cache
cmd_update = configRegistry.get('update/commands/update', 'apt-get update')

# Show package information
cmd_show = configRegistry.get('update/commands/show', 'apt-cache show')

# Upgrade only installed packages
cmd_upgrade = configRegistry.get('update/commands/upgrade', 'apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir --trivial-only=no --assume-yes --quiet=1 -u upgrade')
cmd_upgrade_sim = configRegistry.get('update/commands/upgrade/simulate', 'apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir --trivial-only=no --assume-yes --quiet=1 -us upgrade')

# Upgrade system, may install new packages to satisfy dependencies
cmd_dist_upgrade = configRegistry.get('update/commands/distupgrade', 'apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir --trivial-only=no --assume-yes --quiet=1 -u dist-upgrade')
cmd_dist_upgrade_sim = configRegistry.get('update/commands/distupgrade/simulate', 'apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir --trivial-only=no --assume-yes --quiet=1 -us dist-upgrade')

# Install packages
cmd_install = configRegistry.get('update/commands/install', 'apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir --trivial-only=no --assume-yes --quiet=1 install')

# Remove packages
cmd_remove = configRegistry.get('update/commands/remove', 'apt-get --yes remove')

# Configure all pending packages
cmd_config = configRegistry.get('update/commands/configure', 'dpkg --configure -a')

del ConfigRegistry
del configRegistry
