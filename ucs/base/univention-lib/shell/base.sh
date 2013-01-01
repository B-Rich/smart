# Univention Common Shell Library
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


#
# creates an empty file with given owner/group and permissions
# create_logfile <filename> <owner> <permissions>
# e.g. create_logfile /tmp/foo.log root:adm 0750
#
create_logfile () {
	touch "$1"
	chown "$2" "$1"
	chmod "$3" "$1"
}

#
# creates an empty file with given owner/group and permissions if file does not exist
# create_logfile_if_missing <filename> <owner> <permissions>
# e.g. create_logfile_if_missing /tmp/foo.log root:adm 0750
#
create_logfile_if_missing () {
	if [ ! -e "$1" ] ; then
		create_logfile "$@"
	fi
}

#
# calls the given joinscript
# call_joinscript <joinscript>
# e.g. call_joinscript 99my-custom-joinscript.inst
# e.g. call_joinscript 99my-custom-joinscript.inst --binddn ... --bindpwd ...
#
call_joinscript () {
	local joinscript
	joinscript="/usr/lib/univention-install/$1"
	if [ -x "$joinscript" ] ; then
		shift
		local role="$(ucr get server/role)"
		if [ "$role" = "domaincontroller_master" -o "$role" = "domaincontroller_backup" ] ; then
			"$joinscript" "$@"
		fi
	fi
}

#
# calls the given joinscript ONLY on DC master
# call_joinscript_on_dcmaster <joinscript>
# e.g. call_joinscript_on_dcmaster 99my-custom-joinscript.inst
# e.g. call_joinscript_on_dcmaster 99my-custom-joinscript.inst --binddn ... --bindpwd ...
#
call_joinscript_on_dcmaster () {
	local joinscript
	joinscript="/usr/lib/univention-install/$1"
	if [ -x "$joinscript" ] ; then
		shift
		if [ "$(ucr get server/role)" = "domaincontroller_master" ] ; then
			"$joinscript" "$@"
		fi
	fi
}

#
# stops any currently running UDM CLI server
#
stop_udm_cli_server () {
	local pids signal=SIGTERM
	pids=$(pgrep -f "/usr/bin/python.* /usr/share/univention-directory-manager-tools/univention-cli-server") || return 0
	# As long as one of the processes remains, try to kill it.
	while /bin/kill -"$signal" $pids 2>/dev/null # IFS
	do
		sleep 1
		signal=SIGKILL
	done
	return 0
}

#
# if is_domain_controller; then
#         ... do domain controller stuff ...
# fi
#
is_domain_controller () {
	case "$(ucr get server/role)" in
	domaincontroller_master) return 0 ;;
	domaincontroller_backup) return 0 ;;
	domaincontroller_slave) return 0 ;;
	*) return 1 ;;
	esac
}

#
# returns the default IP address
#
get_default_ip_address () {
	PYTHONPATH=/usr/lib/pymodules/python2.6/univention/config_registry python2.6 2>/dev/null \
	-c 'from interfaces import Interfaces;print Interfaces().get_default_ip_address().ip'
}

#
# returns the default IPv4 address
#
get_default_ipv4_address () {
	PYTHONPATH=/usr/lib/pymodules/python2.6/univention/config_registry python2.6 2>/dev/null \
	-c 'from interfaces import Interfaces;print Interfaces().get_default_ipv4_address().ip'
}

#
# returns the default IPv6 address
#
get_default_ipv6_address () {
	PYTHONPATH=/usr/lib/pymodules/python2.6/univention/config_registry python2.6 2>/dev/null \
	-c 'from interfaces import Interfaces;print Interfaces().get_default_ipv6_address().ip'
}

#
# returns the default netmask
#
get_default_netmask () {
	PYTHONPATH=/usr/lib/pymodules/python2.6/univention/config_registry python2.6 2>/dev/null \
	-c 'from interfaces import Interfaces;import ipaddr;a=Interfaces().get_default_ip_address();print a.netmask if isinstance(a,ipaddr.IPv4Network) else a.prefixlen'
}

#
# returns the default network
#
get_default_network () {
	PYTHONPATH=/usr/lib/pymodules/python2.6/univention/config_registry python2.6 2>/dev/null \
	-c 'from interfaces import Interfaces;print Interfaces().get_default_ip_address().network'
}


#
# check whether a package is installed or not
#
check_package_status ()
{
        echo "$(dpkg --get-selections "$1" 2>/dev/null | awk '{print $2}')"
}


# vim:set sw=4 ts=4 noet:
