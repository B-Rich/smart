/*
 * Univention Directory Listener
 *  cache_lowlevel.c
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

#define _GNU_SOURCE /* for strndup */

#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdbool.h>
#include <sys/types.h>

#include <univention/debug.h>

#include "common.h"
#include "cache_lowlevel.h"

struct cache_entry_header {
	u_int16_t type;
	u_int32_t key_size;
	u_int32_t data_size;
};


void hex_dump(int level, void *data, u_int32_t start, u_int32_t size)
{
	int i;
	int pos;
	char hex[80];
	char str[80];
	const int per_line = 10;

	pos = 0;
	memset(hex, 0, 80);
	memset(str, 0, 80);

	for (i=0; i<size; i++) {
		snprintf(hex+(pos*3), 80-(pos*3), "%02x ", ((u_int8_t*)data+start)[i]);
		snprintf(str+pos    , 80-pos    , "%c", isprint(((char*)data+start)[i]) ? ((char*)data+start)[i] : '?');
		pos+=1;
		if ((i+1) % per_line == 0) {
			univention_debug(UV_DEBUG_LISTENER, level, "%s| %s (%08d)", hex, str, start+i-per_line);
			//fprintf(stderr, "%s| %s (%08d)\n", hex, str, start+i-per_line);
			memset(hex, 0, 80);
			memset(str, 0, 80);
			pos = 0;
		}
	}
	if (pos != 0)
		univention_debug(UV_DEBUG_LISTENER, level, "%s | %s", hex, str);
}

/* assumption: enough memory as been allocated for us */
static int append_buffer(void **data, u_int32_t *size, u_int32_t *pos, void* blob_data, u_int32_t blob_size)
{
	if (blob_size > 0) {
		memcpy((void*)(((char*)*data)+*pos), blob_data, blob_size);
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "position was=%d is=%d", *pos, *pos+blob_size);
		*pos += blob_size;
	}
	return 0;
}

static int write_header(void **data, u_int32_t *size, u_int32_t *pos, u_int16_t type, void* key_data, u_int32_t key_size, void* data_data, u_int32_t data_size)
{
	struct cache_entry_header h;
	u_int32_t need_memory;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "write_header key_size=%d data_size=%d", key_size, data_size);

	need_memory = sizeof(struct cache_entry_header)+key_size+data_size;
	if (*size < *pos+need_memory) {
		while (*size < *pos+need_memory)
			*size += BUFSIZ;
		if ((*data = realloc(*data, *size)) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "failed to allocate memory");
			return 1;
		}
	}

	h.type = type;
	h.key_size = key_size;
	h.data_size = data_size;

	append_buffer(data, size, pos, (void*) &h, sizeof(struct cache_entry_header));
	append_buffer(data, size, pos, key_data, key_size);
	append_buffer(data, size, pos, data_data, data_size);

	return 0;
}

int unparse_entry(void **data, u_int32_t *size, CacheEntry *entry)
{
	CacheEntryAttribute **attribute;
	char **value;
	char **module;
	int *length;
	int i;
	u_int32_t pos=0;

	for (attribute=entry->attributes; attribute != NULL && *attribute != NULL; attribute++) {
		for (value=(*attribute)->values, i=0, length=(*attribute)->length; *value != NULL; value++, i++) {
			write_header(data, size, &pos, 1,
					(void*) (*attribute)->name, strlen((*attribute)->name)+1,
					(void*) *value, length[i]);
		}
	}
	for (module=entry->modules; module != NULL && *module != NULL; module++) {
		write_header(data, size, &pos, 2,
				(void*) *module, strlen(*module)+1,
				NULL, 0);
	}

	/* allocated memory maybe bigger than size, but doesn't matter anyhow... */
	*size = pos;

	return 0;
}

static int read_header(void *data, u_int32_t size, u_int32_t *pos, void **key_data, u_int32_t *key_size, void **data_data, u_int32_t *data_size)
{
	struct cache_entry_header *h;

	if (*pos == size) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "end of buffer pos=size=%d", *pos);
		return 0;
	} else if (*pos+sizeof(struct cache_entry_header) > size) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "buffer exceeded pos=%d size=%d", *pos, size);
		return -1;
	}

	h = (struct cache_entry_header*)((char*)data+*pos);

	if ((h->type != 1 && h->type != 2) || h->key_size == 0) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "read_header pos=%d type=%d key_size=%d data_size=%d", *pos, h->type, h->key_size, h->data_size);
		*key_size = 0;
		*key_data = NULL;
		*data_size = 0;
		*data_data = NULL;
		return -1;
	}
	*pos += sizeof(struct cache_entry_header);
	if (*pos+h->key_size+h->data_size > size) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "buffer exceeded pos=%d size=%d", *pos, size);
		return -1;
	}

	*key_size = h->key_size;
	*key_data = (void*)((char*)data+*pos);
	*pos += *key_size;

	if (h->data_size > 0) {
		*data_size = h->data_size;
		*data_data = (void*)((char*)data+*pos);

		if (*data_size != strlen(*data_data)+1)
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "data_size and strlen don't match: %d != %zd", *data_size, strlen(*data_data)+1);
		*pos += *data_size;
	} else {
		*data_size = 0;
		*data_data = NULL;
	}
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "read_header pos=%d type=%d key_size=%d data_size=%d key_data=[%s] data_data=[%s]", *pos, h->type, h->key_size, h->data_size, (char*)*key_data, (char*)*data_data);

	return h->type;
}

int parse_entry(void *data, u_int32_t size, CacheEntry *entry)
{
	FILE *file;
	u_int16_t type;
	void *key_data, *data_data;
	u_int32_t key_size, data_size;
	u_int32_t pos=0;
	char *f;

	entry->attributes=NULL;
	entry->attribute_count=0;
	entry->modules=NULL;
	entry->module_count=0;

	while ((type = read_header(data, size, &pos, &key_data, &key_size, &data_data, &data_size)) > 0) {
		if (type == 1) {
			CacheEntryAttribute **attribute;
			bool found = false;

			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "attribute is \"%s\"", (char*)key_data);

			for (attribute=entry->attributes; attribute != NULL && *attribute != NULL; attribute++) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "current attribute is \"%s\"", (*attribute)->name);
				if (strcmp((*attribute)->name, (char*)key_data) == 0) {
					found = true;
					break;
				}
			}
			if (!found) {
				entry->attributes = realloc(entry->attributes, (entry->attribute_count+2)*sizeof(CacheEntryAttribute*));
				if (entry->attributes == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "realloc failed");
					abort(); // FIXME
				}
				entry->attributes[entry->attribute_count] = malloc(sizeof(CacheEntryAttribute));
				if (entry->attributes[entry->attribute_count] == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "malloc failed");
					abort(); // FIXME
				}
				entry->attributes[entry->attribute_count+1] = NULL;

				attribute=entry->attributes+entry->attribute_count;
				(*attribute)->name = strndup((char*)key_data, key_size);
				if ((*attribute)->name == NULL) {
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "strndup failed");
					abort(); // FIXME
				}
				entry->attributes[entry->attribute_count+1] = NULL;
				(*attribute)->values = NULL;
				(*attribute)->length = NULL;
				(*attribute)->value_count = 0;
				entry->attribute_count++;

				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "%s is at %p", (*attribute)->name, *attribute);
			}
			(*attribute)->values = realloc((*attribute)->values, ((*attribute)->value_count+2)*sizeof(char*));
			if ((*attribute)->values == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "realloc failed");
				abort(); // FIXME
			}
			(*attribute)->length = realloc((*attribute)->length, ((*attribute)->value_count+2)*sizeof(int));
			if ((*attribute)->length == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "realloc failed");
				abort(); // FIXME
			}
			// TODO: stdndup() copies until the first \0, which would be incorrect if data is binary!
			(*attribute)->values[(*attribute)->value_count] = strndup((char*)data_data, data_size);
			if ((*attribute)->values[(*attribute)->value_count] == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "strndup failed");
				abort(); // FIXME
			}
			(*attribute)->length[(*attribute)->value_count] = data_size;
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "value is \"%s\"", (*attribute)->values[(*attribute)->value_count]);
			(*attribute)->values[(*attribute)->value_count+1] = NULL;
			(*attribute)->value_count++;
		} else if (type == 2) {
			entry->modules = realloc(entry->modules, (entry->module_count+2)*sizeof(char*));
			entry->modules[entry->module_count] = strndup((char*)key_data, key_size);
			if (entry->modules[entry->module_count] == NULL) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "strndup failed");
				abort(); // FIXME
			}
			entry->modules[entry->module_count+1] = NULL;
			entry->module_count++;
		} else {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "bad data block at position %d:", pos);
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "last 100 bytes of previous entry:");
			hex_dump(UV_DEBUG_ERROR, data, pos-1000 < 0 ? 0 : pos-1000, pos-1000 < 0 ? pos : 1000);
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "first 100 bytes of current entry:");
			hex_dump(UV_DEBUG_ERROR, data, pos, pos+1000 > size ? size-pos : 1000);

			if (asprintf(&f, "%s/bad_cache", cache_dir) < 0) abort();
			if ((file = fopen(f, "w")) != NULL) {
				fprintf(file, "Check log file");
				fclose(file);
			}
			free(f);

			return -1;
		}
	}

	return 0;
}
