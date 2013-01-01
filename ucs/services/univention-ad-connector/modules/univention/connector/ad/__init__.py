#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention AD Connector
#  Basic class for the AD connector part
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


import string, ldap, sys, traceback, base64, time, pdb, os, copy, types
import array
import univention.uldap
import univention.connector
import univention.debug2 as ud
from ldap.controls import LDAPControl
from ldap.controls import SimplePagedResultsControl

# page results
PAGE_SIZE=1000

def activate_user (connector, key, object):
        # set userAccountControl to 544
        for i in range(0,10):
                try:
                        connector.lo_ad.lo.modify_s(compatible_modstring(object['dn']), [(ldap.MOD_REPLACE, 'userAccountControl', ['544'])])
                except ldap.NO_SUCH_OBJECT:
                        time.sleep(1)
                        continue
                return True
        return False

def group_members_sync_from_ucs(connector, key, object):
	return connector.group_members_sync_from_ucs(key, object)
	
def object_memberships_sync_from_ucs(connector, key, object):
	return connector.object_memberships_sync_from_ucs(key, object)

def group_members_sync_to_ucs(connector, key, object):
	return connector.group_members_sync_to_ucs(key, object)

def object_memberships_sync_to_ucs(connector, key, object):
	return connector.object_memberships_sync_to_ucs(key, object)

def primary_group_sync_from_ucs(connector, key, object):
	return connector.primary_group_sync_from_ucs(key, object)
	
def primary_group_sync_to_ucs(connector, key, object):
	return connector.primary_group_sync_to_ucs(key, object)

def disable_user_from_ucs(connector, key, object):
	return connector.disable_user_from_ucs(key, object)

def set_userPrincipalName_from_ucr(connector, key, object):
	return connector.set_userPrincipalName_from_ucr(key, object)

def disable_user_to_ucs(connector, key, object):
	return connector.disable_user_to_ucs(key, object)

def encode_attrib(attrib):
	if not attrib or type(attrib) == type(u''): # referral or already unicode
		return attrib
	return unicode(attrib, 'utf8')

def encode_attriblist(attriblist):
	if not type(attriblist) == type([]):
		return encode_attrib(attriblist)
	else:
		for i in range(len(attriblist)):
			attriblist[i] = encode_attrib(attriblist[i])
		return attriblist

def encode_ad_object(ad_object):
	if type(ad_object) == type([]):
		return encode_attriblist(ad_object)
	else:
		for key in ad_object.keys():
			if key == 'objectSid':
				ad_object[key]=[decode_sid(ad_object[key][0])]
			elif key in ['objectGUID','ipsecData','repsFrom','replUpToDateVector','userCertificate','dNSProperty','dnsRecord','securityIdentifier','mS-DS-CreatorSID','logonHours','mSMQSites','mSMQSignKey','currentLocation','dSASignature','linkTrackSecret','mSMQDigests','mSMQEncryptKey','mSMQSignCertificates','may','sIDHistory', 'msExchMailboxSecurityDescriptor', 'msExchMailboxGuid', 'msExchMasterAccountSid', 'replicationSignature', 'repsTo']:
				ud.debug(ud.LDAP, ud.INFO,
						       "encode_ad_object: attrib %s ignored during encoding" % key) # don't recode
			else:
				try:
					ad_object[key]=encode_attriblist(ad_object[key])
				except (ldap.SERVER_DOWN, SystemExit):
					raise
				except: # FIXME: which exception is to be caught?
					ud.debug(ud.LDAP, ud.WARN,
							       "encode_ad_object: encode attrib %s failed, ignored!" % key)
		return ad_object

def encode_ad_result(ad_result):
	'''
	encode an result from an python-ldap search
	'''
	return (encode_attrib(ad_result[0]),encode_ad_object(ad_result[1]))

def encode_ad_resultlist(ad_resultlist):
	'''
	encode an result from an python-ldap search
	'''
	for i in range(len(ad_resultlist)):
		ad_resultlist[i] = encode_ad_result(ad_resultlist[i])
	return ad_resultlist

def unix2ad_time(l):
	d=116444736000000000L #difference between 1601 and 1970
	return long(time.mktime(time.gmtime(time.mktime(time.strptime(l,"%Y-%m-%d"))+90000)))*10000000+d # 90000s are one day and one hour

def ad2unix_time(l):
	d=116444736000000000L #difference between 1601 and 1970
	return time.strftime("%d.%m.%y",time.gmtime((l-d)/10000000))

def samba2ad_time(l):
	if l in [0,1]:
		return l
	d=116444736000000000L #difference between 1601 and 1970
	return long(time.mktime(time.gmtime(l+3600)))*10000000+d

def ad2samba_time(l):
	if l == 0:
		return l
	d=116444736000000000L #difference between 1601 and 1970
	return long(((l-d))/10000000)

# mapping funtions
def samaccountname_dn_mapping(connector, given_object, dn_mapping_stored, ucsobject, propertyname, propertyattrib, ocucs, ucsattrib, ocad):
	'''
	map dn of given object (which must have an samaccountname in AD)
	ocucs and ocad are objectclasses in UCS and AD
	'''
	object = copy.deepcopy(given_object)

	samaccountname = ''
	
	if object['dn'] != None:
		if object['attributes'].has_key('sAMAccountName'):
			samaccountname=object['attributes']['sAMAccountName'][0]
		
	def dn_premapped(object, dn_key, dn_mapping_stored):
		if (not dn_key in dn_mapping_stored) or (not object[dn_key]):
			ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: not premapped (in first instance)")
			return False
		else: # check if DN exists
			if ucsobject:
				if connector.get_object(object[dn_key]) != None:
					ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: premapped AD object found")
					return True
				else:
					ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: premapped AD object not found")
					return False
			else:
				if connector.get_ucs_ldap_object(object[dn_key]) != None:
					ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: premapped UCS object found")
					return True
				else:
					ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: premapped UCS object not found")
					return False
					
								

	for dn_key in ['dn','olddn']:
		ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: check newdn for key %s:"%dn_key)
		if object.has_key(dn_key) and not dn_premapped(object, dn_key, dn_mapping_stored):

			dn = object[dn_key]

			# Skip Configuration objects with empty DNs
			if dn == None:
				break

			pos = string.find(dn,'=')
			pos2 =  len(univention.connector.ad.explode_unicode_dn(dn)[0])
			attrib = dn[:pos]
			value = dn[pos+1:pos2]

			if ucsobject:
				# lookup the cn as sAMAccountName in AD to get corresponding DN, if not found create new
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: got an UCS-Object")

				if connector.property[propertyname].mapping_table and propertyattrib in connector.property[propertyname].mapping_table.keys():
					for ucsval, conval in connector.property[propertyname].mapping_table[propertyattrib]:
						try:
							if value.lower() == ucsval.lower():
								value = conval
								ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: map samaccountanme regarding to mapping-table")
								continue
						except UnicodeDecodeError:
							pass # values are not the same codec
								
				
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: search in ad samaccountname=%s"%value)
				result = connector.lo_ad.lo.search_ext_s(connector.lo_ad.base,ldap.SCOPE_SUBTREE,
								     compatible_modstring('(&(objectclass=%s)(samaccountname=%s))'%(ocad,value)))
				if result and len(result)>0 and result[0] and len(result[0])>0 and result[0][0]: # no referral, so we've got a valid result
					addn = encode_attrib(result[0][0])
					adpos2 = len(univention.connector.ad.explode_unicode_dn(addn)[0])
					if dn_key == 'olddn' or (dn_key == 'dn' and not object.has_key('olddn')):
						newdn = addn
					else:
						addn = addn[:adpos2] + dn[pos2:]
						newdn = addn.lower().replace(connector.lo_ad.base.lower(), connector.lo.base.lower())					
					
				else:
					newdn = 'cn' + dn[pos:] #new object, don't need to change

			else:
				# get the object to read the sAMAccountName in AD and use it as name
				# we have no fallback here, the given dn must be found in AD or we've got an error
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: got an AD-Object")
				i = 0
				
				while ( not samaccountname ): # in case of olddn this is already set
					i = i + 1
					search_dn = dn
					if object.has_key('deleted_dn'):
						search_dn = object['deleted_dn']
					try:
						samaccountname = encode_attrib(
							connector.lo_ad.lo.search_ext_s(compatible_modstring(search_dn), ldap.SCOPE_BASE,
											'(objectClass=%s)' % ocad, ['sAMAccountName']) [0][1]['sAMAccountName'][0])
						ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: got samaccountname from AD")
					except ldap.NO_SUCH_OBJECT: # AD may need time
						if i > 5:
							raise
						time.sleep(1) # AD may need some time...

				pos = string.find(dn,'=')
				pos2 = len(univention.connector.ad.explode_unicode_dn(dn)[0])

				if connector.property[propertyname].mapping_table and propertyattrib in connector.property[propertyname].mapping_table.keys():
					for ucsval, conval in connector.property[propertyname].mapping_table[propertyattrib]:
						if samaccountname.lower() == conval.lower():
							samaccountname = ucsval
							ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: map samaccountanme regarding to mapping-table")
							continue
						else:
							ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: samaccountname not in mapping-table")

				# search for object with this dn in ucs, needed if it lies in a different container
				ucsdn = ''
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: samaccountname is:%s"%samaccountname)
				ucsdn_result = connector.search_ucs(filter=unicode(u'(&(objectclass=%s)(%s=%s))' % (ocucs, ucsattrib, samaccountname)),
								   base=connector.lo.base, scope='sub', attr=['objectClass'])
				if ucsdn_result and len(ucsdn_result) > 0 and ucsdn_result[0] and len(ucsdn_result[0]) > 0:
					ucsdn = ucsdn_result[0][0]
					
				if ucsdn and (dn_key == 'olddn' or (dn_key == 'dn' and not object.has_key('olddn'))):
					newdn = ucsdn
					ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: newdn is ucsdn")
				else:
					newdn = ucsattrib + '=' + samaccountname + dn[pos2:] # guess the old dn
			try:
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: newdn for key %s:" % dn_key)
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: olddn: %s" % dn)
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: newdn: %s" % newdn)
			except: # FIXME: which exception is to be caught?
				ud.debug(ud.LDAP, ud.INFO, "samaccount_dn_mapping: dn-print failed")


			object[dn_key]=newdn
	return object


def user_dn_mapping(connector, given_object, dn_mapping_stored, isUCSobject):
	'''
	map dn of given user using the samaccountname/uid
	connector is an instance of univention.connector.ad, given_object an object-dict,
	dn_mapping_stored a list of dn-types which are already mapped because they were stored in the config-file
	'''
	return samaccountname_dn_mapping(connector, given_object, dn_mapping_stored, isUCSobject, 'user', u'samAccountName', u'posixAccount', 'uid', u'user')

def group_dn_mapping(connector, given_object, dn_mapping_stored, isUCSobject):
	'''
	map dn of given group using the samaccountname/cn
	connector is an instance of univention.connector.ad, given_object an object-dict,
	dn_mapping_stored a list of dn-types which are already mapped because they were stored in the config-file
	'''
	return samaccountname_dn_mapping(connector, given_object, dn_mapping_stored, isUCSobject, 'group', u'cn', u'posixGroup', 'cn', u'group')

def old_user_dn_mapping(connector, given_object):
	object = copy.deepcopy(given_object)

	# LDAP_SERVER_SHOW_DELETED_OID -> 1.2.840.113556.1.4.417
	ctrls = [LDAPControl('1.2.840.113556.1.4.417',criticality=1)]
	samaccountname = ''

	if object.has_key('sAMAccountName'):
		samaccountname=object['sAMAccountName']
		
	for dn_key in ['dn','olddn']:
		ud.debug(ud.LDAP, ud.INFO, "check newdn for key %s:"%dn_key)
		if object.has_key(dn_key):

			dn = object[dn_key]

			pos = string.find(dn,'=')
			pos2 = len(univention.connector.ad.explode_unicode_dn(dn)[0])-1
			attrib = dn[:pos]
			value = dn[pos+1:pos2]

			if attrib == 'uid':
				# lookup the uid as sAMAccountName in AD to get corresponding DN, if not found create new User
				ud.debug(ud.LDAP, ud.INFO, "search in ad samaccountname=%s"%value)
				result = connector.lo_ad.lo.search_ext_s(connector.lo_ad.base,ldap.SCOPE_SUBTREE,
								     '(&(objectclass=user)(samaccountname=%s))'%compatible_modstring(value))
				ud.debug(ud.LDAP, ud.INFO, "search in result %s"%result)
				if result and len(result)>0 and result[0] and len(result[0])>0 and result[0][0]: # no referral, so we've got a valid result
					addn = encode_attrib(result[0][0])
					ud.debug(ud.LDAP, ud.INFO, "search in ad gave dn %s"%addn)
					adpos2 = len(univention.connector.ad.explode_unicode_dn(addn)[0])-1					
					#newdn = addn[:adpos2] + dn[pos2:]
					newdn = addn
				else:
 					newdn = 'cn' + dn[pos:]

			else:
				# get the object to read the sAMAccountName in AD and use it as uid
				# we have no fallback here, the given dn must be found in AD or we've got an error
				i = 0
				while ( not samaccountname ): # in case of olddn this is already set
					i = i + 1
					search_dn = dn
					if object.has_key('deleted_dn'):
						search_dn = object['deleted_dn']
					try:
						samaccountname = encode_attrib(
							connector.lo_ad.lo.search_ext_s(compatible_modstring(search_dn), ldap.SCOPE_BASE,
											'(objectClass=user)', ['sAMAccountName'],
											serverctrls=ctrls) [0][1]['sAMAccountName'][0])
					except ldap.NO_SUCH_OBJECT: # AD may need time
						if i > 5:
							raise
						time.sleep(1) # AD may need some time...

				pos = string.find(dn,'=')
				pos2 = len(univention.connector.ad.explode_unicode_dn(dn)[0])-1

				newdn = 'uid=' + samaccountname + dn[pos2:]
			try:
				ud.debug(ud.LDAP, ud.INFO, "newdn for key %s:"%dn_key)
				ud.debug(ud.LDAP, ud.INFO, "olddn: %s"%dn)
				ud.debug(ud.LDAP, ud.INFO, "newdn: %s"%newdn)
			except: # FIXME: which exception is to be caught?
				pass

			object[dn_key]=newdn
	return object

def decode_sid(value):
	# SID in AD
	#
	#   | Byte 1         | Byte 2-7           | Byte 9-12                | Byte 13-16 |
	#   ----------------------------------------------------------------------------------------------------------------
	#   | Der erste Wert | Gibt die Laenge    | Hier sind jetzt          | siehe 9-12 |
	#   | der SID, also  | des restlichen     | die eiegntlichen         |            |
	#   | der Teil nach  | Strings an, da die | SID Daten.               |            |
	#   | S-             | SID immer relativ  | In einem int Wert        |            |
	#   |                | kurz ist, meistens | sind die Werte           |            |
	#   |                | nur das 2. Byte    | Hexadezimal gespeichert. |            |
	#
	sid='S-'
	sid+="%d" % ord(value[0])
	
	sid_len=ord(value[1])
	
	sid+="-%d" % ord(value[7])
	
	for i in range(0,sid_len):
		res=ord(value[8+(i*4)]) + (ord(value[9+(i*4)]) << 8) + (ord(value[10+(i*4)]) << 16) + (ord(value[11+(i*4)]) << 24)
		sid+="-%u" % res
			
	return sid

def encode_sid(value):
	a=array.array('c')

	vlist=value.replace('S-','').split('-')
	a.append(chr(int(vlist[0])))
	a.append(chr(len(vlist)-2))
	a.append(chr(0))
	a.append(chr(0))
	a.append(chr(0))
	a.append(chr(0))
	a.append(chr(0))
	a.append(chr(int(vlist[1])))
	for i in range(2,len(vlist)):
		a.append(chr((long(vlist[i]) & 0xff)))
		a.append(chr((long(vlist[i]) & 0xff00) >> 8))
		a.append(chr((long(vlist[i]) & 0xff0000) >> 16))
		a.append(chr((long(vlist[i]) & 0xff000000) >> 24))

	return a


def encode_object_sid(sid_string, encode_in_base64=True):
    binary_encoding = ""

    for i in sid.split("-")[1:]:
        j = int(i)

        oc1 = (j >> 24)
        oc2 = (j - (oc1 * (2 << 23))) >> 16
        oc3 = (j - (oc1 * (2 << 23)) - (oc2 * (2 << 15))) >> 8
        oc4 = j - (oc1 * (2 << 23)) - (oc2 * (2 << 15)) - (oc3 * (2 << 7))

        binary_encoding_chunk = chr(oc4) + chr(oc3) + chr(oc2) + chr(oc1)
        binary_encoding += binary_encoding_chunk

    if encode_in_base64:
        return base64.encodestring(binary_encoding)

    return binary_encoding


def encode_list(list, encoding):
	newlist=[]
	if not list:
		return list
	for val in list:
		if hasattr(val,'encode'):
			newlist.append(val.encode(encoding))
		else:
			newlist.append(val)
	return newlist

def decode_list(list, encoding):
	newlist=[]
	if not list:
		return list
	for val in list:
		if hasattr(val,'decode') and not type(val) == types.UnicodeType:
			newlist.append(val.decode(encoding))
		else:
			newlist.append(val)
	return newlist

def unicode_list(list, encoding):
	newlist=[]
	if encoding:
		for val in list:
			newlist.append(unicode(val,encoding))
	else:
		for val in list:
			newlist.append(unicode(val))
	return newlist

def encode_modlist(list, encoding):
	newlist=[]
	for (modtype, attr, values) in list:
		if hasattr(attr,'encode'):
			newattr=attr.encode(encoding)
		else:
			newattr=attr
		if type(values) == type([]):
			newlist.append((modtype,newattr,encode_list(values, encoding)))
		else:
			newlist.append((modtype,newattr,encode_list(values, encoding)))
	return newlist

def decode_modlist(list, encoding):
	newlist=[]
	for (modtype, attr, values) in list:
		if hasattr(attr,'decode') and not type(attr)==types.UnicodeType:
			newattr=attr.decode(encoding)
		else:
			newattr=attr
		if type(values) == type([]):
			newlist.append((modtype,newattr,decode_list(values, encoding)))
		else:
			newlist.append((modtype,newattr,decode_list(values, encoding)))
	return newlist

def encode_addlist(list, encoding):
	newlist=[]
	for (attr, values) in list:
		if hasattr(attr,'encode'):
			newattr=attr.encode(encoding)
		else:
			newattr=attr
		if type(values) == type([]):
			newlist.append((newattr,encode_list(values, encoding)))
		else:
			newlist.append((newattr,encode_list(values, encoding)))
	return newlist

def decode_addlist(list, encoding):
	newlist=[]
	for (attr, values) in list:
		if hasattr(attr,'decode') and not type(attr)==types.UnicodeType:
			newattr=attr.decode(encoding)
		else:
			newattr=attr
		if type(values) == type([]):
			newlist.append((newattr,decode_list(values, encoding)))
		else:
			newlist.append((newattr,decode_list(values, encoding)))
	return newlist

def compatible_list(list):
	return encode_list(decode_list(list,'latin'),'utf8')

def compatible_modlist(list):
	return encode_modlist(decode_modlist(list,'latin'),'utf8')

def compatible_addlist(list):
	return encode_addlist(decode_addlist(list,'latin'),'utf8')

def compatible_modstring(string):
	if hasattr(string,'decode') and not type(string) == types.UnicodeType:
		string = string.decode('latin')
	if hasattr(string,'encode'):
		string = string.encode('utf8')
	return string

def explode_unicode_dn(dn, notypes=0):
	ret = []
	last = -1
	last_found = 0
	while dn.find(',',last+1) > 0:
		last = dn.find(',',last+1)
		if dn[last-1] != '\\':
			if notypes == 1:
				last_found = dn.find('=',last_found)+1
			if dn[last_found] == ',':
				last_found += 1
			ret.append(dn[last_found:last])
			last_found = last			
	ret.append(dn[last+1:])                                                                                                      
	
	return ret

class ad(univention.connector.ucs):
	def __init__(self, CONFIGBASENAME, property, baseConfig, ad_ldap_host, ad_ldap_port, ad_ldap_base, ad_ldap_binddn, ad_ldap_bindpw, ad_ldap_certificate, listener_dir, init_group_cache=True):

		univention.connector.ucs.__init__(self, CONFIGBASENAME, property, baseConfig, listener_dir)

		self.CONFIGBASENAME = CONFIGBASENAME

		self.ad_ldap_host = ad_ldap_host
		self.ad_ldap_port = ad_ldap_port
		self.ad_ldap_base = ad_ldap_base
		self.ad_ldap_binddn = ad_ldap_binddn
		self.ad_ldap_bindpw = ad_ldap_bindpw
		self.ad_ldap_certificate = ad_ldap_certificate
		self.baseConfig = baseConfig


		self.open_ad()

		if not self.config.has_section('AD'):
			ud.debug(ud.LDAP, ud.INFO,"__init__: init add config section 'AD'")
			self.config.add_section('AD')

		if not self.config.has_section('AD rejected'):
			ud.debug(ud.LDAP, ud.INFO,"__init__: init add config section 'AD rejected'")
			self.config.add_section('AD rejected')
			
		if not self.config.has_option('AD','lastUSN'):
			ud.debug(ud.LDAP, ud.INFO,"__init__: init lastUSN with 0")
			self._set_config_option('AD','lastUSN','0')
			self.__lastUSN=0
		else:
			self.__lastUSN=int(self._get_config_option('AD','lastUSN'))

		if not self.config.has_section('AD GUID'):
			ud.debug(ud.LDAP, ud.INFO,"__init__: init add config section 'AD GUID'")
			self.config.add_section('AD GUID')

		# Build an internal cache with AD as key and the UCS object as cache
		self.group_mapping_cache_ucs = {}
		self.group_mapping_cache_con = {}
		
		# Save the old members of a group
		# 	lower dn as key and members as dn list
		self.group_members_cache_ucs = {}
		self.group_members_cache_con = {}

		if init_group_cache:
			ud.debug(ud.LDAP, ud.PROCESS, 'Building internal group membership cache')
			ad_groups = self.__search_ad( filter='objectClass=group', attrlist=['member'])
			ud.debug(ud.LDAP, ud.INFO,"__init__: ad_groups: %s" % ad_groups)
			for ad_group in ad_groups:
				if not ad_group or not ad_group[0]:
					continue
				group = ad_group[0].lower()
				self.group_members_cache_con[group] = []
				if ad_group[1]:
					for member in ad_group[1].get('member'):
						self.group_members_cache_con[group].append(member.lower())
			ud.debug(ud.LDAP, ud.INFO,"__init__: self.group_members_cache_con: %s" % self.group_members_cache_con)

			ucs_groups = self.search_ucs( filter='objectClass=univentionGroup', attr=['uniqueMember'])
			for ucs_group in ucs_groups:
				group = ucs_group[0].lower()
				self.group_members_cache_ucs[group] = []
				if ucs_group[1]:
					for member in ucs_group[1].get('uniqueMember'):
						self.group_members_cache_ucs[group].append(member.lower())
			ud.debug(ud.LDAP, ud.INFO,"__init__: self.group_members_cache_ucs: %s" % self.group_members_cache_ucs)

			ud.debug(ud.LDAP, ud.PROCESS, 'Internal group membership cache was created')
			
		try:
			self.ad_sid = univention.connector.ad.decode_sid(
				self.lo_ad.lo.search_ext_s(ad_ldap_base,ldap.SCOPE_BASE,
										   'objectclass=domain',['objectSid'],
										   timeout=-1, sizelimit=0)[0][1]['objectSid'][0])
			
		except Exception, msg:
			print "Failed to get SID from AD: %s" % msg
			sys.exit(1)

	def open_ad(self):
		tls_mode = 2
		if self.baseConfig.has_key('%s/ad/ldap/ssl' % self.CONFIGBASENAME) and self.baseConfig['%s/ad/ldap/ssl' % self.CONFIGBASENAME] == "no":
			ud.debug(ud.LDAP, ud.INFO,"__init__: The LDAP connection to AD does not use SSL (switched off by UCR \"%s/ad/ldap/ssl\")." % self.CONFIGBASENAME)
			tls_mode = 0

		ldaps = self.baseConfig.is_true('%s/ad/ldap/ldaps' % self.CONFIGBASENAME, False) # tls or ssl

		self.lo_ad=univention.uldap.access(host=self.ad_ldap_host, port=int(self.ad_ldap_port), base=self.ad_ldap_base, binddn=self.ad_ldap_binddn, bindpw=self.ad_ldap_bindpw, start_tls=tls_mode, use_ldaps = ldaps, ca_certfile=self.ad_ldap_certificate, decode_ignorelist=['objectSid', 'objectGUID', 'repsFrom', 'replUpToDateVector', 'ipsecData', 'logonHours', 'userCertificate', 'dNSProperty', 'dnsRecord', 'member'])

		self.lo_ad.lo.set_option(ldap.OPT_REFERRALS,0)

	# encode string to unicode
	def encode(self, string):
		try:
			return unicode(string)
		except: # FIXME: which exception is to be caught?
			return unicode(string, 'Latin-1')
			
	def _get_lastUSN(self):
		_d=ud.function('ldap._get_lastUSN')
		return max(self.__lastUSN, int(self._get_config_option('AD','lastUSN')))
	
	def get_lastUSN(self):
		return self._get_lastUSN()

	def _commit_lastUSN(self):
		_d=ud.function('ldap._commit_lastUSN')
		self._set_config_option('AD','lastUSN',str(self.__lastUSN))

	def _set_lastUSN(self, lastUSN):
		_d=ud.function('ldap._set_lastUSN')
		ud.debug(ud.LDAP, ud.INFO,"_set_lastUSN: new lastUSN is: %s" % lastUSN)
		self.__lastUSN=lastUSN

	# save ID's
	def __check_base64(self,string):
		# check if base64 encoded string string has correct length
		if not len(string) & 3 == 0:
			string = string + "="*(4 - len(string) & 3)
		return string

	def __encode_GUID(self, GUID):
		# GUID may be unicode
		if type(GUID) == type(u''):
			return GUID.encode('ISO-8859-1').encode('base64')
		else:
			return unicode(GUID,'latin').encode('ISO-8859-1').encode('base64')

	def _get_DN_for_GUID(self,GUID):
		_d=ud.function('ldap._get_DN_for_GUID')
		return self._decode_dn_from_config_option(self._get_config_option('AD GUID', self.__encode_GUID(GUID)))
		
		
	def _set_DN_for_GUID(self,GUID,DN):
		_d=ud.function('ldap._set_DN_for_GUID')
		self._set_config_option('AD GUID', self.__encode_GUID(GUID), self._encode_dn_as_config_option(DN))

	def _remove_GUID(self,GUID):
		_d=ud.function('ldap._remove_GUID')
		self._remove_config_option('AD GUID', self.__encode_GUID(GUID))

## handle rejected Objects

	def _save_rejected(self, id, dn):
		_d=ud.function('ldap._save_rejected')
		try:
			self._set_config_option('AD rejected',str(id),compatible_modstring(dn))
		except UnicodeEncodeError, msg:
			self._set_config_option('AD rejected',str(id),'unknown')
			self._debug_traceback(ud.WARN,
					      "failed to set dn in configfile (AD rejected)")

	def _get_rejected(self, id):
		_d=ud.function('ldap._get_rejected')
		return self._get_config_option('AD rejected',str(id))

	def _remove_rejected(self,id):
		_d=ud.function('ldap._remove_rejected')
		self._remove_config_option('AD rejected',str(id))

	def _list_rejected(self):
		_d=ud.function('ldap._list_rejected')
		result = []
		for i in self._get_config_items('AD rejected'):
			result.append(i)
		return result

	def list_rejected(self):
		return self._list_rejected()

	def save_rejected(self, object):
		"""
		save object as rejected
		"""
		_d=ud.function('ldap.save_rejected')
		self._save_rejected(self.__get_change_usn(object),object['dn'])

	def remove_rejected(self, object):
		"""
		remove object from rejected
		"""
		_d=ud.function('ldap.remove_rejected')
		self._remove_rejected(self.__get_change_usn(object),object['dn'])


	def get_object(self, dn):
		_d=ud.function('ldap.get_object')
		try:
			dn, ad_object=self.lo_ad.lo.search_ext_s(compatible_modstring(dn),ldap.SCOPE_BASE,'(objectClass=*)')[0]
			try:
				ud.debug(ud.LDAP, ud.INFO,"get_object: got object: %s" % dn)
			except: # FIXME: which exception is to be caught?
				ud.debug(ud.LDAP, ud.INFO,"get_object: got object: <print failed>")
			return encode_ad_object(ad_object)
		except (ldap.SERVER_DOWN, SystemExit):
			raise
		except: # FIXME: which exception is to be caught?
			pass
		

	def __get_change_usn(self, object):
		'''
		get change usn as max(uSNCreated,uSNChanged)
		'''
		_d=ud.function('ldap.__get_change_usn')
		if not object:
			return 0
		usnchanged=0
		usncreated=0		
		if object['attributes'].has_key('uSNCreated'):
			usncreated = int(object['attributes']['uSNCreated'][0])
		if object['attributes'].has_key('uSNChanged'):
			usnchanged = int(object['attributes']['uSNChanged'][0])

		return max(usnchanged,usncreated)

	def __search_ad(self, base=None, scope=ldap.SCOPE_SUBTREE, filter='', attrlist= [], show_deleted=False):
		'''
		search ad
		'''
		_d=ud.function('ldap.__search_ad')

		if not base:
			base=self.lo_ad.base

		ctrls=[]
		ctrls.append(SimplePagedResultsControl(ldap.LDAP_CONTROL_PAGE_OID,True,(PAGE_SIZE,'')))

		if show_deleted:
			# LDAP_SERVER_SHOW_DELETED_OID -> 1.2.840.113556.1.4.417
			ctrls.append(LDAPControl('1.2.840.113556.1.4.417',criticality=1))

		ud.debug(ud.LDAP, ud.INFO, "Search AD with filter: %s" % filter)
		msgid = self.lo_ad.lo.search_ext(base, scope, filter, attrlist, serverctrls=ctrls, timeout=-1, sizelimit=0)

		res = []
		pages = 0
		while True:
			pages += 1
			rtype, rdata, rmsgid, serverctrls = self.lo_ad.lo.result3(msgid)
			res += rdata

			pctrls = [
				c
				for c in serverctrls
				if c.controlType == ldap.LDAP_CONTROL_PAGE_OID
			]
			if pctrls:
				est, cookie = pctrls[0].controlValue
				if cookie:
					if pages > 1:
						ud.debug(ud.LDAP, ud.PROCESS, "AD search continues, already found %s objects" % len(res))
					ctrls[0].controlValue = (PAGE_SIZE, cookie)
					msgid = self.lo_ad.lo.search_ext(base, scope, filter, attrlist, serverctrls=ctrls, timeout=-1, sizelimit=0)
				else:
					break
			else:
				ud.debug(ud.LDAP, ud.WARN, "AD ignores PAGE_RESULTS")
				break

		
		return encode_ad_resultlist(res)
		

	def __search_ad_changes(self, show_deleted=False, filter=''):
		'''
		search ad for changes since last update (changes greater lastUSN)
		'''
		_d=ud.function('ldap.__search_ad_changes')
		lastUSN = self._get_lastUSN()
		# filter erweitern um "(|(uSNChanged>=lastUSN+1)(uSNCreated>=lastUSN+1))"
		# +1 da suche nur nach '>=', nicht nach '>' möglich

		def search_ad_changes_by_attribute( attribute, lowerUSN, higherUSN = '' ):
			if higherUSN:
				usnFilter = '(&(%s>=%s)(%s<=%s))' % (attribute, lowerUSN, attribute, higherUSN)
			else:
				usnFilter = '(%s>=%s)' % (attribute, lowerUSN)

			if filter !='':
				usnFilter = '(&(%s)(%s))' % ( filter, usnFilter )
				
			return self.__search_ad( filter=usnFilter, show_deleted=show_deleted)


		# search fpr objects with uSNCreated and uSNChanged in the known range

		returnObjects = []
		try:
			if lastUSN > 0:
				# During the init phase we have to search for created and changed objects
				# but we need to sync the objects only once
				returnObjects = search_ad_changes_by_attribute( 'uSNCreated', lastUSN+1 )
				for changedObject in search_ad_changes_by_attribute( 'uSNChanged', lastUSN+1 ):
					if changedObject not in returnObjects:
						returnObjects.append(changedObject)
			else:
				# Every object has got a uSNCreated
				returnObjects = search_ad_changes_by_attribute( 'uSNCreated', lastUSN+1 )
		except (ldap.SERVER_DOWN, SystemExit):		
			raise
		except ldap.SIZELIMIT_EXCEEDED:
			# The LDAP control page results was not sucessful. Without this control 
			# AD does not return more than 1000 results. We are going to split the
			# search.
			highestCommittedUSN = self.__get_highestCommittedUSN()
			tmpUSN=lastUSN
			ud.debug(ud.LDAP, ud.PROCESS,
					       "Need to split results. highest USN is %s, lastUSN is %s"%(highestCommittedUSN,lastUSN))
			while (tmpUSN != highestCommittedUSN):
				lastUSN=tmpUSN
				tmpUSN+=999
				if tmpUSN > highestCommittedUSN:
					tmpUSN=highestCommittedUSN

				ud.debug(ud.LDAP, ud.INFO, "__search_ad_changes: search between USNs %s and %s"%(lastUSN+1,tmpUSN))

				if lastUSN > 0:
					returnObjects += search_ad_changes_by_attribute( 'uSNCreated', lastUSN+1, tmpUSN )
					for changedObject in search_ad_changes_by_attribute( 'uSNChanged', lastUSN+1, tmpUSN ):
						if changedObject not in returnObjects:
							returnObjects.append(changedObject)
				else:
					# Every object has got a uSNCreated
					returnObjects += search_ad_changes_by_attribute( 'uSNCreated', lastUSN+1, tmpUSN )
				
		return returnObjects

	def __search_ad_changeUSN(self, changeUSN, show_deleted=True, filter=''):
		'''
		search ad for change with id
		'''
		_d=ud.function('ldap.__search_ad_changeUSN')
		if filter != '':
			filter = '(&(%s)(|(uSNChanged=%s)(uSNCreated=%s)))' % (filter,changeUSN,changeUSN)
		else:
			filter = '(|(uSNChanged=%s)(uSNCreated=%s))' % (changeUSN,changeUSN)
		return self.__search_ad(filter=filter, show_deleted=show_deleted)


	def __dn_from_deleted_object(self, object, GUID):
		'''
		gets dn for deleted object (original dn before the object was moved into the deleted objects container)
		'''
		_d=ud.function('ldap.__dn_from_deleted_object')

		# FIXME: should be called recursively, if containers are deleted subobjects have lastKnowParent in deletedObjects
 		rdn = object['dn'][:string.find(object['dn'],'DEL:')-3]
 		if object['attributes'].has_key('lastKnownParent'):
			try:
				ud.debug(ud.LDAP, ud.INFO, "__dn_from_deleted_object: get DN from lastKnownParent (%s) and rdn (%s)"
						       % (object['attributes']['lastKnownParent'][0], rdn))
			except: # FIXME: which exception is to be caught?
				ud.debug(ud.LDAP, ud.INFO, "__dn_from_deleted_object: get DN from lastKnownParent")
 			return rdn + "," + object['attributes']['lastKnownParent'][0]							
 		else:
 			ud.debug(ud.LDAP, ud.WARN, 'lastKnownParent attribute for deleted object rdn="%s" was not set, so we must ignore the object' % rdn )
 			return None

	def __object_from_element(self, element):
		"""
		gets an object from an LDAP-element, implements necessary mapping

		"""
		_d=ud.function('ldap.__object_from_element')
		if element[0] == 'None' or element[0] == None:
			return None # referrals
		object = {}
		object['dn'] = self.encode(element[0])
		deleted_object = False
		GUID = element[1]['objectGUID'][0] # don't send this GUID to univention-debug

		# modtype
		if element[1].has_key('isDeleted') and element[1]['isDeleted'][0] == 'TRUE':
			object['modtype'] = 'delete'
			deleted_object = True

		else:
			#check if is moved
			olddn = self.encode(self._get_DN_for_GUID(GUID))
			ud.debug(ud.LDAP, ud.INFO, "object_from_element: olddn: %s"%olddn)
			if olddn and not compatible_modstring(olddn).lower() == compatible_modstring(self.encode(element[0])).lower() and ldap.explode_rdn(compatible_modstring(olddn).lower()) == ldap.explode_rdn(compatible_modstring(self.encode(element[0])).lower()): 
				object['modtype'] = 'move'
				object['olddn'] = olddn
				ud.debug(ud.LDAP, ud.INFO, "object_from_element: detected move of AD-Object")
			else:
				object['modtype'] = 'modify'
				if olddn and not compatible_modstring(olddn).lower() == compatible_modstring(self.encode(element[0])).lower(): # modrdn
					object['olddn'] = olddn
				

		object['attributes'] = element[1]
		for key in object['attributes'].keys():
			vals = []
			for value in object['attributes'][key]:
				vals.append(self.encode(value))
			object['attributes'][key] = vals	

		
			
		if deleted_object: # dn is in deleted-objects-container, need to parse to original dn
			object['deleted_dn'] = object['dn']
			object['dn'] = self.__dn_from_deleted_object(object, GUID)
			ud.debug(ud.LDAP, ud.INFO, "object_from_element: DN of removed object: %s" % object['dn'])
			#self._remove_GUID(GUID) # cache is not needed anymore?
			
			if not object['dn']:
				return None
		return object

	def __identify(self, object):
		_d=ud.function('ldap.__identify')
		if not object or not object.has_key('attributes'):
			return None
		for key in self.property.keys():
			if self._filter_match(self.property[key].con_search_filter,object['attributes']):
				return key

	def __update_lastUSN(self, object):
		"""
		Update der lastUSN
		"""
		_d=ud.function('ldap.__update_lastUSN')
		if self.__get_change_usn(object) > self._get_lastUSN():
			self._set_lastUSN(self.__get_change_usn(object))

	def __get_highestCommittedUSN(self):
		'''
		get highestCommittedUSN stored in AD
		'''
		_d=ud.function('ldap.__get_highestCommittedUSN')
		try:
			res=self.lo_ad.lo.search_ext_s('', # base
				 ldap.SCOPE_BASE,
				 'objectclass=*', # filter
				 ['highestCommittedUSN'],
				 timeout=-1, sizelimit=0)[0][1]['highestCommittedUSN'][0]

			return int(res)
		except Exception, msg:
			self._debug_traceback(ud.ERROR,
								  "search for highestCommittedUSN failed")
			print "ERROR: initial search in AD failed, check network and configuration"
			return 0

	def set_primary_group_to_ucs_user(self, object_key, object_ucs):
		'''
		check if correct primary group is set to a fresh UCS-User
		'''
		_d=ud.function('ldap.set_primary_group_to_ucs_user')

		ad_group_rid_resultlist = self.__search_ad(base=self.lo_ad.base, scope=ldap.SCOPE_SUBTREE, filter='samaccountname=%s' % compatible_modstring(object_ucs['username']), attrlist=['dn', 'primaryGroupID'])

		if not ad_group_rid_resultlist[0][0] in ['None','',None]:

			ad_group_rid = ad_group_rid_resultlist[0][1]['primaryGroupID'][0]

			ud.debug(ud.LDAP, ud.INFO,
								   "set_primary_group_to_ucs_user: AD rid: %s"%ad_group_rid)
			object_sid_string = str(self.ad_sid) + "-" + str(ad_group_rid)

			ldap_group_ad = self.__search_ad( base=self.lo_ad.base, scope=ldap.SCOPE_SUBTREE, filter="objectSid=" + object_sid_string)

			if not ldap_group_ad[0][0]:
				ud.debug(ud.LDAP, ud.ERROR, "ad.set_primary_group_to_ucs_user: Primary Group in AD not found (not enough rights?), sync of this object will fail!")
			ucs_group = self._object_mapping('group',{'dn':ldap_group_ad[0][0],'attributes':ldap_group_ad[0][1]}, object_type='con')


			object_ucs['primaryGroup'] = ucs_group['dn']

	def primary_group_sync_from_ucs(self, key, object): # object mit ad-dn
		'''
		sync primary group of an ucs-object to ad
		'''
		_d=ud.function('ldap.primary_group_sync_from_ucs')

		object_key = key
		object_ucs = self._object_mapping(object_key,object)

		ldap_object_ucs = self.get_ucs_ldap_object(object_ucs['dn'])
		if not ldap_object_ucs:
			ud.debug(ud.LDAP, ud.PROCESS, 'primary_group_sync_from_ucs: The UCS object (%s) was not found. The object was removed.' % object_ucs['dn'])
			return
			
		ldap_object_ad = self.get_object(object['dn'])
		if not ldap_object_ad:
			ud.debug(ud.LDAP, ud.PROCESS, 'primary_group_sync_from_ucs: The AD object (%s) was not found. The object was removed.' % object['dn'])
			return
		
		ucs_group_id = ldap_object_ucs['gidNumber'][0] # FIXME: fails if group does not exsist
		ucs_group_ldap = self.search_ucs(filter='(&(objectClass=univentionGroup)(gidNumber=%s))' % ucs_group_id) # is empty !?

		if ucs_group_ldap == []:
			ud.debug(ud.LDAP, ud.WARN,
								   "primary_group_sync_from_ucs: failed to get UCS-Group with gid %s, can't sync to AD"%ucs_group_id)
			return


		member_key = 'group' # FIXME: generate by identify-function ?
		ad_group_object = self._object_mapping(member_key, {'dn':ucs_group_ldap[0][0], 'attributes': ucs_group_ldap[0][1]}, 'ucs')
		ldap_object_ad_group = self.get_object(ad_group_object['dn'])
		rid = "513" # FIXME: Fallback: should be configurable
		if ldap_object_ad_group and ldap_object_ad_group.has_key('objectSid'):
			sid = ldap_object_ad_group['objectSid'][0]
			rid = sid[string.rfind(sid,"-")+1:]
		else:
			print "no SID !!!"

		# to set a valid primary group we need to:
		# - check if either the primaryGroupID is already set to rid or
		# - proove that the user is member of this group, so: at first we need the ad_object for this element
		# this means we need to map the user to get it's AD-DN which would call this function recursively

		if ldap_object_ad.has_key("primaryGroupID") and ldap_object_ad["primaryGroupID"][0] == rid:
			ud.debug(ud.LDAP, ud.INFO,
								   "primary_group_sync_from_ucs: primary Group is correct, no changes needed")
			return True # nothing left to do
		else:
			is_member = False
			if ldap_object_ad_group.has_key('member'):
				for member in ldap_object_ad_group['member']:
					if compatible_modstring(object['dn']).lower() == compatible_modstring(member).lower():
						is_member = True
						break

			if not is_member: # add as member
				ad_members = []
				if ldap_object_ad_group.has_key('member'):
					for member in ldap_object_ad_group['member']:
						ad_members.append(compatible_modstring(member))
				ad_members.append(compatible_modstring(object['dn']))
				self.lo_ad.lo.modify_s(compatible_modstring(ad_group_object['dn']),[(ldap.MOD_REPLACE, 'member', ad_members)])
				ud.debug(ud.LDAP, ud.INFO,
									   "primary_group_sync_from_ucs: primary Group needed change of membership in AD")
				
			# set new primary group
			self.lo_ad.lo.modify_s(compatible_modstring(object['dn']),[(ldap.MOD_REPLACE, 'primaryGroupID', rid)])
			ud.debug(ud.LDAP, ud.INFO,
								   "primary_group_sync_from_ucs: changed primary Group in AD")

			# If the user is not member in UCS of the previous primary group, the user must
			# be removed from this group in AD: https://forge.univention.org/bugzilla/show_bug.cgi?id=26809
			prev_samba_primary_group_id = ldap_object_ad.get('primaryGroupID', [])[0]
			object_sid_string = str(self.ad_sid) + "-" + str(prev_samba_primary_group_id)
			ad_group = self.__search_ad( base=self.lo_ad.base, scope=ldap.SCOPE_SUBTREE, filter='objectSid=%s' % object_sid_string)
			ucs_group_object = self._object_mapping('group', {'dn':ad_group[0][0], 'attributes': ad_group[0][1]}, 'con')
			ucs_group = self.get_ucs_ldap_object(ucs_group_object['dn'])
			is_member = False
			for member in ucs_group.get('uniqueMember', []):
				if member.lower() == object_ucs['dn'].lower():
					is_member = True
					break
			if not is_member:
				# remove AD member from previous group
				self.lo_ad.lo.modify_s(ad_group[0][0],[(ldap.MOD_DELETE, 'member', [compatible_modstring(object['dn'])])])
			
			return True

	def primary_group_sync_to_ucs(self, key, object): # object mit ucs-dn
		'''
		sync primary group of an ad-object to ucs
		'''
		_d=ud.function('ldap.primary_group_sync_to_ucs')

		object_key = key

		ad_object = self._object_mapping(object_key,object,'ucs')
		ldap_object_ad = self.get_object(ad_object['dn'])
		ad_group_rid = ldap_object_ad['primaryGroupID'][0]
		ud.debug(ud.LDAP, ud.INFO,
							   "primary_group_sync_to_ucs: AD rid: %s"%ad_group_rid)

		object_sid_string = str(self.ad_sid) + "-" + str(ad_group_rid)

		ldap_group_ad = self.__search_ad( base=self.lo_ad.base, scope=ldap.SCOPE_SUBTREE, filter='objectSID=' + object_sid_string)


		ucs_group = self._object_mapping('group',{'dn':ldap_group_ad[0][0],'attributes':ldap_group_ad[0][1]})

		ud.debug(ud.LDAP, ud.INFO,
							   "primary_group_sync_to_ucs: ucs-group: %s" % ucs_group['dn'])

		ucs_admin_object=univention.admin.objects.get(self.modules[object_key], co='', lo=self.lo, position='', dn=object['dn'])
		ucs_admin_object.open()

		if not ucs_admin_object['primaryGroup'].lower() == ucs_group['dn'].lower():
			# need to set to dn with correct case or the ucs-module will fail
			new_group = ucs_group['dn'].lower()
			ucs_admin_object['primaryGroup'] = new_group
			ucs_admin_object.modify()

			ud.debug(ud.LDAP, ud.INFO,
								   "primary_group_sync_to_ucs: changed primary Group in ucs")
		else:
			ud.debug(ud.LDAP, ud.INFO,
								   "primary_group_sync_to_ucs: change of primary Group in ucs not needed")
		
	def object_memberships_sync_from_ucs(self, key, object):
		"""
		sync group membership in AD if object was changend in UCS
		"""
		_d=ud.function('ldap.object_memberships_sync_from_ucs')
		ud.debug(ud.LDAP, ud.INFO,
				       "object_memberships_sync_from_ucs: object: %s" % object)

		# search groups in UCS which have this object as member

		object_ucs = self._object_mapping(key, object)

		# Exclude primary group
		ucs_groups_ldap = self.search_ucs(filter='(&(objectClass=univentionGroup)(uniqueMember=%s)(!(gidNumber=%s)))' % (object_ucs['dn'], object_ucs['attributes'].get('gidNumber', [])[0]))

		if ucs_groups_ldap == []:
			ud.debug(ud.LDAP, ud.INFO,
					       "object_memberships_sync_from_ucs: No group-memberships in UCS for %s" % object['dn'])
			return

		ud.debug(ud.LDAP, ud.INFO,
				       "object_memberships_sync_from_ucs: is member in %s groups " % len(ucs_groups_ldap))
		for groupDN, attributes in ucs_groups_ldap:
			if groupDN not in ['None','',None]:
				ad_object = { 'dn' : groupDN, 'attributes': attributes, 'modtype': 'modify'}
				if not self._ignore_object( 'group', ad_object ):
					sync_object = self._object_mapping( 'group' , ad_object, 'ucs' )
					sync_object_ad = self.get_object( sync_object['dn'] )
					ad_group_object = {'dn': sync_object['dn'], 'attributes': sync_object_ad }
					if sync_object_ad:
						# self.group_members_sync_from_ucs( 'group', sync_object )
						self.one_group_member_sync_from_ucs(ad_group_object, object  )

			ud.debug(ud.LDAP, ud.INFO, "object_memberships_sync_to_ucs: Append user %s to group ucs cache of %s" % (object_ucs['dn'].lower(), groupDN.lower()))
			if not self.group_members_cache_ucs.get(groupDN.lower()):
				self.group_members_cache_ucs[groupDN.lower()] = []
			self.group_members_cache_ucs[groupDN.lower()].append(object_ucs['dn'].lower())
		

	def group_members_sync_from_ucs(self, key, object): # object mit ad-dn
		"""
		sync groupmembers in AD if changend in UCS
		"""
		_d=ud.function('ldap.group_members_sync_from_ucs')

		ud.debug(ud.LDAP, ud.INFO,"group_members_sync_from_ucs: %s"%object)

		object_key = key
		object_ucs = self._object_mapping(object_key,object)

		ud.debug(ud.LDAP, ud.INFO,"group_members_sync_from_ucs: type of object_ucs['dn']: %s"%type(object_ucs['dn']))
		ud.debug(ud.LDAP, ud.INFO,"group_members_sync_from_ucs: dn is: %s"%object_ucs['dn'])
		ldap_object_ucs = self.get_ucs_ldap_object(object_ucs['dn'])

		if not ldap_object_ucs:
			ud.debug(ud.LDAP, ud.PROCESS, 'group_members_sync_from_ucs:: The UCS object (%s) was not found. The object was removed.' % object_ucs['dn'])
			return

		if ldap_object_ucs.has_key('uniqueMember'):
			ucs_members = ldap_object_ucs['uniqueMember']
		else:
			ucs_members = []

		ud.debug(ud.LDAP, ud.INFO, "ucs_members: %s" % ucs_members)

		# remove members which have this group as primary group (set same gidNumber)
		prim_members_ucs = self.lo.lo.search(filter='gidNumber=%s'%ldap_object_ucs['gidNumber'][0],attr=['gidNumber'])
		

		# all dn's need to be lower-case so we can compare them later and put them in the group ucs cache:
		self.group_members_cache_ucs[object_ucs['dn'].lower()] = []
		ucs_members_lower = []
		for dn in ucs_members:
			ucs_members_lower.append(dn.lower())
			self.group_members_cache_ucs[object_ucs['dn'].lower()].append(dn.lower())

		ucs_members = ucs_members_lower
		
		for prim_object in prim_members_ucs:
			if  prim_object[0].lower() in ucs_members:
				ucs_members.remove(prim_object[0].lower())

		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: clean ucs_members: %s" % ucs_members)

		ldap_object_ad = self.get_object(object['dn'])
		if not ldap_object_ad:
			ud.debug(ud.LDAP, ud.PROCESS, 'group_members_sync_from_ucs:: The AD object (%s) was not found. The object was removed.' % object['dn'])
			return
		
		if ldap_object_ad and ldap_object_ad.has_key('member'):
			ad_members = ldap_object_ad['member']
		else:
			ad_members = []

		ud.debug(ud.LDAP, ud.INFO,
							   "group_members_sync_from_ucs: ad_members %s" % ad_members)

		ad_members_from_ucs = []

		# map members from UCS to AD and check if they exist
		for member_dn in ucs_members:
			ad_dn = self.group_mapping_cache_ucs.get(member_dn.lower())
			if ad_dn:
				ud.debug(ud.LDAP, ud.INFO, "Found %s in group cache ucs" % member_dn)
				ad_members_from_ucs.append(ad_dn.lower())
			else:
				ud.debug(ud.LDAP, ud.INFO, "Did not find %s in group cache ucs" % member_dn)
				member_object = {'dn':member_dn,'modtype':'modify','attributes':self.lo.get(member_dn)}

				# can't sync them if users have no posix-account
				if not member_object['attributes'].has_key('gidNumber'):
					continue

				# check if this is members primary group, if true it shouldn't be added to ad
				if member_object['attributes'].has_key('gidNumber') and ldap_object_ucs.has_key('gidNumber') and \
					   member_object['attributes']['gidNumber'] == ldap_object_ucs['gidNumber']:
					# is primary group
					continue
				
				#print 'member_object: %s '%member_object
				for k in self.property.keys():
					if self.modules[k].identify(member_dn, member_object['attributes']):
						key=k
						break
				#print 'object key: %s' % key
				ad_dn = self._object_mapping(key, member_object, 'ucs')['dn']
				# check if dn exists in ad
				try:
					if self.lo_ad.get(ad_dn,attr=['cn']): # search only for cn to suppress coding errors
						ad_members_from_ucs.append(ad_dn.lower())
						self.group_mapping_cache_ucs[member_dn.lower()] = ad_dn
				except (ldap.SERVER_DOWN, SystemExit):
					raise
				except:  # FIXME: which exception is to be caught?
					ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: failed to get dn from ad, assume object doesn't exist")

		ud.debug(ud.LDAP, ud.INFO,
							   "group_members_sync_from_ucs: UCS-members in ad_members_from_ucs %s" % ad_members_from_ucs)

		# check if members in AD don't exist in UCS, if true they need to be added in AD
		for member_dn in ad_members:
			if not member_dn.lower() in ad_members_from_ucs:
				try:
					ad_object = self.get_object(member_dn)					
					
					key = self.__identify({'dn':member_dn,'attributes':ad_object})
					ucs_dn = self._object_mapping(key, {'dn':member_dn,'attributes':ad_object})['dn']
					if not self.lo.get(ucs_dn, attr=['cn']):
						# ad_members_from_ucs.append(member_dn.lower())
						ud.debug(ud.LDAP, ud.INFO,
								       "group_members_sync_from_ucs: Object exists only in AD [%s]" % ucs_dn)			
					elif self._ignore_object(key,{'dn':member_dn,'attributes':ad_object}):
						ad_members_from_ucs.append(member_dn.lower())
						ud.debug(ud.LDAP, ud.INFO,
								       "group_members_sync_from_ucs: Object ignored in AD [%s], key = [%s]" % (ucs_dn,key))			
				except (ldap.SERVER_DOWN, SystemExit):
					raise
				except: # FIXME: which exception is to be caught?
					self._debug_traceback(ud.INFO, "group_members_sync_from_ucs: failed to get dn from ad which is groupmember")

		ud.debug(ud.LDAP, ud.INFO,
							   "group_members_sync_from_ucs: UCS-and AD-members in ad_members_from_ucs %s" % ad_members_from_ucs)

		# compare lists and generate modlist
		# direct compare is not possible, because ad_members_from_ucs are all lowercase, ad_members are not, so we need to iterate...
		# FIXME: should be done in the last iteration (above)

		# need to remove users from ad_members which have this group as primary group. may failed earlier if groupnames are mapped
		try:
			group_rid = decode_sid(self.lo_ad.lo.search_s(compatible_modstring(object['dn']), ldap.SCOPE_BASE,
								      '(objectClass=*)', ['objectSid'])[0][1]['objectSid'][0]).split('-')[-1]
		except ldap.NO_SUCH_OBJECT:
			group_rid = None

		if group_rid:
			# search for members who have this as their primaryGroup
			prim_members_ad = self.__search_ad( self.lo_ad.base,ldap.SCOPE_SUBTREE, 'primaryGroupID=%s'%group_rid, ['cn'])

			for prim_dn, prim_object in prim_members_ad:
				if not prim_dn in ['None','',None]: # filter referrals
					if prim_dn.lower() in ad_members_from_ucs:
						ad_members_from_ucs.remove(prim_dn.lower())
					elif prim_dn in ad_members_from_ucs:
						ad_members_from_ucs.remove(prim_dn)


		ud.debug(ud.LDAP, ud.INFO,
							   "group_members_sync_from_ucs: ad_members_from_ucs without members with this as their primary group: %s" % ad_members_from_ucs)

		add_members = ad_members_from_ucs
		del_members = []

		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: members to add initialized: %s" % add_members)
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: members to del initialized: %s" % del_members)

		for member_dn in ad_members:
			ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: %s in ad_members_from_ucs?" % member_dn)
			if member_dn.lower() in ad_members_from_ucs:
				ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: Yes")
				add_members.remove(member_dn.lower())
			else:
				# remove member only if he was in the cache
				# otherwise it is possible that the user was just created on UCS
				if member_dn.lower() in self.group_members_cache_con.get(object['dn'].lower(), [member_dn.lower()]):
					ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: No")
					del_members.append(member_dn)
				else:
					ud.debug(ud.LDAP, ud.PROCESS, "group_members_sync_from_ucs: %s was not found in group member con cache of %s, don't delete" % (member_dn.lower(), object['dn'].lower()))

		
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: members to add: %s" % add_members)
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: members to del: %s" % del_members)

		if add_members or del_members:
			ad_members = ad_members + add_members
			for member in del_members:
				ad_members.remove(member)
			ud.debug(ud.LDAP, ud.INFO, "group_members_sync_from_ucs: members result: %s" % ad_members)
			group_dn_lower = object_ucs['dn'].lower()
			self.group_members_cache_ucs[group_dn_lower] = []
			for member in ad_members:
				self.group_members_cache_ucs[group_dn_lower].append(member.lower())
			ud.debug(ud.LDAP, ud.INFO, "group_members_cache_ucs[%s]: %s" % (group_dn_lower, self.group_members_cache_ucs[group_dn_lower]))


			modlist_members = []
			for member in ad_members:
				modlist_members.append(compatible_modstring(member))

			try:
				self.lo_ad.lo.modify_s(compatible_modstring(object['dn']),[(ldap.MOD_REPLACE, 'member', modlist_members)])
			except (ldap.SERVER_DOWN, SystemExit):
				raise
			except: # FIXME: which exception is to be caught?
				ud.debug(ud.LDAP, ud.WARN,
						       "group_members_sync_from_ucs: failed to sync members: (%s,%s)" % (object['dn'],[(ldap.MOD_REPLACE, 'member', modlist_members)]))
				raise

			return True
		else:
			return True

	def object_memberships_sync_to_ucs(self, key, object):
		"""
		sync group membership in UCS if object was changend in AD
		"""
		_d=ud.function('ldap.object_memberships_sync_to_ucs')
		# disable this debug line, see Bug #12031
		# ud.debug(ud.LDAP, ud.INFO, "object_memberships_sync_to_ucs: object: %s" % object)

		object_ad = self._object_mapping(key, object)

		if object['attributes'].has_key('memberOf'):
			for groupDN in object['attributes']['memberOf']:
				ad_object = { 'dn' : groupDN, 'attributes': self.get_object(groupDN), 'modtype': 'modify'}
				if not self._ignore_object( 'group', ad_object ):
					sync_object = self._object_mapping( 'group' , ad_object )
					ldap_object_ucs = self.get_ucs_ldap_object( sync_object['dn'] )
					ucs_group_object = {'dn': sync_object['dn'], 'attributes': ldap_object_ucs }
					ud.debug(ud.LDAP, ud.INFO, "object_memberships_sync_to_ucs: sync_object: %s" % ldap_object_ucs)
					# check if group exists in UCS, may fail
					# if the group will be synced later
					if ldap_object_ucs:
						self.one_group_member_sync_to_ucs( ucs_group_object, object )

				if not self.group_members_cache_con.get(groupDN.lower()):
					self.group_members_cache_con[groupDN.lower()] = []
				dn = object['attributes'].get('distinguishedName', [None])[0]
				if dn:
					ud.debug(ud.LDAP, ud.INFO, "object_memberships_sync_to_ucs: Append user %s to group con cache of %s" % (dn.lower(), groupDN.lower()))
					self.group_members_cache_con[groupDN.lower()].append(dn.lower())
				else:
					ud.debug(ud.LDAP, ud.INFO, "object_memberships_sync_to_ucs: Failed to append user %s to group con cache of %s" % (object['dn'].lower(), groupDN.lower()))

	def __compare_lowercase(self, dn, dn_list):
		"""
		Checks if dn is in dn_list
		"""
		for d in dn_list:
			if dn.lower() == d.lower():
				return True
		return False

	def one_group_member_sync_to_ucs(self, ucs_group_object, object):
		"""
		sync groupmembers in UCS if changend one member in AD
		"""
		# In AD the object['dn'] is member of the group sync_object

		ml = []
		if not self.__compare_lowercase(object['dn'], ucs_group_object['attributes'].get('uniqueMember', [])):
			ml.append((ldap.MOD_ADD, 'uniqueMember', [object['dn']]))

		if object['attributes'].get('uid'):
			uid=object['attributes'].get('uid', [])[0]
			if not self.__compare_lowercase(uid, ucs_group_object['attributes'].get('memberUid', [])):
				ml.append((ldap.MOD_ADD, 'memberUid', [uid]))

		if ml:
			try:
				self.lo.lo.modify_s(ucs_group_object['dn'],compatible_modlist(ml))
			except ldap.ALREADY_EXISTS:
				# The user is already member in this group or it is his primary group
				# This might happen, if we synchronize a rejected file with old informations
				# See Bug #25709 Comment #17: https://forge.univention.org/bugzilla/show_bug.cgi?id=25709#c17
				ud.debug(ud.LDAP, ud.INFO, "one_group_member_sync_to_ucs: User is already member of the group: %s modlist: %s" % (ucs_group_object['dn'], ml))
				pass

		# The user has been removed from the cache. He must be added in any case
		if not self.group_members_cache_ucs.get(ucs_group_object['dn'].lower()):
			self.group_members_cache_ucs[ucs_group_object['dn'].lower()] = []
		ud.debug(ud.LDAP, ud.INFO, "one_group_member_sync_to_ucs: Append user %s to group ucs cache of %s" % (object['dn'].lower(), ucs_group_object['dn'].lower()))
		self.group_members_cache_ucs[ucs_group_object['dn'].lower()].append(object['dn'].lower())

	def one_group_member_sync_from_ucs(self, ad_group_object, object):
		"""
		sync groupmembers in AD if changend one member in AD
		"""
		ml = []
		if not self.__compare_lowercase(object['dn'], ad_group_object['attributes'].get('member', [])):
			ml.append((ldap.MOD_ADD, 'member', [object['dn']]))

		if ml:
			try:
				self.lo_ad.lo.modify_s(ad_group_object['dn'],compatible_modlist(ml))
			except ldap.ALREADY_EXISTS:
				# The user is already member in this group or it is his primary group
				# This might happen, if we synchronize a rejected file with old informations
				# See Bug #25709 Comment #17: https://forge.univention.org/bugzilla/show_bug.cgi?id=25709#c17
				ud.debug(ud.LDAP, ud.INFO, "one_group_member_sync_from_ucs: User is already member of the group: %s modlist: %s" % (ad_group_object['dn'], ml))
				pass

		# The user has been removed from the cache. He must be added in any case
		ud.debug(ud.LDAP, ud.INFO, "one_group_member_sync_from_ucs: Append user %s to group con cache of %s" % (object['dn'].lower(), ad_group_object['dn'].lower()))
		if not self.group_members_cache_con.get(ad_group_object['dn'].lower()):
			self.group_members_cache_con[ad_group_object['dn'].lower()] = []
		self.group_members_cache_con[ad_group_object['dn'].lower()].append(object['dn'].lower())
		
	def group_members_sync_to_ucs(self, key, object):
		"""
		sync groupmembers in UCS if changend in AD
		"""
		_d=ud.function('ldap.group_members_sync_to_ucs')
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: object: %s" % object)

		object_key = key

		ad_object = self._object_mapping(object_key,object,'ucs')
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: ad_object (mapped): %s" % ad_object)
		
		ldap_object_ucs = self.get_ucs_ldap_object(object['dn'])
		if ldap_object_ucs.has_key('uniqueMember'):
			ucs_members = ldap_object_ucs['uniqueMember']
		else:
			ucs_members = []
		ud.debug(ud.LDAP, ud.INFO,"group_members_sync_to_ucs: ucs_members: %s" % ucs_members)

		# FIXME: does not use dn-mapping-function
		ldap_object_ad = self.get_object(ad_object['dn']) # FIXME: may fail if object doesn't exist
		if ldap_object_ad and ldap_object_ad.has_key('member'):
			ad_members = ldap_object_ad['member']
		else:
			ad_members = []

		# set _con cache members
		self.group_members_cache_con[ad_object['dn'].lower()] = []
		for member in ad_members:
			ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: Append user %s to group con cache of %s" % (member.lower(), ad_object['dn'].lower()))
			self.group_members_cache_con[ad_object['dn'].lower()].append(member.lower())

		group_sid = ldap_object_ad['objectSid'][0]
		group_rid = group_sid[string.rfind(group_sid,"-")+1:]

		# search for members who have this as their primaryGroup
		prim_members_ad = encode_ad_resultlist(self.lo_ad.lo.search_ext_s(self.lo_ad.base,ldap.SCOPE_SUBTREE,
							     'primaryGroupID=%s'%group_rid,
							     timeout=-1, sizelimit=0))


		for prim_dn, prim_object in prim_members_ad:
			if not prim_dn in ['None','',None]: # filter referrals
				ad_members.append(prim_dn)

		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: ad_members %s" % ad_members)

		ucs_members_from_ad = { 'user' : [], 'group': [], 'unknown': [] }
		
		# map members from AD to UCS and check if they exist
		for member_dn in ad_members:
			ucs_dn = self.group_mapping_cache_con.get(member_dn.lower())
			if ucs_dn:
				ud.debug(ud.LDAP, ud.INFO, "Found %s in group cache ad: DN: %s" % (member_dn, ucs_dn))
				ucs_members_from_ad['unknown'].append(ucs_dn.lower())
			else:
				ud.debug(ud.LDAP, ud.INFO, "Did not find %s in group cache ad" % member_dn)
				member_object = self.get_object(member_dn)
				if member_object:
					mo_key = self.__identify({'dn':member_dn,'attributes':member_object})
					if not mo_key:
						ud.debug(ud.LDAP, ud.WARN, "group_members_sync_to_ucs: failed to identify object type of ad member, ignore membership: %s" % member_dn)
						continue # member is an object which will not be synced
					if self._ignore_object(mo_key, {'dn':member_dn,'attributes':member_object} ):
						ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: Object dn %s should be ignored, ignore membership" % member_dn)
						continue

					ucs_dn = self._object_mapping(key, {'dn':member_dn,'attributes':member_object})['dn']
					ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: mapped ad member to ucs DN %s" % ucs_dn)

					try:
						if self.lo.get(ucs_dn):
							ucs_members_from_ad['unknown'].append(ucs_dn.lower())
							self.group_mapping_cache_con[member_dn.lower()] = ucs_dn
						else:
							ud.debug(ud.LDAP, ud.INFO, "Failed to find %s via self.lo.get" % ucs_dn)
					except (ldap.SERVER_DOWN, SystemExit):
						raise
					except: # FIXME: which exception is to be caught?
						ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: failed to get dn from ucs, assume object doesn't exist")
				
		# build an internal cache
		cache={}

		# check if members in UCS don't exist in AD, if true they need to be added in UCS
		for member_dn in ucs_members:
			if not (member_dn.lower() in ucs_members_from_ad['user'] or member_dn.lower() in ucs_members_from_ad['group'] or member_dn.lower() in ucs_members_from_ad['unknown']):
				try:
					cache[member_dn] = self.lo.get(member_dn)
					ucs_object = {'dn':member_dn,'modtype':'modify','attributes': cache[member_dn]}

					if self._ignore_object(key, object):
						continue

					for k in self.property.keys():
						if self.modules[k].identify(member_dn, ucs_object['attributes']):
							ad_dn = self._object_mapping(k, ucs_object, 'ucs')['dn']

							ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: search for: %s" % ad_dn)
							# search only for cn to suppress coding errors
							if not self.lo_ad.get(ad_dn,attr=['cn']): 
								# member does not exist in AD but should
								# stay a member in UCS
								ucs_members_from_ad[k].append(member_dn.lower())
						break

				except (ldap.SERVER_DOWN, SystemExit):
					raise
				except: # FIXME: which exception is to be caught?
					self._debug_traceback(ud.INFO, "group_members_sync_to_ucs: failed to get dn from ucs which is groupmember")

		add_members = copy.deepcopy(ucs_members_from_ad)
		del_members = { 'user' : [], 'group': [] }

		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: ucs_members: %s" % ucs_members)
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: ucs_members_from_ad: %s" % ucs_members_from_ad)

		for member_dn in ucs_members:
			if member_dn.lower() in ucs_members_from_ad['user']:
				add_members['user'].remove(member_dn.lower())
			elif member_dn.lower() in ucs_members_from_ad['group']:
				add_members['group'].remove(member_dn.lower())
			elif member_dn.lower() in ucs_members_from_ad['unknown']:
				add_members['unknown'].remove(member_dn.lower())
			else:
				# remove member only if he was in the cache
				# otherwise it is possible that the user was just created on UCS
				if member_dn.lower() in self.group_members_cache_ucs.get(ad_object['dn'].lower(), [member_dn.lower()]):
					ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: %s was found in group member ucs cache of %s" % (member_dn.lower(), object['dn'].lower()))
					ucs_object_attr=cache.get(member_dn)
					if not ucs_object_attr:
						ucs_object_attr = self.lo.get(member_dn)
						cache[member_dn] = ucs_object_attr
					ucs_object = {'dn':member_dn,'modtype':'modify','attributes':ucs_object_attr}

					if not self._ignore_object('user', ucs_object) and not self._ignore_object('group', ucs_object):
						for k in self.property.keys():
							# identify if DN is a user or a group (will be ignored it is a host)
							if self.modules[k].identify(member_dn, ucs_object['attributes']):
								del_members[k].append(member_dn)
								break					
				else:
					ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: %s was not found in group member ucs cache of %s, don't delete" % (member_dn.lower(), object['dn'].lower()))
		self.group_members_cache_ucs[object['dn'].lower()] = ucs_members_from_ad['user'] + ucs_members_from_ad['group'] + ucs_members_from_ad['unknown']
		ud.debug(ud.LDAP, ud.INFO, "group_members_cache_ucs[%s]: %s" % (object['dn'].lower(), self.group_members_cache_ucs[object['dn'].lower()]))

		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: members to add: %s" % add_members)
		ud.debug(ud.LDAP, ud.INFO, "group_members_sync_to_ucs: members to del: %s" % del_members)

		if add_members['user'] or add_members['group'] or del_members['user'] or del_members['group'] or add_members['unknown']:
			ucs_admin_object=univention.admin.objects.get(self.modules[object_key], co='', lo=self.lo, position='', dn=object['dn'])
			ucs_admin_object.open()

			uniqueMember_add = add_members['user'] + add_members['group'] + add_members['unknown']
			uniqueMember_del = del_members['user'] + del_members['group']
			memberUid_add = []
			memberUid_del = []
			for member in add_members['user']:
				uid = ldap.explode_dn(member)[0].split('=')[-1]
				memberUid_add.append(uid)
			for member in add_members['unknown']: # user or group?
				ucs_object_attr = self.lo.get(member)
				uid=ucs_object_attr.get('uid')
				if uid:
					memberUid_add.append(uid[0])
			for member in del_members['user']:
				uid = ldap.explode_dn(member)[0].split('=')[-1]
				memberUid_del.append(uid)
			if uniqueMember_del or memberUid_del:
				ucs_admin_object.fast_member_remove(uniqueMember_del, memberUid_del, ignore_license=1)
			if uniqueMember_add or memberUid_del:
				ucs_admin_object.fast_member_add(uniqueMember_add, memberUid_add)

		else:
			pass
			
	def set_userPrincipalName_from_ucr(self, key, object):
		object_key = key
		object_ucs = self._object_mapping(object_key,object)
		ldap_object_ad = self.get_object(object['dn'])

		kerberosdomain = self.baseConfig.get('%s/ad/mapping/kerberosdomain' % self.CONFIGBASENAME, None)
		if kerberosdomain and not ldap_object_ad.has_key('userPrincipalName'):
			ucs_admin_object=univention.admin.objects.get(self.modules[object_key], co='', lo=self.lo, position='', dn=object_ucs['dn'])
			ucs_admin_object.open()

			userPrincipalName = "%s@%s" % (ucs_admin_object['username'], kerberosdomain)
			modlist=[(ldap.MOD_REPLACE, 'userPrincipalName', [userPrincipalName])]
			ud.debug(ud.LDAP, ud.INFO, "set_userPrincipalName_from_ucr: set kerberos principle %s for AD user %s with modlist %s " % (userPrincipalName, object['dn'], modlist))
			self.lo_ad.lo.modify_s(compatible_modstring(object['dn']), compatible_modlist(modlist))


	def disable_user_from_ucs(self, key, object):		
		object_key = key

		object_ucs = self._object_mapping(object_key,object)
		ldap_object_ad = self.get_object(object['dn'])

		ucs_admin_object=univention.admin.objects.get(self.modules[object_key], co='', lo=self.lo, position='', dn=object_ucs['dn'])
		ucs_admin_object.open()

		modlist=[]

		ud.debug(ud.LDAP, ud.INFO, "Disabled state: %s" % ucs_admin_object['disabled'].lower())
		if not (ucs_admin_object['disabled'].lower() in [ 'none', '0' ]):
			# user disabled in UCS
			if ldap_object_ad.has_key('userAccountControl') and (int(ldap_object_ad['userAccountControl'][0]) & 2 ) == 0:
				#user enabled in AD -> change
				res=str(int(ldap_object_ad['userAccountControl'][0]) | 2)
				modlist.append((ldap.MOD_REPLACE, 'userAccountControl', [res]))
		else:
			# user enabled in UCS
			if ldap_object_ad.has_key('userAccountControl') and (int(ldap_object_ad['userAccountControl'][0]) & 2 ) > 0:
				#user disabled in AD -> change
				res=str(int(ldap_object_ad['userAccountControl'][0]) - 2)
				modlist.append((ldap.MOD_REPLACE, 'userAccountControl', [res]))

		# account expires
		# This value represents the number of 100 nanosecond intervals since January 1, 1601 (UTC). A value of 0 or 0x7FFFFFFFFFFFFFFF (9223372036854775807) indicates that the account never expires.
		if not ucs_admin_object['userexpiry']:
			# ucs account not expired
			if ldap_object_ad.has_key('accountExpires') and (long(ldap_object_ad['accountExpires'][0]) != long(9223372036854775807) or ldap_object_ad['accountExpires'][0] == '0'):
				# ad account expired -> change
				modlist.append((ldap.MOD_REPLACE, 'accountExpires', ['9223372036854775807']))
		else:
			# ucs account expired
			if ldap_object_ad.has_key('accountExpires') and ldap_object_ad['accountExpires'][0] != unix2ad_time(ucs_admin_object['userexpiry']):
				# ad account not expired -> change
				modlist.append((ldap.MOD_REPLACE, 'accountExpires', [str(unix2ad_time(ucs_admin_object['userexpiry']))]))

		if modlist:
			self.lo_ad.lo.modify_s(compatible_modstring(object['dn']), compatible_modlist(modlist))
		pass

	def disable_user_to_ucs(self, key, object):
		object_key = key

		ad_object = self._object_mapping(object_key,object,'ucs')

		ldap_object_ucs = self.get_ucs_ldap_object(object['dn'])
		ldap_object_ad = self.get_object(ad_object['dn'])

		modified=0
		ucs_admin_object=univention.admin.objects.get(self.modules[object_key], co='', lo=self.lo, position='', dn=object['dn'])
		ucs_admin_object.open()

		if ldap_object_ad.has_key('userAccountControl') and (int(ldap_object_ad['userAccountControl'][0]) & 2) == 0:
			#user enabled in AD
			if not ucs_admin_object['disabled'].lower() in [ 'none', '0' ]:
				#user disabled in UCS -> change
				ucs_admin_object['disabled']='none'
				modified=1
		else:
			#user disabled in AD
			if ucs_admin_object['disabled'].lower() in [ 'none', '0' ]:
				#user enabled in UCS -> change
				ucs_admin_object['disabled']='all'
				modified=1
		if ldap_object_ad.has_key('accountExpires') and ( long(ldap_object_ad['accountExpires'][0]) == long(9223372036854775807) or ldap_object_ad['accountExpires'][0] == '0'):
			# ad account not expired
			if ucs_admin_object['userexpiry']:
				# ucs account expired -> change
				ucs_admin_object['userexpiry']=None
				modified=1
		else:
			# ad account expired
			ud.debug(ud.LDAP, ud.INFO, "sync account_expire:      adtime: %s    unixtime: %s" %
					       (long(ldap_object_ad['accountExpires'][0]),ucs_admin_object['userexpiry']))

			if ad2unix_time(long(ldap_object_ad['accountExpires'][0])) != ucs_admin_object['userexpiry']:
				# ucs account not expired -> change
				ucs_admin_object['userexpiry']=ad2unix_time(long(ldap_object_ad['accountExpires'][0]))
				modified=1

		if modified:
			ucs_admin_object.modify()
		pass



	def initialize(self):
		_d=ud.function('ldap.initialize')
		print "--------------------------------------"
		print "Initialize sync from AD"
		if self._get_lastUSN() == 0: # we startup new
			ud.debug(ud.LDAP, ud.PROCESS, "initialize AD: last USN is 0, sync all")
			# query highest USN in LDAP
			highestCommittedUSN = self.__get_highestCommittedUSN()

			# poll for all objects without deleted objects
			polled=self.poll(show_deleted=False)

			# compare highest USN from poll with highest before poll, if the last changes deletes
			# the highest USN from poll is to low
			self._set_lastUSN(max(highestCommittedUSN,self._get_lastUSN()))

			self._commit_lastUSN()
			ud.debug(ud.LDAP, ud.INFO, "initialize AD: sync of all objects finished, lastUSN is %d", self.__get_highestCommittedUSN())
		else:
			self.resync_rejected()
			polled=self.poll()		
			self._commit_lastUSN()
		print "--------------------------------------"
		
	def resync_rejected(self):
		'''
		tries to resync rejected dn
		'''
		print "--------------------------------------"
		
		_d=ud.function('ldap.resync_rejected')
		change_count = 0
		rejected = self._list_rejected()
		print "Sync %s rejected changes from AD to UCS" % len(rejected)
		sys.stdout.flush()
		if rejected:
			for id, dn in rejected:
				try:
					premapped_ad_dn = unicode(dn, 'utf8')
				except TypeError:
					premapped_ad_dn = dn
				ud.debug(ud.LDAP, ud.PROCESS, 'sync to ucs: Resync rejected dn: %s' % (premapped_ad_dn))
				try:
					sync_successfull = False
					elements = self.__search_ad_changeUSN(id, show_deleted=True)
					if not elements or len(elements) < 1 or not elements[0][0]:
						ud.debug(ud.LDAP, ud.INFO,
											   "rejected change with id %s not found, don't need to sync" % id)
						self._remove_rejected(id)
					elif len(elements) > 1 and not (elements[1][0] == 'None' or elements[1][0] == None): # all except the first should be referrals
						ud.debug(ud.LDAP, ud.WARN,
											   "more than one rejected object with id %s found, can't proceed" % id)
					else:						
						object = self.__object_from_element(elements[0])
						property_key = self.__identify(object)
						mapped_object = self._object_mapping(property_key,object)
						try:
							if not self._ignore_object(property_key,mapped_object) and not self._ignore_object(property_key,object):
								sync_successfull = self.sync_to_ucs(property_key, mapped_object, premapped_ad_dn)
							else:
								sync_successfull = True
						except (ldap.SERVER_DOWN, SystemExit):
							raise
						except: # FIXME: which exception is to be caught?
							self._debug_traceback(ud.ERROR,
												  "sync of rejected object failed \n\t%s" % (object['dn']))
							sync_successfull = False
						if sync_successfull:
							change_count+=1
							self._remove_rejected(id)
							self.__update_lastUSN(object)
							self._set_DN_for_GUID(elements[0][1]['objectGUID'][0],elements[0][0])
				except (ldap.SERVER_DOWN, SystemExit):
					raise		
				except Exception, msg:
					self._debug_traceback(ud.ERROR,
										  "unexpected Error during ad.resync_rejected")
		print "restored %s rejected changes" % change_count
		print "--------------------------------------"
		sys.stdout.flush()

	def poll(self, show_deleted=True):
		'''
		poll for changes in AD
		'''
		_d=ud.function('ldap.poll')
		# search from last_usn for changes

		change_count = 0
		changes = []
		try:
			changes = self.__search_ad_changes(show_deleted=show_deleted)
		except (ldap.SERVER_DOWN, SystemExit):
			raise		
		except: # FIXME: which exception is to be caught?
			self._debug_traceback(ud.WARN,"Exception during search_ad_changes")

		print "--------------------------------------"
		print "try to sync %s changes from AD" % len(changes)
		print "done:",
		sys.stdout.flush()
		done_counter = 0
		object = None
		lastUSN = self._get_lastUSN()
		newUSN = lastUSN

		for element in changes:
			try:
				if element[0] == 'None': # referrals
					continue
				old_element = copy.deepcopy(element)
				object = self.__object_from_element(element)
			except: # FIXME: which exception is to be caught?
				#ud.debug(ud.LDAP, ud.ERROR, "Exception during poll/object-mapping, tried to map element: %s" % old_element[0])
				#ud.debug(ud.LDAP, ud.ERROR, "This object will not be synced again!")
				# debug-trace may lead to a segfault here :(
				self._debug_traceback(ud.ERROR,"Exception during poll/object-mapping, object will not be synced again!")
				
			if object:
				property_key = self.__identify(object)
				if property_key:
					
					if self._ignore_object(property_key,object):
						if object['modtype'] == 'move':
							ud.debug(ud.LDAP, ud.INFO, "object_from_element: Detected a move of an AD object into a ignored tree: dn: %s" % object['dn'])
							object['deleted_dn'] = object['olddn']
							object['dn'] = object['olddn']
							object['modtype'] = 'delete'
							# check the move target
						else:
							self.__update_lastUSN(object)
							done_counter += 1
							print "%s"%done_counter,
							continue

					if object['dn'].find('\\0ACNF:') > 0:
						ud.debug(ud.LDAP, ud.PROCESS, 'Ignore conflicted object: %s' % object['dn'])
						self.__update_lastUSN(object)
						done_counter += 1
						print "%s"%done_counter,
						continue

					sync_successfull = False
					try:
						mapped_object = self._object_mapping(property_key,object)
						if not self._ignore_object(property_key,mapped_object):
							sync_successfull = self.sync_to_ucs(property_key, mapped_object, object['dn'])
						else:
							sync_successfull = True
					except (ldap.SERVER_DOWN, SystemExit):
						raise
					except univention.admin.uexceptions.ldapError, msg:
						ud.debug(ud.LDAP, ud.INFO, "Exception during poll with message (1) %s"%msg)
						if msg == "Can't contact LDAP server":
							raise ldap.SERVER_DOWN
						else:
							self._debug_traceback(ud.WARN,"Exception during poll/sync_to_ucs")
					except univention.admin.uexceptions.ldapError, msg:
						ud.debug(ud.LDAP, ud.INFO, "Exception during poll with message (2) %s"%msg)
						if msg == "Can't contact LDAP server":
							raise ldap.SERVER_DOWN
						else:
							self._debug_traceback(ud.WARN,"Exception during poll")
					except: # FIXME: which exception is to be caught?
						self._debug_traceback(ud.WARN,
								"Exception during poll/sync_to_ucs")



					if not sync_successfull:
						ud.debug(ud.LDAP, ud.WARN,
											   "sync to ucs was not successfull, save rejected")
						ud.debug(ud.LDAP, ud.WARN,
											   "object was: %s"%object['dn'])

					if sync_successfull:
						change_count+=1
						newUSN = max( self.__get_change_usn(object), newUSN)
						try:
							GUID = old_element[1]['objectGUID'][0]
							self._set_DN_for_GUID(GUID,old_element[0])
						except (ldap.SERVER_DOWN, SystemExit):
							raise
						except: # FIXME: which exception is to be caught?
							self._debug_traceback(ud.WARN,
									      "Exception during set_DN_for_GUID")

					else:
						self.save_rejected(object)
						self.__update_lastUSN(object)
				else:
					newUSN = max( self.__get_change_usn(object), newUSN)

				done_counter += 1
				print "%s"%done_counter,
			else:
				done_counter += 1
				print "(%s)"%done_counter,
			sys.stdout.flush()
				
		print ""

		if newUSN != lastUSN:
			self._set_lastUSN(newUSN)
			self._commit_lastUSN()

		# return number of synced objects
		rejected = self._list_rejected()
		if rejected:
			print "Changes from AD:  %s (%s saved rejected)" % (change_count, len(rejected))
		else:
			print "Changes from AD:  %s (%s saved rejected)" % (change_count, '0')
		print "--------------------------------------"
		sys.stdout.flush()
		return change_count


	def sync_from_ucs(self, property_type, object, pre_mapped_ucs_dn, old_dn=None, old_ucs_object = None):
		_d=ud.function('ldap.__sync_from_ucs')
		# Diese Methode erhaelt von der UCS Klasse ein Objekt,
		# welches hier bearbeitet wird und in das AD geschrieben wird.
		# object ist brereits vom eingelesenen UCS-Objekt nach AD gemappt, old_dn ist die alte UCS-DN
		ud.debug(ud.LDAP, ud.INFO, "sync_from_ucs: sync object: %s"%object['dn'])

		# if sync is read (sync from AD) or none, there is nothing to do
		if self.property[property_type].sync_mode in ['read', 'none']:
			ud.debug(ud.LDAP, ud.INFO, "sync_from_ucs ignored, sync_mode is %s" % self.property[property_type].sync_mode)
			return True

		pre_mapped_ucs_old_dn = old_dn		
		
		if old_dn:
			ud.debug(ud.LDAP, ud.INFO, "move %s from [%s] to [%s]" % (property_type, old_dn, object['dn']))
			if hasattr ( self.property[property_type], 'dn_mapping_function' ):
				tmp_object = copy.deepcopy(object)
				tmp_object['dn'] = old_dn
				for function in self.property[property_type].dn_mapping_function:
					tmp_object=function(self, tmp_object, [], isUCSobject=True)
				old_dn = tmp_object['dn']
			if hasattr(self.property[property_type], 'position_mapping'):
				for mapping in self.property[property_type].position_mapping:
					old_dn=self._subtree_replace(old_dn.lower(),mapping[0].lower(),mapping[1].lower())
				old_dn = self._subtree_replace(old_dn,self.lo.base,self.lo_ad.base)

			# the old object was moved in UCS, but does this object exist in AD?
			try:
				old_object = self.lo_ad.lo.search_ext_s(compatible_modstring(old_dn),ldap.SCOPE_BASE,'objectClass=*',timeout=-1,sizelimit=0)
			except (ldap.SERVER_DOWN, SystemExit):
				raise
			except:
				old_object=None

			if old_object:
				ud.debug(ud.LDAP, ud.INFO, "move %s from [%s] to [%s]" % (property_type, old_dn, object['dn']))
				try:
					self.lo_ad.rename(unicode(old_dn), object['dn'])
				except ldap.NO_SUCH_OBJECT: # check if object is already moved (we may resync now)
					new = encode_ad_resultlist(self.lo_ad.lo.search_ext_s(compatible_modstring(object['dn']),ldap.SCOPE_BASE,'objectClass=*',timeout=-1,sizelimit=0))
					if not new:
						raise
				# need to actualise the GUID and DN-Mapping
				self._set_DN_for_GUID(self.lo_ad.lo.search_ext_s(compatible_modstring(object['dn']),ldap.SCOPE_BASE,'objectClass=*',timeout=-1,sizelimit=0)[0][1]['objectGUID'][0],
							  object['dn'])
				self._remove_dn_mapping(pre_mapped_ucs_old_dn, unicode(old_dn))
				self._check_dn_mapping(pre_mapped_ucs_dn, object['dn'])

		ud.debug(ud.LDAP, ud.PROCESS,
							   'sync from ucs: [%14s] [%10s] %s' % (property_type,object['modtype'], object['dn']))

		if object.has_key('olddn'):
			object.pop('olddn') # not needed anymore, will fail object_mapping in later functions
		old_dn=None

		addlist=[]
		modlist=[]

		if self.group_mapping_cache_con.get(object['dn'].lower()) and object['modtype'] != 'delete':
			ud.debug(ud.LDAP, ud.INFO, "sync_from_ucs: remove %s from group cache" % object['dn'])
			self.group_mapping_cache_con[object['dn'].lower()] = None

		ad_object=self.get_object(object['dn'])

		if (object['modtype'] == 'add' and not ad_object) or (object['modtype'] == 'modify' and not ad_object):
			ud.debug(ud.LDAP, ud.INFO, "sync_from_ucs: add object: %s"%object['dn'])

			# objectClass
			if self.property[property_type].con_create_objectclass:
				addlist.append(('objectClass', self.property[property_type].con_create_objectclass))

			if hasattr(self.property[property_type], 'attributes') and self.property[property_type].attributes != None:
				for attr,value in object['attributes'].items():
					for attribute in self.property[property_type].attributes.keys():
						if self.property[property_type].attributes[attribute].con_attribute == attr:
							addlist.append((attr, value))
						if self.property[property_type].attributes[attribute].con_other_attribute == attr:
							addlist.append((attr, value))
			if hasattr(self.property[property_type], 'post_attributes') and self.property[property_type].post_attributes != None:
				for attr,value in object['attributes'].items():
					for attribute in self.property[property_type].post_attributes.keys():
						if self.property[property_type].post_attributes[attribute].reverse_attribute_check:
							if not object['attributes'].get(self.property[property_type].post_attributes[attribute].ldap_attribute):
								continue
						if self.property[property_type].post_attributes[attribute].con_attribute == attr:
							modlist.append((ldap.MOD_REPLACE, attr, value))
							if value:
								modlist.append((ldap.MOD_REPLACE, attr, value))
							else:
								modlist.append((ldap.MOD_DELETE, attr, None))
						if self.property[property_type].post_attributes[attribute].con_other_attribute == attr:
							if value:
								modlist.append((ldap.MOD_REPLACE, attr, value))
							else:
								modlist.append((ldap.MOD_DELETE, attr, None))

			self.lo_ad.lo.add_s(compatible_modstring(object['dn']), compatible_addlist(addlist)) #FIXME encoding

			if property_type == 'group':
				self.group_members_cache_con[object['dn'].lower()] = []
				ud.debug(ud.LDAP, ud.INFO, "group_members_cache_con[%s]: []" % (object['dn'].lower()))

			if hasattr(self.property[property_type],"post_con_create_functions"):
				for f in self.property[property_type].post_con_create_functions:
					f(self, property_type, object)

			ud.debug(ud.LDAP, ud.INFO, "to modify: %s"%object['dn'])
			if modlist:
				self.lo_ad.lo.modify_s(compatible_modstring(object['dn']), compatible_modlist(modlist))

			if hasattr(self.property[property_type],"post_con_modify_functions"):
				for f in self.property[property_type].post_con_modify_functions:
					ud.debug(ud.LDAP, ud.INFO, "Call post_con_modify_functions: %s" % f)
					f(self, property_type, object)
					ud.debug(ud.LDAP, ud.INFO, "Call post_con_modify_functions: %s (done)" % f)

		elif (object['modtype'] == 'modify' and ad_object) or (object['modtype'] == 'add' and ad_object):
			ud.debug(ud.LDAP, ud.INFO, "sync_from_ucs: modify object: %s"%object['dn'])
			attr_list = []
			if hasattr(self.property[property_type], 'attributes') and self.property[property_type].attributes != None:
				for attr,value in object['attributes'].items():
					attr_list.append(attr)
					for attribute in self.property[property_type].attributes.keys():
						if self.property[property_type].attributes[attribute].con_attribute == attr or self.property[property_type].attributes[attribute].con_other_attribute == attr:
							if not ad_object.has_key(attr):
								if value:
									modlist.append((ldap.MOD_ADD, attr, value))
 							elif not univention.connector.compare_lowercase(value,ad_object[attr]): # FIXME: use defined compare-function from mapping.py
								modlist.append((ldap.MOD_REPLACE, attr, value))
			if hasattr(self.property[property_type], 'post_attributes') and self.property[property_type].post_attributes != None:
				for attr,value in object['attributes'].items():
					attr_list.append(attr)
					for attribute in self.property[property_type].post_attributes.keys():
						if self.property[property_type].post_attributes[attribute].con_attribute == attr or self.property[property_type].post_attributes[attribute].con_other_attribute == attr:
							if self.property[property_type].post_attributes[attribute].reverse_attribute_check:
								if not object['attributes'].get(self.property[property_type].post_attributes[attribute].ldap_attribute):
									continue
							if not ad_object.has_key(attr):
								if value:
									modlist.append((ldap.MOD_ADD, attr, value))
 							elif not univention.connector.compare_lowercase(value,ad_object[attr]): # FIXME: use defined compare-function from mapping.py
								modlist.append((ldap.MOD_REPLACE, attr, value))

			attrs_in_current_ucs_object = object['attributes'].keys()
			attrs_which_should_be_mapped = []
			attrs_to_remove_from_ad_object = []


			if hasattr(self.property[property_type], 'attributes') and self.property[property_type].attributes != None:
				for ac in self.property[property_type].attributes.keys():
					if not self.property[property_type].attributes[ac].con_attribute in attrs_which_should_be_mapped:
						attrs_which_should_be_mapped.append(self.property[property_type].attributes[ac].con_attribute)
					if self.property[property_type].attributes[ac].con_other_attribute:
						if not self.property[property_type].attributes[ac].con_other_attribute in attrs_which_should_be_mapped:
							attrs_which_should_be_mapped.append(self.property[property_type].attributes[ac].con_other_attribute)

			if hasattr(self.property[property_type], 'post_attributes') and self.property[property_type].post_attributes != None:
				for ac in self.property[property_type].post_attributes.keys():
					if not self.property[property_type].post_attributes[ac].con_attribute in attrs_which_should_be_mapped:
						if self.property[property_type].post_attributes[ac].reverse_attribute_check:
							if object['attributes'].get(self.property[property_type].post_attributes[ac].ldap_attribute):
								attrs_which_should_be_mapped.append(self.property[property_type].post_attributes[ac].con_attribute)
							elif ad_object.get(self.property[property_type].post_attributes[ac].con_attribute):
								modlist.append((ldap.MOD_DELETE, self.property[property_type].post_attributes[ac].con_attribute, None))
						else:
							attrs_which_should_be_mapped.append(self.property[property_type].post_attributes[ac].con_attribute)
					if self.property[property_type].post_attributes[ac].con_other_attribute:
						if not self.property[property_type].post_attributes[ac].con_other_attribute in attrs_which_should_be_mapped:
							attrs_which_should_be_mapped.append(self.property[property_type].post_attributes[ac].con_other_attribute)

			modlist_empty_attrs = []			
			for expected_attribute in attrs_which_should_be_mapped:
				if not object['attributes'].has_key(expected_attribute):
					attrs_to_remove_from_ad_object.append(expected_attribute)

				if modlist:
					for modified_attrs in modlist:
						if modified_attrs[1] in attrs_to_remove_from_ad_object and len(modified_attrs[2]) > 0:
							attrs_to_remove_from_ad_object.remove(modified_attrs[1])

			for yank_empty_attr in attrs_to_remove_from_ad_object:
				if ad_object.has_key(yank_empty_attr):
					if value != None:
						modlist.append((ldap.MOD_DELETE, yank_empty_attr, None))

			if modlist:
				self.lo_ad.lo.modify_s(compatible_modstring(object['dn']), compatible_modlist(modlist))


			if hasattr(self.property[property_type],"post_con_modify_functions"):
				for f in self.property[property_type].post_con_modify_functions:
					ud.debug(ud.LDAP, ud.INFO, "Call post_con_modify_functions: %s" % f)
					f(self, property_type, object)
					ud.debug(ud.LDAP, ud.INFO, "Call post_con_modify_functions: %s (done)" % f)
		elif object['modtype'] == 'delete':
			self.delete_in_ad( object )
				
		else:
			ud.debug(ud.LDAP, ud.WARN,
								   "unknown modtype (%s : %s)" %
								   (object['dn'],object['modtype']))
			return False


		self._check_dn_mapping(pre_mapped_ucs_dn, object['dn'])

		ud.debug(ud.LDAP, ud.ALL,
							   "sync from ucs return True" )
		return True # FIXME: return correct False if sync fails

	def delete_in_ad(self, object ):
		_d=ud.function('ldap.delete_in_ad')
		try:
			self.lo_ad.lo.delete_s(compatible_modstring(object['dn']))
		except ldap.NO_SUCH_OBJECT:
			pass # object already deleted
		except ldap.NOT_ALLOWED_ON_NONLEAF:
			ud.debug(ud.LDAP, ud.INFO,"remove object from AD failed, need to delete subtree")
			for result in self.lo_ad.lo.search_ext_s(compatible_modstring(object['dn']),ldap.SCOPE_SUBTREE,'objectClass=*',timeout=-1,sizelimit=0):
				if univention.connector.compare_lowercase(result[0], object['dn']):
					continue
				ud.debug(ud.LDAP, ud.INFO,"delete: %s"% result[0])
				subobject={'dn': result[0], 'modtype': 'delete', 'attributes': result[1]}
				key = None
				for k in self.property.keys():
					if self.modules[k].identify(result[0], result[1]):
						key=k
						break
				object_mapping = self._object_mapping(key, subobject)
				ud.debug(ud.LDAP, ud.WARN,"delete subobject: %s"% object_mapping['dn'])
				if not self._ignore_object(key,object_mapping):
					if not self.sync_from_ucs(key, subobject, object_mapping['dn']):
						try:
							ud.debug(ud.LDAP, ud.WARN,"delete of subobject failed: %s"% result[0])
						except (ldap.SERVER_DOWN, SystemExit):
							raise							
						except: # FIXME: which exception is to be caught?
							ud.debug(ud.LDAP, ud.WARN,"delete of subobject failed")
						return False


			return self.delete_in_ad(object)


