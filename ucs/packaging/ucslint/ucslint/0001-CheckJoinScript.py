# -*- coding: iso-8859-15 -*-
# pylint: disable-msg=C0301

try:
	import univention.ucslint.base as uub
except ImportError:
	import ucslint.base as uub
import re
import os

# Pr�fen, ob ein Join-Skript im Paket vorhanden ist
# - Pr�fen, ob das Join-Skript in rules installiert wird
# - Pr�fen, ob das Join-Skript in postinst aufgerufen wird
# - Pr�fen, ob das Join-Skript "VERSION=" enth�lt
# - Pr�fen, ob das Join-Skript " v${VERSION} " enth�lt
#
# FIXME: Pr�fen, ob das Join-Skript den richtigen Dateinamen per grep in .index.txt sucht und mit echo eintr�gt
# FIXME: Pr�fen, ob das Join-Skript im postinst richtig aufgerufen wird:
#           if [ "$server_role" = "domaincontroller_master" ] || [ "$server_role" = "domaincontroller_backup" ]; then
#               /usr/lib/univention-install/38univention-management-console-distribution.inst || true
#           fi
#           ==> mit "|| true" und Abfrage auf DC Master oder DC Backup


class UniventionPackageCheck(uub.UniventionPackageCheckDebian):
	def __init__(self):
		super(UniventionPackageCheck, self).__init__()
		self.name = '0001-CheckJoinScript'

	def getMsgIds(self):
		return { '0001-1': [ uub.RESULT_STYLE, 'the old command "univention-admin" is used' ],
				 '0001-2': [ uub.RESULT_ERROR, '"$@" for passing credentials to univention-directory-manager is missing' ],
				 '0001-3': [ uub.RESULT_WARN,  'join scripts are now versioned - the variable VERSION is not set' ],
				 '0001-4': [ uub.RESULT_WARN,  'join scripts are now versioned - the string " v${VERSION} " within grep/echo is missing' ],
				 '0001-5': [ uub.RESULT_ERROR, 'debian/rules is missing' ],
				 '0001-6': [ uub.RESULT_WARN,  'join script seems not to be installed via debian/rules' ],
				 '0001-7': [ uub.RESULT_WARN,  'join script seems not to be called in any postinst file' ],
				 '0001-8': [ uub.RESULT_WARN,  'join scripts should be called with "|| true" do avoid failing postinst scripts if "set -e" is used' ],
				 '0001-9': [ uub.RESULT_WARN,  'cannot open specified file' ],
				 '0001-10': [ uub.RESULT_ERROR, 'join script contains "eval $(ucr shell)" without proper quoting' ], # unused, moved to 0017
				 '0001-11': [ uub.RESULT_ERROR, 'join script contains lines with unquoted $@' ],
				 '0001-12': [ uub.RESULT_ERROR, 'join script contains more than one line with VERSION=  statement' ],
				 '0001-13': [ uub.RESULT_ERROR, 'join script does not include "joinscripthelper.lib"' ],
				 '0001-14': [ uub.RESULT_ERROR, 'join script does not call "joinscript_init"' ],
				 '0001-15': [ uub.RESULT_ERROR, 'join script does not call "joinscript_save_current_version"' ],
				 }

	def postinit(self, path):
		""" checks to be run before real check or to create precalculated data for several runs. Only called once! """
		pass

	RE_LINE_ENDS_WITH_TRUE = re.compile('\|\|[ \t]+true[ \t]*$')
	RE_LINE_CONTAINS_SET_E = re.compile('\n[\t ]*set -e', re.M)
	RE_DH_UMC = re.compile(r'\bdh-umc-module-install\b')

	def check_join_script(self, filename):
		"""Check a single join script."""
		try:
			content = open(filename, 'r').read()
		except IOError:
			self.addmsg('0001-9', 'failed to open and read file', filename)
			return

		lines = content.splitlines()
		cnt = { 'version': 0,
				'vversion': 0,
				'credential_arg_missing': 0,
				'unquoted_credential_arg': 0,
				'old_cmd_name': 0,
				'joinscripthelper.lib': 0,
				'joinscript_init': 0,
				'joinscript_save_current_version': 0,
				}
		for line in lines:
			line = line.strip()
			if not line or line.startswith('#'):
				continue

			# check for old style joinscript
			if line.startswith( 'VERSION=' ):
				cnt['version'] += 1
			if line.find( ' v${VERSION} ' ) >= 0:
				cnt['vversion'] += 1

			# check for new style joinscript
			if line.startswith('source /usr/share/univention-join/joinscripthelper.lib') or line.startswith('. /usr/share/univention-join/joinscripthelper.lib'):
				cnt['joinscripthelper.lib'] += 1
			if 'joinscript_init' in line:
				cnt['joinscript_init'] += 1
			if 'joinscript_save_current_version' in line:
				cnt['joinscript_save_current_version'] += 1

			# check udm calls
			if 'univention-admin ' in line or 'univention-directory-manager ' in line or 'udm ' in line:
					if 'univention-admin ' in line:
						cnt['old_cmd_name'] += 1
					if not ' $@ ' in line and not ' "$@" ' in line:
						cnt['credential_arg_missing'] += 1
						self.debug('line contains no $@:\n%s' % line)
			if ' $@ ' in line:
				cnt['unquoted_credential_arg'] += 1
				self.debug('line contains unquoted $@:\n%s' % line)

		if cnt['old_cmd_name'] > 0:
			self.addmsg( '0001-1', 'join script contains %d lines using "univention-admin"' % (cnt['old_cmd_name']), filename)
		if cnt['credential_arg_missing'] > 0:
			self.addmsg( '0001-2', 'join script contains %s lines with missing "$@"' % (cnt['credential_arg_missing']), filename)
		if cnt['unquoted_credential_arg'] > 0:
			self.addmsg( '0001-11', 'join script contains %d lines with unquoted $@' % (cnt['unquoted_credential_arg']), filename)

		if cnt['version'] == 0:
			self.addmsg( '0001-3', 'join script does not set VERSION', filename)
		if cnt['version'] > 1:
			self.addmsg( '0001-12', 'join script does set VERSION more than once', filename)

		if not cnt['joinscripthelper.lib']:
			# no usage of joinscripthelper.lib
			if cnt['vversion'] > 0 and cnt['vversion'] < 2:
				self.addmsg( '0001-4', 'join script does not grep for " v${VERSION} "', filename)
			elif cnt['vversion'] == 0:
				self.addmsg( '0001-13', 'join script does not use joinscripthelper.lib', filename)
		else:
			if not cnt['joinscript_init']:
				self.addmsg( '0001-14', 'join script does not use joinscript_init', filename)
			if not cnt['joinscript_save_current_version']:
				self.addmsg( '0001-15', 'join script does not use joinscript_save_current_version', filename)

	def check(self, path):
		""" the real check """
		super(UniventionPackageCheck, self).check(path)

		fnlist_joinscripts = {}

		#
		# search join scripts
		#
		for f in os.listdir( path ):
			if f.endswith('.inst') and f[0:2].isdigit():
				fn = os.path.join(path, f)
				fnlist_joinscripts[fn] = False
				self.debug('found %s' % fn)

		#
		# check if join scripts use versioning
		#
		for js in fnlist_joinscripts.keys():
			self.check_join_script(js)

		#
		# check if join scripts are present in debian/rules || debian/*.install
		#
		found = {}
		debianpath = os.path.join( path, 'debian' )
		# get all .install files
		fnlist = list(uub.FilteredDirWalkGenerator(debianpath, suffixes=['.install']))
		# append debian/rules
		fn_rules = os.path.join(path, 'debian', 'rules' )
		fnlist.append(fn_rules)

		# Look for dh-umc-modules-install
		try:
			content = open(fn_rules, 'r').read()
		except IOError:
			self.addmsg( '0001-9', 'failed to open and read file', fn )
		else:
			if UniventionPackageCheck.RE_DH_UMC.search(content):
				self.debug('Detected use of dh-umc-module-install')
				for fn in uub.FilteredDirWalkGenerator(debianpath, suffixes=['.umc-modules']):
					package = os.path.basename(fn)[:-len('.umc-modules')]
					inst = '%s.inst' % (package,)
					for js in fnlist_joinscripts.keys():
						if js.endswith(inst):
							self.debug('%s installed by dh-umc-module-install' % (js,))
							found[js] = found.get(js, 0) + 1
							fnlist_joinscripts[js] = True

		for fn in fnlist:
			try:
				content = open(fn, 'r').read()
			except IOError:
				self.addmsg( '0001-9', 'failed to open and read file', fn )

			for js in fnlist_joinscripts.keys():
				name = os.path.basename(js)
				self.debug('looking for %s in %s' % (name, fn))
				if name in content:
					self.debug('found %s in %s' % (name, fn))
					found[js] = found.get(js,0) + 1

		for js in fnlist_joinscripts.keys():
			if found.get(js,0) == 0:
				self.addmsg( '0001-6', 'join script is not mentioned in debian/rules or *.install files', js )

		#
		# check if join scripts are present in debian/*postinst
		#
		for f in os.listdir( os.path.join(path, 'debian') ):
			if ( f.endswith('.postinst') and not f.endswith('.debhelper.postinst') ) or ( f == 'postinst' ):
				fn = os.path.join( path, 'debian', f )
				self.debug('loading %s' % (fn))
				try:
					content = open(fn, 'r').read()
				except IOError:
					self.addmsg( '0001-9', 'failed to open and read file', fn )
					continue

				for js in fnlist_joinscripts.keys():
					name = os.path.basename(js)
					self.debug('looking for %s in %s' % (name, fn))
					if name in content:
						fnlist_joinscripts[js] = True
						self.debug('found %s in %s' % (name, fn))

						match = UniventionPackageCheck.RE_LINE_CONTAINS_SET_E.search(content)
						if match:
							self.debug('found "set -e" in %s' % fn)
							for line in content.splitlines():
								if name in line:
									match = UniventionPackageCheck.RE_LINE_ENDS_WITH_TRUE.search(line)
									if not match:
										self.addmsg('0001-8', 'the join script %s is not called with "|| true" but "set -e" is set' % (name,), fn)

		for js, found in fnlist_joinscripts.items():
			if not found:
				self.addmsg( '0001-7', 'Join script is not mentioned in debian/*.postinst', js)
