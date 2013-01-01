#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: software management
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

# standard library
import locale
import sys
import urllib
import urllib2
import re

# related third party
import notifier
import notifier.threads

# univention
from univention.lib.package_manager import PackageManager, LockError
from univention.management.console.log import MODULE
from univention.management.console.modules.decorators import simple_response, sanitize, sanitize_list, multi_response
from univention.management.console.modules.sanitizers import PatternSanitizer, MappingSanitizer, DictSanitizer, StringSanitizer, ChoicesSanitizer, ListSanitizer, EmailSanitizer, BooleanSanitizer
from univention.updater import UniventionUpdater
from univention.updater.errors import ConfigurationError
import univention.config_registry
import univention.management.console as umc
import univention.management.console.modules as umcm

# local application
from app_center import Application, LICENSE
from sanitizers import basic_components_sanitizer, advanced_components_sanitizer, add_components_sanitizer
import constants
import util


_ = umc.Translation('univention-management-console-module-appcenter').translate

class Instance(umcm.Base):
	def init(self):
		self.ucr = univention.config_registry.ConfigRegistry()
		self.ucr.load()

		util.install_opener(self.ucr)

		self.package_manager = PackageManager(
			info_handler=MODULE.process,
			step_handler=None,
			error_handler=MODULE.warn,
			lock=False,
			always_noninteractive=True,
		)
		self.uu = UniventionUpdater(False)
		self.component_manager = util.ComponentManager(self.ucr, self.uu)

		# in order to set the correct locale for Application
		locale.setlocale(locale.LC_ALL, str(self.locale))

	@sanitize(email=EmailSanitizer(required=True))
	@simple_response
	def request_new_license(self, email):
		license = LICENSE.dump_data()
		if license is None:
			raise umcm.UMC_CommandError(_('Cannot parse License from LDAP'))
		data = {}
		data['email'] = email
		data['licence'] = license
		data = urllib.urlencode(data)
		url = 'https://license.univention.de/keyid/conversion/submit'
		request = urllib2.Request(url, data=data, headers={'User-agent' : 'UMC/AppCenter'})
		try:
			util.urlopen(request)
		except Exception as e:
			try:
				# try to parse an html error
				body = e.read()
				detail = re.search('<span id="details">(?P<details>.*?)</span>',  body).group(1)
			except:
				detail = str(e)
			raise umcm.UMC_CommandError(_('An error occurred while sending the request: %s') % detail)
		else:
			return True

	@sanitize(pattern=PatternSanitizer(default='.*'))
	@simple_response
	def query(self, pattern):
		LICENSE.reload()
		try:
			applications = Application.all(force_reread=True)
		except (urllib2.HTTPError, urllib2.URLError) as e:
			raise umcm.UMC_CommandError(_('Could not query App Center: %s') % e)
		result = []
		self.package_manager.reopen_cache()
		for application in applications:
			if pattern.search(application.name):
				props = application.to_dict(self.package_manager)

				# delete larger entries
				for ikey in ('readmeupdate', 'licenseagreement'):
					if ikey in props:
						del props[ikey]

				result.append(props)
		return result

	@sanitize(application=StringSanitizer(minimum=1, required=True))
	@simple_response
	def get(self, application):
		LICENSE.reload()
		application = Application.find(application)
		self.package_manager.reopen_cache()
		return application.to_dict(self.package_manager)

	@sanitize(
			function=ChoicesSanitizer(['install', 'uninstall', 'update'], required=True),
			application=StringSanitizer(minimum=1, required=True),
			force=BooleanSanitizer()
		)
	def invoke(self, request):
		function = request.options.get('function')
		application_id = request.options.get('application')
		application = Application.find(application_id)
		force = request.options.get('force')
		try:
			# make sure that the application cane be installed/updated
			can_continue = True
			result = {
				'install' : [],
				'remove' : [],
				'broken' : [],
			}
			if not application:
				MODULE.info('Application not found: %s' % application_id)
				can_continue = False
			elif function == 'install' and not application.can_be_installed(self.package_manager):
				MODULE.info('Application cannot be installed: %s' % application_id)
				can_continue = False
			elif function == 'update' and not application.can_be_updated():
				MODULE.info('Application cannot be updated: %s' % application_id)
				can_continue = False

			if can_continue and function in ('install', 'update'):
				result = application.install_dry_run(self.package_manager, self.component_manager, remove_component=False)
				if result['broken'] or (result['remove'] and not force):
					MODULE.info('Remove component: %s' % application_id)
					self.component_manager.remove_app(application)
					self.package_manager.update()
					can_continue = False
			elif can_continue and function in ('uninstall',) and not force:
				result['remove'] = application.uninstall_dry_run(self.package_manager)
				can_continue = False
			result['can_continue'] = can_continue
			self.finished(request.id, result)

			if can_continue:
				def _thread(module, application, function):
					with module.package_manager.locked(reset_status=True, set_finished=True):
						with module.package_manager.no_umc_restart():
							if function in ('install', 'update'):
								# dont have to add component: already added during dry_run
								return application.install(module.package_manager, module.component_manager, add_component=False)
							else:
								return application.uninstall(module.package_manager, module.component_manager)
				def _finished(thread, result):
					if isinstance(result, BaseException):
						MODULE.warn('Exception during %s %s: %s' % (function, application_id, str(result)))
				thread = notifier.threads.Simple('invoke',
					notifier.Callback(_thread, self, application, function), _finished)
				thread.run()
		except LockError:
			# make it thread safe: another process started a package manager
			# this module instance already has a running package manager
			raise umcm.UMC_CommandError(_('Another package operation is in progress'))

	@simple_response
	def app_center_app_license(self, application):
		application = Application.find(application)
		if not application or not application.get('licensefile'):
			raise umcm.UMC_CommandError(_('No license file available for application: %s') % (application.id))

		# open the license file and replace line breaks with BR-tags
		fp = util.urlopen(application.get('licensefile'))
		txt = ''.join(fp.readlines()).strip()
		txt = txt.replace('\n\n\n', '\n<br>\n<br>\n<br>\n')
		txt = txt.replace('\n\n', '\n<br>\n<br>\n')
		return txt

	@simple_response
	def packages_sections(self):
		""" fills the 'sections' combobox in the search form """

		sections = set()
		for package in self.package_manager.packages():
			sections.add(package.section)

		return sorted(sections)

	@sanitize(pattern=PatternSanitizer(required=True))
	@simple_response
	def packages_query(self, pattern, section='all', key='package'):
		""" Query to fill the grid. Structure is fixed here. """
		result = []
		for package in self.package_manager.packages():
			if section == 'all' or package.section == section:
				toshow = False
				if pattern.pattern == '^.*$':
					toshow = True
				elif key == 'package' and pattern.search(package.name):
					toshow = True
				elif key == 'description' and pattern.search(package.candidate.raw_description):
					toshow = True
				if toshow:
					result.append(self._package_to_dict(package, full=False))
		return result

	@simple_response
	def packages_get(self, package):
		""" retrieves full properties of one package """

		package = self.package_manager.get_package(package)
		if package is not None:
			return self._package_to_dict(package, full=True)
		else:
			# TODO: 404?
			return {}

	@sanitize(function=MappingSanitizer({
				'install' : 'install',
				'upgrade' : 'install',
				'uninstall' : 'remove',
			}, required=True),
		packages=ListSanitizer(StringSanitizer(minimum=1), required=True)
		)
	@simple_response
	def packages_invoke_dry_run(self, packages, function):
		packages = self.package_manager.get_packages(packages)
		kwargs = {'install' : [], 'remove' : [], 'dry_run' : True}
		if function == 'install':
			kwargs['install'] = packages
		else:
			kwargs['remove'] = packages
		return dict(zip(['install', 'remove', 'broken'], self.package_manager.mark(**kwargs)))

	@sanitize(function=MappingSanitizer({
				'install' : 'install',
				'upgrade' : 'install',
				'uninstall' : 'remove',
			}, required=True),
		packages=ListSanitizer(StringSanitizer(minimum=1), required=True)
		)
	def packages_invoke(self, request):
		""" executes an installer action """
		packages = request.options.get('packages')
		function = request.options.get('function')

		try:
			with self.package_manager.locked(reset_status=True):
				not_found = [pkg_name for pkg_name in packages if self.package_manager.get_package(pkg_name) is None]
				self.finished(request.id, {'not_found' : not_found})

				if not not_found:
					def _thread(package_manager, function, packages):
						with package_manager.locked(set_finished=True):
							with package_manager.no_umc_restart():
								if function == 'install':
									package_manager.install(*packages)
								else:
									package_manager.uninstall(*packages)
					def _finished(thread, result):
						if isinstance(result, BaseException):
							MODULE.warn('Exception during %s %s: %r' % (function, packages, str(result)))
					thread = notifier.threads.Simple('invoke', 
						notifier.Callback(_thread, self.package_manager, function, packages), _finished)
					thread.run()
		except LockError:
			# make it thread safe: another process started a package manager
			# this module instance already has a running package manager
			raise umcm.UMC_CommandError(_('Another package operation is in progress'))

	@simple_response
	def progress(self):
		timeout = 5
		return self.package_manager.poll(timeout)

	def _package_to_dict(self, package, full):
		""" Helper that extracts properties from a 'apt_pkg.Package' object
			and stores them into a dictionary. Depending on the 'full'
			switch, stores only limited (for grid display) or full
			(for detail view) set of properties.
		"""
		installed = package.installed # may be None
		candidate = package.candidate

		result = {
			'package': package.name,
			'installed': package.is_installed,
			'upgradable': package.is_upgradable,
			'summary': candidate.summary,
		}

		# add (and translate) a combined status field
		# *** NOTE *** we translate it here: if we would use the Custom Formatter
		#		of the grid then clicking on the sort header would not work.
		if package.is_installed:
			if package.is_upgradable:
				result['status'] = _('upgradable')
			else:
				result['status'] = _('installed')
		else:
			result['status'] = _('not installed')

		# additional fields needed for detail view
		if full:
			result['section'] = package.section
			result['priority'] = package.priority
			# Some fields differ depending on whether the package is installed or not:
			if package.is_installed:
				result['summary'] = installed.summary # take the current one
				result['description'] = installed.description
				result['installed_version'] = installed.version
				result['size'] = installed.installed_size
				if package.is_upgradable:
					result['candidate_version'] = candidate.version
			else:
				del result['upgradable'] # not installed: don't show 'upgradable' at all
				result['description'] = candidate.description
				result['size'] = candidate.installed_size
				result['candidate_version'] = candidate.version
			# format size to handle bytes
			size = result['size']
			byte_mods = ['B', 'kB', 'MB']
			for byte_mod in byte_mods:
				if size < 10000:
					break
				size = float(size) / 1000 # MB, not MiB
			else:
				size = size * 1000 # once too often
			if size == int(size):
				format_string = '%d %s'
			else:
				format_string = '%.2f %s'
			result['size'] = format_string % (size, byte_mod)

		return result

	@simple_response
	def components_query(self):
		"""	Returns components list for the grid in the ComponentsPage.
		"""
		# be as current as possible.
		self.uu.ucr_reinit()
		self.ucr.load()

		result = []
		for comp in self.uu.get_all_components():
			result.append(self.component_manager.component(comp))
		return result

	@sanitize_list(StringSanitizer())
	@multi_response(single_values=True)
	def components_get(self, iterator, component_id):
		# be as current as possible.
		self.uu.ucr_reinit()
		self.ucr.load()
		for component_id in iterator:
			yield self.component_manager.component(component_id)

	@sanitize_list(DictSanitizer({'object' : advanced_components_sanitizer}))
	@multi_response
	def components_put(self, iterator, object):
		"""Writes back one or more component definitions.
		"""
		# umc.widgets.Form wraps the real data into an array:
		#
		#	[
		#		{
		#			'object' : { ... a dict with the real data .. },
		#			'options': None
		#		},
		#		... more such entries ...
		#	]
		#
		# Current approach is to return a similarly structured array,
		# filled with elements, each one corresponding to one array
		# element of the request:
		#
		#	[
		#		{
		#			'status'	:	a number where 0 stands for success, anything else
		#							is an error code
		#			'message'	:	a result message
		#			'object'	:	a dict of field -> error message mapping, allows
		#							the form to show detailed error information
		#		},
		#		... more such entries ...
		#	]
		with util.set_save_commit_load(self.ucr) as super_ucr:
			for object, in iterator:
				yield self.component_manager.put(object, super_ucr)
		self.package_manager.update()

	# do the same as components_put (update)
	# but dont allow adding an already existing entry
	components_add = sanitize_list(DictSanitizer({'object' : add_components_sanitizer}))(components_put)
	components_add.__name__ = 'components_add'

	@sanitize_list(StringSanitizer())
	@multi_response(single_values=True)
	def components_del(self, iterator, component_id):
		for component_id in iterator:
			yield self.component_manager.remove(component_id)
		self.package_manager.update()

	@multi_response
	def settings_get(self, iterator):
		# *** IMPORTANT *** Our UCR copy must always be current. This is not only
		#	to catch up changes made via other channels (ucr command line etc),
		#	but also to reflect the changes we have made ourselves!
		self.ucr.load()

		for _ in iterator:
			yield {
				'maintained' : self.ucr.is_true('repository/online/maintained', False),
				'unmaintained' : self.ucr.is_true('repository/online/unmaintained', False),
				'server' : self.ucr.get('repository/online/server', ''),
				'prefix' : self.ucr.get('repository/online/prefix', ''),
			}

	@sanitize_list(DictSanitizer({'object' : basic_components_sanitizer}),
		min_elements=1, max_elements=1 # moduleStore with one element...
	)
	@multi_response
	def settings_put(self, iterator, object):
		# FIXME: returns values although it should yield (multi_response)
		changed = False
		# Set values into our UCR copy.
		try:
			with util.set_save_commit_load(self.ucr) as super_ucr:
				for object, in iterator:
					for key, value in object.iteritems():
						MODULE.info("   ++ Setting new value for '%s' to '%s'" % (key, value))
						super_ucr.set_registry_var('%s/%s' % (constants.ONLINE_BASE, key), value)
				changed = super_ucr.changed()
		except Exception as e:
			MODULE.warn("   !! Writing UCR failed: %s" % str(e))
			return [{'message' : str(e), 'status' : constants.PUT_WRITE_ERROR}]

		self.package_manager.update()

		# Bug #24878: emit a warning if repository is not reachable
		try:
			updater = self.uu
			for line in updater.print_version_repositories().split('\n'):
				if line.strip():
					break
			else:
				raise ConfigurationError()
		except ConfigurationError:
			msg = _("There is no repository at this server (or at least none for the current UCS version)")
			MODULE.warn("   !! Updater error: %s" % msg)
			response = {'message' : msg, 'status' : constants.PUT_UPDATER_ERROR}
			# if nothing was committed, we want a different type of error code,
			# just to appropriately inform the user
			if changed:
				response['status'] = constants.PUT_UPDATER_NOREPOS
			return [response]
		except:
			info = sys.exc_info()
			emsg = '%s: %s' % info[:2]
			MODULE.warn("   !! Updater error [%s]: %s" % (emsg))
			return [{'message' : str(info[1]), 'status' : constants.PUT_UPDATER_ERROR}]
		return [{'status' : constants.PUT_SUCCESS}]

