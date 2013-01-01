/*
 * Python Heimdal
 *	Bindings for the encryption API of heimdal
 *
 * Copyright 2003-2012 Univention GmbH
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

#include <Python.h>

#include <krb5.h>

#include "error.h"
#include "context.h"
#include "enctype.h"

static struct PyMethodDef enctype_methods[];

krb5EnctypeObject *enctype_from_enctype(krb5_context context, krb5_enctype enctype)
{
	krb5EnctypeObject *self = (krb5EnctypeObject *) PyObject_NEW(krb5EnctypeObject, &krb5EnctypeType);

	if (self == NULL)
		return NULL;
	self->context = context;
	self->enctype = enctype;

	return self;
}


krb5EnctypeObject *enctype_new(PyObject *unused, PyObject *args)
{
	krb5_error_code ret;
	krb5ContextObject *context;
	char *enctype_string;
	krb5EnctypeObject *self = (krb5EnctypeObject *) PyObject_NEW(krb5EnctypeObject, &krb5EnctypeType);
	int error = 0;

	if (!PyArg_ParseTuple(args, "Os", &context, &enctype_string))
		return NULL;

	if (self == NULL)
		return NULL;
	self->context = context->context;

	ret = krb5_string_to_enctype(context->context, enctype_string,
			&self->enctype);
	if (ret) {
		error = 1;
		krb5_exception(NULL, ret);
		goto out;
	}

 out:
	if (error)
		return NULL;
	else
		return self;
}

PyObject *enctype_string(krb5EnctypeObject *self)
{
	krb5_error_code ret;
	char *enctype_c_string;
	PyObject *enctype_string;
	int error = 0;

	ret = krb5_enctype_to_string(self->context, self->enctype, &enctype_c_string);
	if (ret) {
		error = 1;
		krb5_exception(NULL, ret);
		goto out;
	}
	enctype_string = PyString_FromString(enctype_c_string);
	free(enctype_c_string);

 out:
	if (error)
		return NULL;
	else
		return enctype_string;

}

PyObject *enctype_int(krb5EnctypeObject *self, PyObject *args)
{
	return PyInt_FromLong(self->enctype);
}

static PyObject *enctype_getattr(krb5EnctypeObject *self, char *name)
{
	return Py_FindMethod(enctype_methods, (PyObject *)self, name);
}

void enctype_destroy(krb5EnctypeObject *self)
{
	/* enctype really is integer; nothing to free */
	PyObject_Del( self );
}

PyTypeObject krb5EnctypeType = {
	PyObject_HEAD_INIT(&PyType_Type)
	0,				/*ob_size*/
	"krb5Enctype",			/*tp_name*/
	sizeof(krb5EnctypeObject),	/*tp_basicsize*/
	0,				/*tp_itemsize*/
	/* methods */
	(destructor)enctype_destroy,	/*tp_dealloc*/
	0,				/*tp_print*/
	(getattrfunc)enctype_getattr,	/*tp_getattr*/
	0,				/*tp_setattr*/
	0,				/*tp_compare*/
	(reprfunc)enctype_string,	/*tp_repr*/
	0,				/*tp_repr*/
	0,				/*tp_as_number*/
	0,				/*tp_as_sequence*/
	0,				/*tp_as_mapping*/
	0,				/*tp_hash*/
};

static struct PyMethodDef enctype_methods[] = {
	{"toint", (PyCFunction)enctype_int, METH_VARARGS, "Convert enctype to integer"},
	{NULL, NULL, 0, NULL}
};
