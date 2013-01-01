# -*- coding: iso-8859-15 -*-

try:
	import univention.ucslint.base as uub
except ImportError:
	import ucslint.base as uub
import re
import os
from itertools import product

class UniventionPackageCheck(uub.UniventionPackageCheckDebian):
	def __init__(self):
		super(UniventionPackageCheck, self).__init__()
		self.name = '0011-Control'

	def getMsgIds(self):
		return { '0011-1': [ uub.RESULT_WARN, 'failed to open/read file' ],
				 '0011-2': [ uub.RESULT_ERROR, 'source package name differs in debian/control and debian/changelog' ],
				 '0011-3': [ uub.RESULT_WARN, 'wrong section - should be "Univention"' ],
				 '0011-4': [ uub.RESULT_WARN, 'wrong priority - should be "optional"' ],
				 '0011-5': [ uub.RESULT_ERROR, 'wrong maintainer - should be "Univention GmbH <packages@univention.de>"' ],
				 '0011-6': [ uub.RESULT_ERROR, 'XS-Python-Version without python-central in build-dependencies' ],
				 '0011-7': [ uub.RESULT_ERROR, 'XS-Python-Version without XB-Python-Version in binary package entries' ],
				 '0011-8': [ uub.RESULT_WARN, 'XS-Python-Version should be "2.4"' ],
				 '0011-9': [ uub.RESULT_ERROR, 'cannot determine source package name' ],
				 '0011-10': [uub.RESULT_ERROR, 'parsing error in debian/control' ],
				 '0011-11': [uub.RESULT_WARN,  'debian/control: XS-Python-Version is not required any longer' ],
				 '0011-12': [uub.RESULT_ERROR, 'debian/control: please use python-support instead of python-central in Build-Depends' ],
				 '0011-13': [uub.RESULT_WARN,  'debian/control: ucslint is missing in Build-Depends' ],
				 '0011-14': [uub.RESULT_WARN, 'no matching package in debian/control'],
				 '0011-15': [uub.RESULT_WARN, 'non-prefixed debhelper file'],
				 '0011-16': [uub.RESULT_INFO, 'unknown debhelper file'],
				 }

	def postinit(self, path):
		""" checks to be run before real check or to create precalculated data for several runs. Only called once! """
		pass

	def check(self, path):
		""" the real check """
		super(UniventionPackageCheck, self).check(path)

		fn_changelog = os.path.join(path, 'debian', 'changelog')
		try:
			content_changelog = open(fn_changelog, 'r').read(1024)
		except IOError:
			self.addmsg('0011-1', 'failed to open and read file', filename=fn_changelog)
			return

		fn_control = os.path.join(path, 'debian', 'control')
		try:
			parser = uub.ParserDebianControl(fn_control)
		except uub.FailedToReadFile:
			self.addmsg('0011-1', 'failed to open and read file', filename=fn_control)
			return
		except uub.UCSLintException:
			self.addmsg('0011-11', 'parsing error', filename=fn_control)
			return

		# compare package name
		reChangelogPackage = re.compile('^([a-z0-9.-]+) \((.*?)\) (.*?)\n')
		match = reChangelogPackage.match(content_changelog)
		if match:
			srcpkgname = match.group(1)
		else:
			srcpkgname = None
			self.addmsg('0011-9', 'cannot determine source package name', filename=fn_changelog)

		controlpkgname = parser.source_section.get('Source')
		if not controlpkgname:
			self.addmsg('0011-9', 'cannot determine source package name', filename=fn_control)

		if srcpkgname and controlpkgname:
			if srcpkgname != controlpkgname:
				self.addmsg('0011-2', 'source package name differs in debian/changelog and debian/control', filename=fn_changelog)


		# parse source section of debian/control
		if not parser.source_section.get('Section', '') in ( 'univention' ):
			self.addmsg('0011-3', 'wrong Section entry - should be "univention"', filename=fn_control)

		if not parser.source_section.get('Priority', '') in ( 'optional' ):
			self.addmsg('0011-4', 'wrong Priority entry - should be "optional"', filename=fn_control)

		if not parser.source_section.get('Maintainer', '') in ( 'Univention GmbH <packages@univention.de>' ):
			self.addmsg('0011-5', 'wrong Maintainer entry - should be "Univention GmbH <packages@univention.de>"', filename=fn_control)

		if parser.source_section.get('XS-Python-Version', ''):
			self.addmsg('0011-11', 'XS-Python-Version is not required any longer', filename=fn_control)

		if 'python-central' in parser.source_section.get('Build-Depends', ''):
			self.addmsg('0011-12', 'please use python-support instead of python-central in Build-Depends', filename=fn_control)

		if not 'ucslint' in parser.source_section.get('Build-Depends', ''):
			self.addmsg('0011-13', 'ucslint is missing in Build-Depends', filename=fn_control)

		self.check_debhelper(path, parser)

	EXCEPTION_FILES = set((
			'changelog', # dh_installchangelogs default
			'clean', # dh_clean
			'compat', # dh
			'control',
			'copyright', # dh_installdocs default
			'files', # dh_builddeb
			'NEWS', # dh_installchangelogs default
			'rules',
			'source.lintian-overrides', # dh_lintian
			'ucslint.overrides',
			))

	KNOWN_DH_FILES = set((
			'bash-completion', # dh_bash-completion
			'bug-control', # dh_bugfiles
			'bug-presubj', # dh_bugfiles
			'bug-script', # dh_bugfiles
			'changelog', # dh_installchangelogs
			'compress', # dh_compress
			'conffiles', # dh_installdeb
			'config', # dh_installdebconf
			'copyright', # dh_installdocs
			'cron.daily', # dh_installcron
			'cron.d', # dh_installcron
			'cron.hourly', # dh_installcron
			'cron.monthly', # dh_installcron
			'cron.weekly', # dh_installcron
			'debhelper.log', # dh
			'default', # dh_installinit
			'dirs', # dh_installdirs
			'doc-base', # dh_installdocs
			'docs', # dh_installdocs
			'emacsen-install', # dh_installemacsen
			'emacsen-remove', # dh_installemacsen
			'emacsen-startup', # dh_installemacsen
			'examples', # dh_installexamples
			'files', # dh_movefiles
			'gconf-defaults', # dh_gconf
			'gconf-mandatory', # dh_gconf
			'if-down', # dh_installifupdown
			'if-pre-down', # dh_installifupdown
			'if-pre-up', # dh_installifupdown
			'if-up', # dh_installifupdown
			'info', # dh_installinfo
			'init', # dh_installinit
			'install', # dh_install
			'links', # dh_link
			'lintian-overrides', # dh_lintian
			'logcheck.cracking', # dh_installlogcheck
			'logcheck.ignore.paranoid', # dh_installlogcheck
			'logcheck.ignore.server', # dh_installlogcheck
			'logcheck.ignore.workstation', # dh_installlogcheck
			'logcheck.violations', # dh_installlogcheck
			'logcheck.violations.ignore', # dh_installlogcheck
			'manpages', # dh_installman
			'menu', # dh_installmenu
			'menu-method', # dh_installmenu
			'mine', # dh_installmime
			'modprobe', # dh_installmodules
			'modules', # dh_installmodules
			'NEWS', # dh_installchangelogs
			'pam', # dh_installpam
			'postinst', # dh_installdeb
			'postinst.debhelper', # dh_installdeb
			'postrm', # dh_installdeb
			'postrm.debhelper', # dh_installdeb
			'ppp.ip-down', # dh_installppp
			'ppp.ip-up', # dh_installppp
			'preinst', # dh_installdeb
			'preinst.debhelper', # dh_installdeb
			'prerm', # dh_installdeb
			'prerm.debhelper', # dh_installdeb
			'README.Debian', # dh_installdocs
			'sgmlcatalogs', # dh_installcatalogs
			'sharedmimeinfo', # dh_installmime
			'shlibs', # dh_installdeb
			'substvars', # dh_gencontrol
			'symbols', # dh_makeshlibs
			'symbols.i386', # dh_makeshlibs
			'templates', # dh_installdebconf
			'TODO', # dh_installdocs
			'triggers', # dh_installdeb
			'udev', # dh_installudev
			'umc-modules', # dh-umc-modules-install
			'univention-config-registry-categories', # univention-install-config-registry-info
			'univention-config-registry-mapping', # univention-install-config-registry-info
			'univention-config-registry', # univention-install-config-registry
			'univention-config-registry-variables', # univention-install-config-registry-info
			'univention-service', # univention-install-service-info
			'upstart', # dh_installinit
			'wm', # dh_installwm
			))

	def check_debhelper(self, path, parser):
		"""Check for debhelper package files."""
		if len(parser.binary_sections) == 1:
			# If there is only one binary package, accept the non-prefixed files ... for now
			return

		pkgs = [pkg['Package'] for pkg in parser.binary_sections]

		debianpath = os.path.join(path, 'debian')
		files = os.listdir(debianpath)

		for pkg, suffix in product(pkgs, UniventionPackageCheck.KNOWN_DH_FILES):
			fn = '%s.%s' % (pkg, suffix)
			try:
				files.remove(fn)
			except ValueError:
				continue

		for rel_name in files:
			fn = os.path.join(debianpath, rel_name)

			if rel_name in UniventionPackageCheck.EXCEPTION_FILES:
				continue

			if not os.path.isfile(fn):
				continue

			for suffix in UniventionPackageCheck.KNOWN_DH_FILES:
				if rel_name == suffix:
					self.addmsg('0011-15', 'non-prefixed debhelper file of package "%s"' % (pkgs[0],), filename=fn)
					break
				elif rel_name.endswith('.%s' % (suffix,)):
					self.addmsg('0011-14', 'no matching package in debian/control', filename=fn)
					break
			else:
				self.addmsg('0011-16', 'unknown debhelper file', filename=fn)
