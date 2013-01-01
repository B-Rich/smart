#!/bin/bash
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

. /usr/share/univention-lib/all.sh

LDB_MODULES_PATH=/usr/lib/ldb; export LDB_MODULES_PATH;		## currently necessary for ldbtools

eval "$(univention-config-registry shell)"

samba_private_dir="/var/lib/samba/private"
samba_sam="$samba_private_dir/sam.ldb"
samba_secrets="$samba_private_dir/secrets.ldb"
SCRIPTDIR=/usr/share/univention-samba4/scripts
LOGFILE="/var/log/univention/samba4-provision.log"

touch $LOGFILE
chmod 600 $LOGFILE

usage(){ echo "$0 [-h|--help] [-w <samba4-admin password file>] [-W]"; exit 1; }

adminpw="$(pwgen -1 -s -c -n 16)"
adminpw2="$adminpw"

while getopts  "h-:W:" option; do
	case "${option}" in
		h) usage;;
		-)
		case "${OPTARG}" in
			binddn)
				binddn="${!OPTIND}"
				OPTIND=$((OPTIND+1))
				;;
			bindpwd)
				bindpwd="${!OPTIND}"
				OPTIND=$((OPTIND+1))
				;;
			site|site=*)
				## allow "--site=foo" and "--site foo"
				val=${OPTARG#*=}
				if [ "$val" != "$OPTARG" ]; then
					opt=${OPTARG%=$val}
				else
					val="${!OPTIND}"
					opt="${OPTARG}"
					OPTIND=$((OPTIND+1))
				fi
				## store the sitename
				sitename="$val"
				;;
			help)
				usage
				;;
			*)
				echo "Unknown option --${OPTARG}" >&2
				;;
		esac;;
		w) if [ -r "$OPTARG" ]; then adminpw="$(< $OPTARG)"; adminpw2="$adminpw"; fi ;;
		W) adminpw2='!unset';;
	esac
done

DOMAIN_SID="$(univention-ldapsearch -x "(&(objectclass=sambadomain)(sambaDomainName=$windows_domain))" sambaSID | sed -n 's/sambaSID: \(.*\)/\1/p')"

## helper function
stop_conflicting_services() {
	## stop samba3 services and heimdal-kdc if present
	if [ -x /etc/init.d/samba ]; then
		if [ -n "$(pgrep -f '/usr/sbin/(smbd|nmbd)')" ]; then
			/etc/init.d/samba stop 2>&1 | tee -a "$LOGFILE"
		fi
	fi
	if [ -x /etc/init.d/winbind ]; then
		if [ -n "$(pgrep -xf /usr/sbin/winbindd)" ]; then
			/etc/init.d/winbind stop 2>&1 | tee -a "$LOGFILE"
		fi
	fi
	if [ -x /etc/init.d/heimdal-kdc ]; then
		if [ -n "$(pgrep -f '/usr/lib/heimdal-servers/(kdc|kpasswdd)')" ]; then
			/etc/init.d/heimdal-kdc stop 2>&1 | tee -a "$LOGFILE"
		fi
	fi

	tmp_ucr_key_value_list=()
	if [ "$samba_autostart" != "no" ]; then
			tmp_ucr_key_value_list[0]="samba/autostart=no"
	fi
	if [ "$winbind_autostart" != "no" ]; then
			tmp_ucr_key_value_list[${#tmp_ucr_key_value_list[@]}]="winbind/autostart=no"
	fi
	if [ "$kerberos_autostart" != "no" ]; then
			tmp_ucr_key_value_list[${#tmp_ucr_key_value_list[@]}]="kerberos/autostart=no"
	fi
	if [ -n "$tmp_ucr_key_value_list" ]; then
		univention-config-registry set "${tmp_ucr_key_value_list[@]}" 2>&1 | tee -a "$LOGFILE"
	fi
	unset tmp_ucr_key_value_list
}

set_machine_secret() {
	## 1. store password locally in secrets.ldb
	old_kvno=$(ldbsearch -H "$samba_sam" samAccountName="${hostname}\$" msDS-KeyVersionNumber | sed -n 's/msDS-KeyVersionNumber: \(.*\)/\1/p')
	new_kvno=$(($old_kvno + 1))

	ldbmodify -H "$samba_secrets" <<-%EOF
	dn: flatname=${windows_domain},cn=Primary Domains
	changetype: modify
	replace: secret
	secret:< file:///etc/machine.secret
	-
	replace: msDS-KeyVersionNumber
	msDS-KeyVersionNumber: $new_kvno
	-
	%EOF

	## 2. replace random machine secret in SAM with /etc/machine.secret
	samba-tool user setpassword "${hostname}\$" --newpassword="$(cat /etc/machine.secret)"
}

# Search for Samba 3 DCs
S3_DCS="$(univention-ldapsearch -x "(&(objectclass=univentionDomainController)(univentionService=Samba 3))" cn | sed -n 's/cn: \(.*\)/\1/p')"
if [ -n "$S3_DCS" ]; then
	## safty belt
	if is_ucr_true samba4/ignore/mixsetup; then
		echo "WARNING: The following Samba 3 domaincontroller have been found:"
		echo "         $S3_DCS"
		echo "         It is not possible to install a samba 4 domaincontroller "
		echo "         into a samba 3 environment.samba4/ignore/mixsetup is true."
		echo "         Continue as requested"
	else
		echo "ERROR: The following Samba 3 domaincontroller have been found:"
		echo "       $S3_DCS"
		echo "       It is not possible to install a samba 4 domaincontroller "
		echo "       into a samba 3 environment."
		exit 1
	fi
fi

if [ -z "$binddn" ]; then
	if [ -r "/etc/ldap.secret" ]; then
		binddn="cn=admin,$ldap_base"
		bindpwd=$(< /etc/ldap.secret)
	else
		echo "ERROR: Options --binddn and --bindpwd not given for samba3upgrade"
		exit 1
	fi
fi
## store the binddn and bindpwd options in UDM_ARGV
UDM_ARGV=("--binddn" "$binddn" --bindpwd "$bindpwd")
set -- "${UDM_ARGV[@]}"


while [ "$adminpw" != "$adminpw2" ]; do
	read -p "Choose Samba4 admin password: " adminpw
	if [ "${#adminpw}" -lt 8 ]; then
		echo "Password too short, Samba4 minimal requirements: 8 characters, one digit, one uppercase"
		continue
	fi
	read -p "Confirm password: " adminpw2
	if [ "$adminpw" != "$adminpw2" ]; then
		echo "Passwords don't match, please try again"
	fi
done

## Provision Samba4
stop_conflicting_services

if [ ! -e /usr/modules ]; then
	ln -s /usr/lib /usr/modules		# somehow MODULESDIR is set to /usr/modules in samba4 source despite --enable-fhs
fi

if [ -z "$samba4_function_level" ]; then
	samba4_function_level=2003
	univention-config-registry set samba4/function/level="$samba4_function_level"
fi


if [ -z "$S3_DCS" ] || [ -z "$DOMAIN_SID" ]; then

	if [ -z "$DOMAIN_SID" ]; then
		# No SID for this windows/domain has been generated
		DOMAIN_SID="$(univention-newsid)"
	fi

	if [ -z "$sitename" ]; then
		samba-tool domain provision --realm="$kerberos_realm" --domain="$windows_domain" --domain-sid="$DOMAIN_SID" \
							--function-level="$samba4_function_level" \
							--adminpass="$adminpw" --server-role='domain controller'	\
							--machinepass="$(</etc/machine.secret)" 2>&1 | tee -a "$LOGFILE"
	else
		samba-tool domain provision --realm="$kerberos_realm" --domain="$windows_domain" --domain-sid="$DOMAIN_SID" \
							--function-level="$samba4_function_level" \
							--adminpass="$adminpw" --server-role='domain controller'	\
							--sitename="$sitename" \
							--machinepass="$(</etc/machine.secret)" 2>&1 | tee -a "$LOGFILE"
	fi

	if ! ldbsearch -H "$samba_sam" -b "$samba4_ldap_base" -s base dn 2>/dev/null| grep -qi ^"dn: $samba4_ldap_base"; then
		echo "Samba4 provision failed, exiting $0"
		exit 1
	fi

else
	## Before starting the upgrade check for Samba accounts that are not POSIX accounts:
	non_posix_sambaSamAccount_dns=$(univention-ldapsearch -xLLL "(&(objectClass=sambaSamAccount)(!(objectClass=posixAccount)))" dn | sed -n 's/^dn: \(.*\)/\1/p')
	if [ -n "$non_posix_sambaSamAccount_dns" ]; then
		echo "ERROR: Found Samba accounts in LDAP that are not POSIX accounts, please remove these before updating to Samba 4" >&2
		echo "$non_posix_sambaSamAccount_dns" | while read dn; do
			echo "DN: $dn" >&2
		done
		exit 1
	fi

	## Before starting the upgrade check for group names colliding with user names
	uid_ldap_check_function() {
		local filter="$1"
		collision=$(univention-ldapsearch -xLLL "(&(objectClass=posixAccount)(|$filter))" uid | sed -n 's/^uid: \(.*\)/\1/p')
		if [ -n "$collision" ]; then
			echo "ERROR: Group names and user names must be unique, please rename these before updating to Samba 4" >&2
			echo "The following user names are also present as group names:" >&2
			echo "$collision" >&2
			exit 1
		fi
	}

	filter_maxsize=10000	## approximate limit for the LDAP filter string size
	while read name; do
		if [ "$((${#filter} + ${#name}))" -lt "$filter_maxsize" ]; then
			filter="$filter(uid=$name)"
		else
			uid_ldap_check_function "$filter"
			filter="(uid=$name)"
		fi
	done < <(univention-ldapsearch -xLLL "(objectClass=posixGroup)" cn | sed -n 's/^cn: \(.*\)/\1/p')
	if [ -n "$filter" ]; then
		uid_ldap_check_function "$filter"
	fi

	## Preparations for the samba3update:
	eval $(echo "$@" | sed -n 's/.*--binddn \(.*\) --bindpwd \(.*\).*/binddn="\1"\nbindpwd="\2"/p')
	groups=("Windows Hosts" "DC Backup Hosts" "DC Slave Hosts" "Computers" "Power Users")
	for group in "${groups[@]}"; do
		record=$(univention-ldapsearch -xLLL "(&(cn=$group)(objectClass=univentionGroup))" dn description | ldapsearch-wrapper)
		description=$(echo "$record" | sed -n 's/^description: \(.*\)/\1/p')
		if [ -z "$description" ]; then
			dn=$(echo "$record" | sed -n 's/^dn: \(.*\)/\1/p')
			univention-directory-manager groups/group modify "$@" --dn "$dn" --set description="$group"
		fi
	done

	### create ldifs to temporarily fix sambaGroupType 5 and 2 for samba3upgrade
	### unfortunately udm currently does not allow setting sambaGroupType=4
	create_modify_ldif() {
		record="$1"
		dn=$(echo "$record" | sed -n "s/dn: \(.*\)/\1/p")
		if [ -n "$dn" ]; then
			cat <<-%EOF
			dn: $dn
			changetype: modify
			replace: sambaGroupType
			sambaGroupType: 4
			-

			%EOF
		fi
	}

	ldif_records() {
		func="$1"; shift
		if ! declare -F "$func" >/dev/null; then
			echo "ldif_records: First argument must be a valid function name"
			echo "ldif_records: "$func" is not a valid function name"
			return 1
		fi
		while read -d '' record; do
			"$func" "$record" "$@"
		done < <(sed 's/^$/\x0/')	## beware: skips last record, but that's ok with usual univention-ldapsearch output
	}

	ldif_sambaGroupType_5_to_4=$(univention-ldapsearch sambaGroupType=5 dn sambaGroupType | ldapsearch-wrapper | ldif_records create_modify_ldif)
	reverse_ldif_sambaGroupType_5_to_4="${ldif_sambaGroupType_5_to_4//sambaGroupType: 4/sambaGroupType: 5}"

	ldif_sambaGroupType_2_to_4=$(univention-ldapsearch sambaGroupType=2 dn sambaGroupType | ldapsearch-wrapper | ldif_records create_modify_ldif)
	reverse_ldif_sambaGroupType_2_to_4="${ldif_sambaGroupType_2_to_4//sambaGroupType: 4/sambaGroupType: 2}"

	reverse_sambaGroupType_change() {
		echo "$reverse_ldif_sambaGroupType_5_to_4" | ldapmodify -h "$ldap_master" -p "$ldap_master_port" -D "$binddn" -w "$bindpwd" | tee -a "$LOGFILE"
		echo "$reverse_ldif_sambaGroupType_2_to_4" | ldapmodify -h "$ldap_master" -p "$ldap_master_port" -D "$binddn" -w "$bindpwd" | tee -a "$LOGFILE"
	}
	trap reverse_sambaGroupType_change EXIT

	## now adjust sambaGroupType 2 and 5
	echo "$ldif_sambaGroupType_5_to_4" | ldapmodify -h "$ldap_master" -p "$ldap_master_port" -D "$binddn" -w "$bindpwd" | tee -a "$LOGFILE"
	echo "$ldif_sambaGroupType_2_to_4" | ldapmodify -h "$ldap_master" -p "$ldap_master_port" -D "$binddn" -w "$bindpwd" | tee -a "$LOGFILE"

	## commit samba3 smb.conf
	mkdir -p /var/lib/samba3/etc/samba
	cat /usr/share/univention-samba4/samba3upgrade/smb.conf.d/* | ucr filter > /var/lib/samba3/etc/samba/smb.conf
	## fix up /var/lib/samba3/smb.conf for samba-tool
	touch /etc/samba/base.conf /etc/samba/installs.conf /etc/samba/printers.conf /etc/samba/shares.conf
	echo -e "[global]\n\trealm = $kerberos_realm" >> /var/lib/samba3/etc/samba/smb.conf

	## move  univention-samba4 default smb.conf out of the way
	mv /etc/samba/smb.conf /var/tmp/univention-samba4_smb.conf
	### run samba-tool domain samba3upgrade
	samba-tool domain classicupgrade /var/lib/samba3/etc/samba/smb.conf --dbdir /var/lib/samba3 | tee -a "$LOGFILE"
	## move univention-samba4 config back again, overwriting minimal smb.conf created by samba3upgrade
	mv /var/tmp/univention-samba4_smb.conf /etc/samba/smb.conf

	### revert changes for sambaGroupType 5 and 2
	reverse_sambaGroupType_change
	trap - EXIT

	## set the samba4 machine account secret in secrets.ldb to /etc/machine.secret
	set_machine_secret

	## finally set the Administrator password, which samba3upgrade did not migrate
	samba-tool user setpassword Administrator --newpassword="$adminpw"
fi

if [ ! -d /etc/phpldapadmin ]; then
	mkdir /etc/phpldapadmin
fi
if [ ! -e /etc/phpldapadmin/config.php ]; then
	cp "$samba_private_dir/phpldapadmin-config.php" /etc/phpldapadmin/config.php
fi

### Next adjust OpenLDAP ports before starting Samba4

# Test:
# r 389
# r 7389,389
# r 389,7389
# r 389,7389,8389
# r 7389,389,8389
# r 7389,8389,389
remove_port ()
{
	if [ -n "$1" -a -n "$2" ]; then
		echo "$1" | sed -e "s|^${2},||;s|,${2},|,|;s|,${2}$||;s|^${2}$||"
	fi

}

if [ -n "$slapd_port" ]; then
	univention-config-registry set slapd/port="$(remove_port "$slapd_port" 389)" 2>&1 | tee -a "$LOGFILE"
fi
if [ -n "$slapd_port_ldaps" ]; then
	univention-config-registry set slapd/port/ldaps="$(remove_port "$slapd_port_ldaps" 636)" 2>&1 | tee -a "$LOGFILE"
fi
if [ "$ldap_server_name" = "$hostname.$domainname" ]; then
	univention-config-registry set ldap/server/port="7389" 2>&1 | tee -a "$LOGFILE"
fi
if [ "$ldap_master" = "$hostname.$domainname" ]; then
	univention-config-registry set ldap/master/port="7389" 2>&1 | tee -a "$LOGFILE"
fi

## restart processes with adjusted ports
stop_udm_cli_server
/etc/init.d/slapd restart 2>&1 | tee -a "$LOGFILE"
/etc/init.d/univention-directory-listener restart 2>&1 | tee -a "$LOGFILE"
/etc/init.d/univention-management-console-server restart 2>&1 | tee -a "$LOGFILE"

exit 0
