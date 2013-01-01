/*
 * Univention Directory Listener
 *  entries in the cache
 *
 * Copyright 2004-2012 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */

#include <stdlib.h>
#include <ctype.h>
#include <stdbool.h>
#include <string.h>
#include <ldap.h>

#include <univention/debug.h>
#include <univention/config.h>

#include "cache_entry.h"
#include "base64.h"

int cache_free_entry(char **dn, CacheEntry *entry)
{
	int i, j;

	if (dn != NULL) {
		free(*dn);
		*dn = NULL;
	}

	for(i=0; i<entry->attribute_count; i++) {
		if(entry->attributes[i]->name) {
			free(entry->attributes[i]->name);
		}
		for(j=0; j<entry->attributes[i]->value_count; j++) {
			if(entry->attributes[i]->values[j]) {
				free(entry->attributes[i]->values[j]);
			}
		}
		if(entry->attributes[i]->values) {
			free(entry->attributes[i]->values);
		}
		if(entry->attributes[i]->length) {
			free(entry->attributes[i]->length);
		}
		if(entry->attributes[i]) {
			free(entry->attributes[i]);
		}
	}

	if (entry->attributes) {
		free(entry->attributes);
	}

	for(i=0; i<entry->module_count; i++) {
		if (entry->modules[i]) {
			free(entry->modules[i]);
		}
	}

	if(entry->modules) {
		free(entry->modules);
	}

	entry->modules = NULL;
	entry->module_count = 0;

	return 0;
}

int cache_dump_entry(char *dn, CacheEntry *entry, FILE *fp)
{
	CacheEntryAttribute **attribute;
	char **module;
	char **value;

	fprintf(fp, "dn: %s\n", dn);
	int i, j;
	for(i=0; i<entry->attribute_count; i++) {
		attribute = &entry->attributes[i];
		for (j=0; j<entry->attributes[i]->value_count; j++) {
			value = &entry->attributes[i]->values[j];
			char *c;
			for (c=*value; *c != '\0'; c++) {
				if (!isgraph(*c))
					break;
			}
			if (*c != '\0') {
				char *base64_value;
				size_t srclen = entry->attributes[i]->length[j]-1;
				base64_value = malloc(BASE64_ENCODE_LEN(srclen)+1);
				base64_encode((u_char *)*value, srclen, base64_value, BASE64_ENCODE_LEN(srclen)+1);
				fprintf(fp, "%s:: %s\n", (*attribute)->name, base64_value);
				free(base64_value);
			} else {
				fprintf(fp, "%s: %s\n", (*attribute)->name, *value);
			}
		}
	}
	for (module=entry->modules; module != NULL && *module != NULL; module++) {
		fprintf(fp, "listenerModule: %s\n", *module);
	}

	return 0;
}

int cache_entry_module_add(CacheEntry *entry, char *module)
{
	char **cur;

	for (cur=entry->modules; cur != NULL && *cur != NULL; cur++) {
		if (strcmp(*cur, module) == 0)
			return 0;
	}

	entry->modules = realloc(entry->modules, (entry->module_count+2)*sizeof(char*));
	entry->modules[entry->module_count] = strdup(module);
	entry->modules[entry->module_count+1] = NULL;
	entry->module_count++;

	return 0;
}

int cache_entry_module_remove(CacheEntry *entry, char *module)
{
	char **cur;

	for (cur=entry->modules; cur != NULL && *cur != NULL; cur++) {
		if (strcmp(*cur, module) == 0)
			break;
	}

	if (cur == NULL || *cur == NULL)
		return 0;

	/* replace entry that is to be removed with last entry */
	free(*cur);
	entry->modules[cur-entry->modules] = entry->modules[entry->module_count-1];
	entry->modules[entry->module_count-1] = NULL;
	entry->module_count--;

	entry->modules = realloc(entry->modules, (entry->module_count+1)*sizeof(char*));

	return 0;
}

int cache_entry_module_present(CacheEntry *entry, char *module)
{
	char **cur;

	if (entry == NULL)
		return 0;
	for (cur=entry->modules; cur != NULL && *cur != NULL; cur++) {
		if (strcmp(*cur, module) == 0)
			return 1;
	}
	return 0;
}

int cache_new_entry_from_ldap(char **dn, CacheEntry *cache_entry, LDAP *ld, LDAPMessage *ldap_entry)
{
	BerElement *ber;
	char *attr;
	char *_dn;
	int rv = 0;

	bool memberUidMode = false;
	bool uniqueMemberMode = false;
	bool duplicateMemberUid = false;
	bool duplicateUniqueMember = false;
	int i;

	/* convert LDAP entry to cache entry */
	memset(cache_entry, 0, sizeof(CacheEntry));
	if (dn != NULL) {
		_dn = ldap_get_dn(ld, ldap_entry);
		if(*dn)
				free(*dn);
		*dn = strdup(_dn);
		ldap_memfree(_dn);
	}

	for (attr=ldap_first_attribute(ld, ldap_entry, &ber); attr != NULL; attr=ldap_next_attribute(ld, ldap_entry, ber)) {
		struct berval **val, **v;

		if ((cache_entry->attributes = realloc(cache_entry->attributes, (cache_entry->attribute_count+2)*sizeof(CacheEntryAttribute*))) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: realloc of attributes array failed");
			rv = 1;
			goto result;
		}
		if ((cache_entry->attributes[cache_entry->attribute_count] = malloc(sizeof(CacheEntryAttribute))) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: malloc for CacheEntryAttribute failed");
			rv = 1;
			goto result;
		}
		cache_entry->attributes[cache_entry->attribute_count]->name=strdup(attr);
		cache_entry->attributes[cache_entry->attribute_count]->values=NULL;
		cache_entry->attributes[cache_entry->attribute_count]->length=NULL;
		cache_entry->attributes[cache_entry->attribute_count]->value_count=0;
		cache_entry->attributes[cache_entry->attribute_count+1]=NULL;

		memberUidMode = false;
		if ( !strncmp(cache_entry->attributes[cache_entry->attribute_count]->name, "memberUid", strlen("memberUid")) ) {
			char *ucrval;
			ucrval = univention_config_get_string("listener/memberuid/skip");

			if (ucrval) {
				memberUidMode = !strcmp(ucrval, "yes") || !strcmp(ucrval, "true");
				free(ucrval);
			}
		}
		uniqueMemberMode = false;
		if ( !strncmp(cache_entry->attributes[cache_entry->attribute_count]->name, "uniqueMember", strlen("uniqueMember")) ) {
			char *ucrval;
			ucrval = univention_config_get_string("listener/uniquemember/skip");

			if (ucrval) {
				uniqueMemberMode = !strcmp(ucrval, "yes") || !strcmp(ucrval, "true");
				free(ucrval);
			}
		}
		if ((val=ldap_get_values_len(ld, ldap_entry, attr)) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ldap_get_values failed");
			rv = 1;
			goto result;
		}
		for (v = val; *v != NULL; v++) {
			if ( (*v)->bv_val == NULL ) {
				// check here, strlen behavior might be undefined in this case
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: ignoring bv_val of NULL with bv_len=%ld, ignoring, check attribute: %s of DN: %s", (*v)->bv_len, cache_entry->attributes[cache_entry->attribute_count]->name, *dn);
				rv = 1;
				goto result;
			}
			if (memberUidMode) {
				/* avoid duplicate memberUid entries https://forge.univention.org/bugzilla/show_bug.cgi?id=17998 */
				duplicateMemberUid = 0;
				for (i=0; i<cache_entry->attributes[cache_entry->attribute_count]->value_count; i++) {
					if (!memcmp(cache_entry->attributes[cache_entry->attribute_count]->values[i], (*v)->bv_val, (*v)->bv_len+1) ) {
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "Found a duplicate memberUid entry:");
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "DN: %s",  *dn);
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "memberUid: %s", cache_entry->attributes[cache_entry->attribute_count]->values[i]);
						duplicateMemberUid = true;
						break;
					}
				}
				if (duplicateMemberUid) {
					/* skip this memberUid entry if listener/memberuid/skip is set to yes */
					continue;
				}
			}
			if (uniqueMemberMode) {
				/* avoid duplicate uniqueMember entries https://forge.univention.org/bugzilla/show_bug.cgi?id=18692 */
				duplicateUniqueMember = false;
				for (i=0; i<cache_entry->attributes[cache_entry->attribute_count]->value_count; i++) {
					if (!memcmp(cache_entry->attributes[cache_entry->attribute_count]->values[i], (*v)->bv_val, (*v)->bv_len+1) ) {
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "Found a duplicate uniqueMember entry:");
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "DN: %s",  *dn);
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "uniqueMember: %s", cache_entry->attributes[cache_entry->attribute_count]->values[i]);
						duplicateUniqueMember = true;
						break;
					}
				}
				if (duplicateUniqueMember) {
					/* skip this uniqueMember entry if listener/uniquemember/skip is set to yes */
					continue;
				}
			}
			if ((cache_entry->attributes[cache_entry->attribute_count]->values = realloc(cache_entry->attributes[cache_entry->attribute_count]->values, (cache_entry->attributes[cache_entry->attribute_count]->value_count+2)*sizeof(char*))) == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: realloc of values array failed");
				rv = 1;
				goto result;
			}
			if ((cache_entry->attributes[cache_entry->attribute_count]->length = realloc(cache_entry->attributes[cache_entry->attribute_count]->length, (cache_entry->attributes[cache_entry->attribute_count]->value_count+2)*sizeof(int))) == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: realloc of length array failed");
				rv = 1;
				goto result;
			}
			if ((*v)->bv_len == strlen((*v)->bv_val)) {
				if ((cache_entry->attributes[cache_entry->attribute_count]->values[cache_entry->attributes[cache_entry->attribute_count]->value_count]=strdup((*v)->bv_val)) == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: strdup of value failed");
					rv = 1;
					goto result;
				}
				cache_entry->attributes[cache_entry->attribute_count]->length[cache_entry->attributes[cache_entry->attribute_count]->value_count]=strlen(cache_entry->attributes[cache_entry->attribute_count]->values[cache_entry->attributes[cache_entry->attribute_count]->value_count])+1;
			} else {	// in this case something is strange about the string in bv_val, maybe contains a '\0'
				// the legacy approach is to copy bv_len bytes, let's stick with this and just terminate to be safe
				if ((cache_entry->attributes[cache_entry->attribute_count]->values[cache_entry->attributes[cache_entry->attribute_count]->value_count]=malloc(((*v)->bv_len+1)*sizeof(char))) == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "cache_new_entry_from_ldap: malloc for value failed");
					rv = 1;
					goto result;
				}
				memcpy(cache_entry->attributes[cache_entry->attribute_count]->values[cache_entry->attributes[cache_entry->attribute_count]->value_count],(*v)->bv_val,(*v)->bv_len);
				cache_entry->attributes[cache_entry->attribute_count]->values[cache_entry->attributes[cache_entry->attribute_count]->value_count][(*v)->bv_len]='\0'; // terminate the string to be safe
				cache_entry->attributes[cache_entry->attribute_count]->length[cache_entry->attributes[cache_entry->attribute_count]->value_count]=(*v)->bv_len+1;
			}
			cache_entry->attributes[cache_entry->attribute_count]->values[cache_entry->attributes[cache_entry->attribute_count]->value_count+1]=NULL;
			cache_entry->attributes[cache_entry->attribute_count]->value_count++;
		}
		cache_entry->attribute_count++;

		ldap_value_free_len(val);
		ldap_memfree(attr);
	}

	ber_free(ber, 0);

result:
	if (rv != 0)
		cache_free_entry(NULL, cache_entry);

	return rv;
}

/* return list of changes attributes between new and old; the caller will
   only need to free the (char**); the strings themselves are stolen from
   the new and old entries */
char** cache_entry_changed_attributes(CacheEntry *new, CacheEntry *old)
{
	char **changes = NULL;
	int changes_count = 0;
	CacheEntryAttribute **cur1, **cur2;

	for (cur1 = new->attributes; cur1 != NULL && *cur1 != NULL; cur1++) {
		for (cur2 = old->attributes; cur2 != NULL && *cur2 != NULL; cur2++)
			if (strcmp((*cur1)->name, (*cur2)->name) == 0)
				break;
		if (cur2 != NULL && *cur2 != NULL && (*cur1)->value_count == (*cur2)->value_count) {
			int i;
			for (i = 0; i < (*cur1)->value_count; i++)
				if (memcmp((*cur1)->values[i], (*cur2)->values[i], (*cur1)->length[i]) != 0)
					break;
			if (i == (*cur1)->value_count)
				continue;
		}

		changes = realloc(changes, (changes_count+2)*sizeof(char*));
		changes[changes_count] = (*cur1)->name;
		changes[changes_count+1] = NULL;
		changes_count++;
	}

	for (cur2 = old->attributes; cur2 != NULL && *cur2 != NULL; cur2++) {
		for (cur1 = new->attributes; cur1 != NULL && *cur1 != NULL; cur1++)
			if (strcmp((*cur1)->name, (*cur2)->name) == 0)
				break;
		if (cur1 != NULL && *cur1 != NULL)
			continue;

		changes = realloc(changes, (changes_count+2)*sizeof(char*));
		changes[changes_count] = (*cur2)->name;
		changes[changes_count+1] = NULL;
		changes_count++;
	}

	return changes;
}

int copy_cache_entry(CacheEntry *cache_entry, CacheEntry *backup_cache_entry) {
	CacheEntryAttribute **cur1, **cur2;
	int i=0;
	int rv=0;
	memset(backup_cache_entry, 0, sizeof(CacheEntry));
	for (cur1 = cache_entry->attributes; cur1 != NULL && *cur1 != NULL; cur1++) {
		if ((backup_cache_entry->attributes = realloc(backup_cache_entry->attributes, (backup_cache_entry->attribute_count+2)*sizeof(CacheEntryAttribute*))) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "copy_cache_entry: realloc of attributes array failed");
			rv = 1;
			goto result;
		}
		if ((backup_cache_entry->attributes[backup_cache_entry->attribute_count] = malloc(sizeof(CacheEntryAttribute))) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "copy_cache_entry: malloc for CacheEntryAttribute failed");
			rv = 1;
			goto result;
		}
		cur2 = &backup_cache_entry->attributes[backup_cache_entry->attribute_count];
		(*cur2)->name=strdup((*cur1)->name);
		(*cur2)->values=NULL;
		(*cur2)->length=NULL;
		(*cur2)->value_count=0;
		backup_cache_entry->attributes[backup_cache_entry->attribute_count+1]=NULL;

		for (i = 0; i < (*cur1)->value_count; i++) {
			if (((*cur2)->values = realloc((*cur2)->values, ((*cur2)->value_count+2)*sizeof(char*))) == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "copy_cache_entry: realloc of values array failed");
				rv = 1;
				goto result;
			}
			if (((*cur2)->length = realloc((*cur2)->length, ((*cur2)->value_count+2)*sizeof(int))) == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "copy_cache_entry: realloc of length array failed");
				rv = 1;
				goto result;
			}
			if ((*cur1)->length[i] == strlen((*cur1)->values[i]) + 1) {
				if (((*cur2)->values[(*cur2)->value_count]=strdup((*cur1)->values[i])) == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "copy_cache_entry: strdup of value failed");
					rv = 1;
					goto result;
				}
				(*cur2)->length[(*cur2)->value_count]=strlen((*cur2)->values[(*cur2)->value_count])+1;
			} else {
				if (((*cur2)->values[(*cur2)->value_count]=malloc(((*cur1)->length[i])*sizeof(char))) == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "copy_cache_entry: malloc for value failed");
					rv = 1;
					goto result;
				}
				memcpy((*cur2)->values[(*cur2)->value_count],(*cur1)->values[i],(*cur1)->length[i]);
				(*cur2)->length[(*cur2)->value_count]=(*cur1)->length[i];
			}
			(*cur2)->values[(*cur2)->value_count+1]=NULL;
			(*cur2)->value_count++;
		}
		backup_cache_entry->attribute_count++;
	}
	char **module_ptr;
	for (module_ptr=cache_entry->modules; module_ptr != NULL && *module_ptr != NULL; module_ptr++) {
		backup_cache_entry->modules = realloc(backup_cache_entry->modules, (backup_cache_entry->module_count+2)*sizeof(char*));
		backup_cache_entry->modules[backup_cache_entry->module_count] = strdup(*module_ptr);
		backup_cache_entry->modules[backup_cache_entry->module_count+1] = NULL;
		backup_cache_entry->module_count++;
	}
result:
	return rv;
}

void compare_cache_entries(CacheEntry *lentry, CacheEntry *rentry)
{
	char		**changes;
	char		**cur;
	int i=0;

	changes = cache_entry_changed_attributes(lentry, rentry);

	for (cur = changes; cur != NULL && *cur != NULL; cur++) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:     %s differs\n", *cur);

		for (i=0; lentry->attributes != NULL && lentry->attributes[i] != NULL; i++) {
			if (strcmp(lentry->attributes[i]->name, *cur) == 0)
				break;
		}
		if (lentry->attributes == NULL || lentry->attributes[i] == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:         lentry = []\n");
		} else {
			int j;
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:         lentry = [");
			for (j=0; lentry->attributes[i]->values &&
					lentry->attributes[i]->values[j] != NULL;
					j++) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, j == 0 ? "%s" : ", %s", lentry->attributes[i]->values[j]);
			}
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "]\n");
		}

		for (i=0; rentry->attributes != NULL && rentry->attributes[i] != NULL; i++) {
			if (strcmp(rentry->attributes[i]->name, *cur) == 0)
				break;
		}
		if (rentry->attributes == NULL || rentry->attributes[i] == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:         rentry = []\n");
		} else {
			int j;
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:         rentry = [");
			for (j=0; rentry->attributes[i]->values &&
					rentry->attributes[i]->values[j] != NULL;
					j++) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, j == 0 ? "%s" : ", %s", rentry->attributes[i]->values[j]);
			}
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "]\n");
		}
	}
	free(changes);

	char		**cur1, **cur2;

	for (cur1=lentry->modules; cur1 != NULL && *cur1 != NULL; cur1++) {
		for (cur2=rentry->modules; cur2 != NULL && *cur2 != NULL; cur2++)
			if (strcmp(*cur1, *cur2) == 0)
				break;
		if (cur2 != NULL && *cur2 != NULL)
			continue;
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:     module %s on lentry missing on rentry\n", *cur1);
	}
	for (cur2=rentry->modules; cur2 != NULL && *cur2 != NULL; cur2++) {
		for (cur1=lentry->modules; cur1 != NULL && *cur1 != NULL; cur1++)
			if (strcmp(*cur1, *cur2) == 0)
				break;
		if (cur1 != NULL && *cur1 != NULL)
			continue;
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "ALERT:     module %s on rentry missing on lentry\n", *cur2);
	}
}
