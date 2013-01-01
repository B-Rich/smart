# vim: set fileencoding=utf-8 ft=python sw=4 ts=4 et :
"""Test case, environment, result and related classes."""
# pylint: disable-msg=R0902,W0201,R0903,E1101,E0611
import sys
import os
from univention.config_registry import ConfigRegistry
import yaml
from univention.testing.codes import TestCodes
from univention.testing.utils import UCSVersion
from operator import and_, or_
from subprocess import call, Popen, PIPE
import apt
from time import time
import logging
import signal
import select
import errno
import re
try:  # >= Python 2.5
	from hashlib import md5
except ImportError:
	from md5 import new as md5


__all__ = ['TestEnvironment', 'TestCase', 'TestResult', 'TestFormatInterface']


# <http://stackoverflow.com/questions/1707890/>
ILLEGAL_XML_UNICHR = (
		(0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x84), (0x86, 0x9F),
		(0xD800, 0xDFFF), (0xFDD0, 0xFDDF), (0xFFFE, 0xFFFF),
		(0x1FFFE, 0x1FFFF), (0x2FFFE, 0x2FFFF), (0x3FFFE, 0x3FFFF),
		(0x4FFFE, 0x4FFFF), (0x5FFFE, 0x5FFFF), (0x6FFFE, 0x6FFFF),
		(0x7FFFE, 0x7FFFF), (0x8FFFE, 0x8FFFF), (0x9FFFE, 0x9FFFF),
		(0xAFFFE, 0xAFFFF), (0xBFFFE, 0xBFFFF), (0xCFFFE, 0xCFFFF),
		(0xDFFFE, 0xDFFFF), (0xEFFFE, 0xEFFFF), (0xFFFFE, 0xFFFFF),
		(0x10FFFE, 0x10FFFF),
		)
RE_ILLEGAL_XML = re.compile(u'[%s]' % u''.join((u'%s-%s' % \
		(unichr(low), unichr(high)) for (low, high) in ILLEGAL_XML_UNICHR
		if low < sys.maxunicode)))

class TestEnvironment(object):
	"""Test environment for running test cases.

	Handels system data, requirements checks, test output.
	"""

	logger = logging.getLogger('test.env')

	def __init__(self, interactive=True, logfile=None):
		self.exposure = 'safe'
		self.interactive = interactive

		self._load_host()
		self._load_ucr()
		self._load_join()
		self._load_apt()

		if interactive:
			self.tags_required = None
			self.tags_prohibited = None
		else:
			self.tags_required = set()
			self.tags_prohibited = set(('SKIP', 'WIP'))

		self.log = open(logfile or os.path.devnull, 'a')

	def _load_host(self):
		"""Load host system informations."""
		(_sysname, nodename, _release, _version, machine) = os.uname()
		self.hostname = nodename
		self.architecture = machine

	def _load_ucr(self):
		"""Load Univention Config Registry informations."""
		self.ucr = ConfigRegistry()
		self.ucr.load()
		self.role = self.ucr.get('server/role', '')
		TestEnvironment.logger.debug('Role=%r' % self.role)

		version = self.ucr.get('version/version').split('.', 1)
		major, minor = int(version[0]), int(version[1])
		patchlevel = int(self.ucr.get('version/patchlevel'))
		if (major, minor) < (3, 0):
			securitylevel = int(self.ucr.get('version/security-patchlevel', 0))
			self.ucs_version = UCSVersion((major, minor, patchlevel,
				securitylevel))
		else:
			erratalevel = int(self.ucr.get('version/erratalevel', 0))
			self.ucs_version = UCSVersion((major, minor, patchlevel,
				erratalevel))
		TestEnvironment.logger.debug('Version=%r' % self.ucs_version)

	def _load_join(self):
		"""Load join status."""
		devnull = open(os.path.devnull, 'w+')
		try:
			ret = call(('/usr/sbin/univention-check-join-status',),
					stdin=devnull, stdout=devnull, stderr=devnull)
			self.joined = ret == 0
		finally:
			devnull.close()
		TestEnvironment.logger.debug('Join=%r' % self.joined)

	def _load_apt(self):
		"""Load package informations."""
		self.apt = apt.Cache()

	def dump(self, stream=sys.stdout):
		"""Dump environment informations."""
		print >> stream, 'hostname: %s' % (self.hostname,)
		print >> stream, 'architecture: %s' % (self.architecture,)
		print >> stream, 'version: %s' % (self.ucs_version,)
		print >> stream, 'role: %s' % (self.role,)
		print >> stream, 'joined: %s' % (self.joined,)
		print >> stream, 'tags_required: %s' % \
				(' '.join(self.tags_required) or '-',)
		print >> stream, 'tags_prohibited: %s' % \
				(' '.join(self.tags_prohibited) or '-',)

	def tag(self, require=set(), ignore=set(), prohibit=set()):
		"""Update required, ignored, prohibited tags."""
		if self.tags_required is not None:
			self.tags_required -= set(ignore)
			self.tags_required |= set(require)
		if self.tags_prohibited is not None:
			self.tags_prohibited -= set(ignore)
			self.tags_prohibited |= set(prohibit)
		TestEnvironment.logger.debug('tags_required=%r tags_prohibited=%r' % \
				(self.tags_required, self.tags_prohibited))

	def set_exposure(self, exposure):
		"""Set maximum allowed exposure level."""
		self.exposure = exposure


class _TestReader(object):  # pylint: disable-msg=R0903
	"""
	Read test case header lines starting with ##.
	"""

	def __init__(self, stream, digest):
		self.stream = stream
		self.digest = digest

	def read(self, size=-1):
		"""Read next line prefixed by '## '."""
		while True:
			line = self.stream.readline(size)
			if not line:
				return ''  # EOF
			if line.startswith('## '):
				return line[3:]
			while line:
				self.digest.update(line)
				line = self.stream.readline(size)


class Verdict(object):
	"""
	Result of a test, either successful or failed.
	"""

	INFO = 0     # Successful check, continue
	WARNING = 1  # Non-critical condition, may continue
	ERROR = 2    # Critical contion, abort

	logger = logging.getLogger('test.cond')

	def __init__(self, level, message, reason=None):
		self.level = level
		self.message = message
		self.reason = reason
		Verdict.logger.debug(self)

	def __nonzero__(self):
		return self.level < Verdict.ERROR

	def __str__(self):
		return '%s: %s' % ('IWE'[self.level], self.message)

	def __repr__(self):
		return '%s(level=%r, message=%r)' % (self.__class__.__name__,
				self.level, self.message)


class Check(object):
	"""
	Abstract check.
	"""

	def check(self, environment):
		"""Check if precondition to run test is met."""
		raise NotImplementedError()


class CheckExecutable(Check):
	"""
	Check language.
	"""

	def __init__(self, filename):
		super(CheckExecutable, self).__init__()
		self.filename = filename

	def check(self, _environment):
		"""Check environment for required executable."""
		if not os.path.isabs(self.filename):
			if self.filename.startswith('python'):
				self.filename = '/usr/bin/' + self.filename
			elif self.filename.endswith('sh'):
				self.filename = '/bin/' + self.filename
			else:
				yield Verdict(Verdict.ERROR, 'Unknown executable: %s' % \
						(self.filename,), TestCodes.REASON_INSTALL)
				return
		if os.path.isfile(self.filename):
			yield Verdict(Verdict.INFO, 'Executable: %s' % (self.filename,))
		else:
			yield Verdict(Verdict.ERROR, 'Missing executable: %s' % \
					(self.filename,), TestCodes.REASON_INSTALL)

	def __str__(self):
		return self.filename


class CheckVersion(Check):
	"""
	Check expected result of test for version.
	"""

	STATES = frozenset(('found', 'fixed', 'skip', 'run'))

	def __init__(self, versions):
		super(CheckVersion, self).__init__()
		self.versions = versions
		self.state = 'run'

	def check(self, environment):
		"""Check environment for expected version."""
		versions = []
		for version, state in self.versions.items():
			ucs_version = UCSVersion(version)
			if state not in CheckVersion.STATES:
				yield Verdict(Verdict.WARNING,
						'Unknown state "%s" for version "%s"' % \
						(state, version))
				continue
			versions.append((ucs_version, state))
		versions.sort()
		for (ucs_version, state) in versions:
			if ucs_version <= environment.ucs_version:
				self.state = state
		if self.state == 'skip':
			yield Verdict(Verdict.ERROR, 'Skipped for version %s' % \
					(environment.ucs_version,),
					TestCodes.REASON_VERSION_MISMATCH)


class CheckTags(Check):
	"""
	Check for required / prohibited tags.
	"""

	def __init__(self, tags):
		super(CheckTags, self).__init__()
		self.tags = set(tags)

	def check(self, environment):
		"""Check environment for required / prohibited tags."""
		if environment.tags_required is None or \
				environment.tags_prohibited is None:
			yield Verdict(Verdict.INFO, 'Tags disabled')
			return
		prohibited = self.tags & environment.tags_prohibited
		if prohibited:
			yield Verdict(Verdict.ERROR, 'De-selected by tag: %s' % \
					(' '.join(prohibited),), TestCodes.REASON_ROLE_MISMATCH)
		elif environment.tags_required:
			required = self.tags & environment.tags_required
			if required:
				yield Verdict(Verdict.INFO, 'Selected by tag: %s' % \
						(' '.join(required),))
			else:
				yield Verdict(Verdict.ERROR, 'De-selected by tag: %s' % \
						(' '.join(environment.tags_required),),
						TestCodes.REASON_ROLE_MISMATCH)


class CheckRoles(Check):
	"""
	Check server role.
	"""

	ROLES = frozenset((
		'domaincontroller_master',
		'domaincontroller_backup',
		'domaincontroller_slave',
		'memberserver',
		'basesystem',
		'mobileclient',
		'fatclient',
		'managedclient',
		'thinclient',
		))

	def __init__(self, roles_required=(), roles_prohibited=()):
		super(CheckRoles, self).__init__()
		self.roles_required = set(roles_required)
		self.roles_prohibited = set(roles_prohibited)

	def check(self, environment):
		"""Check environment for required / prohibited server role."""
		overlap = self.roles_required & self.roles_prohibited
		if overlap:
			yield Verdict(Verdict.WARNING, 'Overlapping roles: %s' % \
					(' '.join(overlap),))
			roles = self.roles_required - self.roles_prohibited
		elif self.roles_required:
			roles = set(self.roles_required)
		else:
			roles = CheckRoles.ROLES - set(self.roles_prohibited)

		unknown_roles = roles - CheckRoles.ROLES
		if unknown_roles:
			yield Verdict(Verdict.WARNING, 'Unknown roles: %s' % \
					(' '.join(unknown_roles),))

		if environment.role not in roles:
			yield Verdict(Verdict.ERROR, 'Wrong role: %s not in (%s)' % \
					(environment.role, ','.join(roles)),
					TestCodes.REASON_ROLE_MISMATCH)


class CheckJoin(Check):
	"""
	Check join status.
	"""

	def __init__(self, joined):
		super(CheckJoin, self).__init__()
		self.joined = joined

	def check(self, environment):
		"""Check environment for join status."""
		if self.joined is None:
			yield Verdict(Verdict.INFO, 'No required join status')
		elif self.joined and not environment.joined:
			yield Verdict(Verdict.ERROR, 'Test requires system to be joined',
					TestCodes.REASON_JOIN)
		elif not self.joined and environment.joined:
			yield Verdict(Verdict.ERROR,
					'Test requires system to be not joined',
					TestCodes.REASON_JOINED)
		else:
			yield Verdict(Verdict.INFO, 'Joined: %s' % (environment.joined,))


class CheckComponents(Check):
	"""
	Check for required / prohibited components.
	"""

	def __init__(self, components):
		super(CheckComponents, self).__init__()
		self.components = components

	def check(self, environment):
		"""Check environment for required / prohibited components."""
		for component, required in self.components.items():
			key = 'repository/online/component/%s' % (component,)
			active = environment.ucr.is_true(key, False)
			if required:
				if active:
					yield Verdict(Verdict.INFO,
							'Required component %s active' % (component,))
				else:
					yield Verdict(Verdict.ERROR,
							'Required component %s missing' % \
							(component,), TestCodes.REASON_INSTALL)
			else:  # not required
				if active:
					yield Verdict(Verdict.ERROR,
							'Prohibited component %s active' % \
							(component,), TestCodes.REASON_INSTALLED)
				else:
					yield Verdict(Verdict.INFO,
							'Prohibited component %s not active' % \
							(component,))


class CheckPackages(Check):
	"""
	Check for required packages.
	"""

	def __init__(self, packages):
		super(CheckPackages, self).__init__()
		self.packages = packages

	def check(self, environment):
		"""Check environment for required / prohibited packages."""
		def check_disjunction(conjunction):
			"""Check is any of the alternative packages is installed."""
			for name, dep_version, dep_op in conjunction:
				try:
					pkg = environment.apt[name]
				except KeyError:
					yield Verdict(Verdict.ERROR,
							'Package %s not found' % (name,),
							TestCodes.REASON_INSTALL)
					continue
				ver = pkg.installed
				if ver is None:
					yield Verdict(Verdict.ERROR,
							'Package %s not installed' % (name,),
							TestCodes.REASON_INSTALL)
					continue
				if dep_version and not \
						apt.apt_pkg.CheckDep(ver.version, dep_op, dep_version):
					yield Verdict(Verdict.ERROR,
							'Package %s version mismatch' % (name,),
							TestCodes.REASON_INSTALL)
					continue
				yield Verdict(Verdict.INFO, 'Package %s installed' % (name,))
				break

		for dependency in self.packages:
			deps = apt.apt_pkg.ParseDepends(dependency)
			for conjunction in deps:
				conditions = list(check_disjunction(conjunction))
				success = reduce(or_, (bool(_) for _ in conditions), False)
				if success:
					for condition in conditions:
						if condition.level < Verdict.ERROR:
							yield condition
				else:
					for condition in conditions:
						yield condition


class CheckExposure(Check):
	"""
	Check for signed exposure.
	"""

	STATES = ['safe', 'careful', 'dangerous']

	def __init__(self, exposure, digest):
		super(CheckExposure, self).__init__()
		self.exposure = exposure
		self.digest = digest

	def check(self, environment):
		"""Check environment for permitted exposure level."""
		exposure = 'DANGEROUS'
		try:
			exposure, expected_md5 = self.exposure.split(None, 1)
		except ValueError:
			exposure = self.exposure
		else:
			current_md5 = self.digest.hexdigest()
			if current_md5 != expected_md5:
				yield Verdict(Verdict.ERROR,
						'MD5 mismatch: %s' % (current_md5,))
			else:
				yield Verdict(Verdict.INFO, 'MD5 matched: %s' % (current_md5,))
		if exposure not in CheckExposure.STATES:
			yield Verdict(Verdict.WARNING,
					'Unknown exposure: %s' % (exposure,))
			return
		if CheckExposure.STATES.index(exposure) > \
				CheckExposure.STATES.index(environment.exposure):
			yield Verdict(Verdict.ERROR, 'Too dangerous: %s > %s' % \
					(exposure, environment.exposure), TestCodes.REASON_DANGER)
		else:
			yield Verdict(Verdict.INFO, 'Safe enough: %s <= %s' % \
					(exposure, environment.exposure))


class TestCase(object):
	"""Test case."""

	logger = logging.getLogger('test.case')

	def __init__(self):
		self.exe = None
		self.args = []
		self.filename = None
		self.uid = None
		self.description = None
		self.bugs = set()
		self.otrs = set()

	def load(self, filename):
		"""
		Load test case from stream.
		"""
		TestCase.logger.info('Loading test %s' % (filename,))
		digest = md5()
		tc_file = open(filename, 'r')
		try:
			firstline = tc_file.readline()
			if not firstline.startswith('#!'):
				raise ValueError('Missing hash-bang')
			args = firstline.split(None)
			try:
				lang = args[1]
			except IndexError:
				lang = ''
			self.exe = CheckExecutable(lang)
			self.args = args[2:]

			digest.update(firstline)
			reader = _TestReader(tc_file, digest)
			header = yaml.load(reader) or {}
		finally:
			tc_file.close()

		self.filename = os.path.abspath(filename)
		self.uid = os.path.sep.join(self.filename.rsplit(os.path.sep, 2)[-2:])

		self.description = header.get('desc', '').strip()
		self.bugs = set(header.get('bugs', []))
		self.otrs = set(header.get('otrs', []))
		self.versions = CheckVersion(header.get('versions', {}))
		self.tags = CheckTags(header.get('tags', []))
		self.roles = CheckRoles(header.get('roles', []),
				header.get('roles-not', []))
		self.join = CheckJoin(header.get('join', None))
		self.components = CheckComponents(header.get('components', {}))
		self.packages = CheckPackages(header.get('packages', []))
		self.exposure = CheckExposure(header.get('exposure', 'dangerous'),
				digest)

		return self

	def check(self, environment):
		"""
		Check if the test case should run.
		"""
		TestCase.logger.info('Checking test %s' % (self.filename,))
		conditions = []
		conditions += list(self.exe.check(environment))
		conditions += list(self.versions.check(environment))
		conditions += list(self.tags.check(environment))
		conditions += list(self.roles.check(environment))
		conditions += list(self.components.check(environment))
		conditions += list(self.packages.check(environment))
		conditions += list(self.exposure.check(environment))
		return conditions

	@staticmethod
	def _run_tee(proc, result, stdout=sys.stdout, stderr=sys.stderr):
		"""Run test collecting and passing through stdout, stderr:"""
		log_stdout, log_stderr = [], []
		fd_stdout = proc.stdout.fileno()
		fd_stderr = proc.stderr.fileno()
		read_set = [fd_stdout, fd_stderr]
		while read_set:
			try:
				rlist, _wlist, _elist = select.select(read_set, [], [])
			except select.error, ex:
				if ex.args[0] == errno.EINTR:
					continue
				raise
			if fd_stdout in rlist:
				data = os.read(fd_stdout, 1024)
				if data == '':
					read_set.remove(fd_stdout)
					proc.stdout.close()
				else:
					stdout.write(data)
					log_stdout.append(data)
			if fd_stderr in rlist:
				data = os.read(fd_stderr, 1024)
				if data == '':
					read_set.remove(fd_stderr)
					proc.stderr.close()
				else:
					stderr.write(data)
					log_stderr.append(data)

		if log_stdout:
			TestCase._attach(result, 'stdout', log_stdout)
		if log_stderr:
			TestCase._attach(result, 'stderr', log_stderr)

	@staticmethod
	def _attach(result, part, content):
		"""Attach content."""
		text = ''.join(content)
		try:
			dirty = text.decode(sys.getfilesystemencoding())
			clean = RE_ILLEGAL_XML.sub(u'\uFFFD', dirty)
		except UnicodeError:
			clean = text.encode('hex')
		result.attach(part, 'text/plain', clean)

	def _translate_result(self, result):
		"""Translate exit code into result."""
		if result.result == TestCodes.RESULT_OKAY:
			result.reason = {
					'fixed': TestCodes.REASON_FIXED_EXPECTED,
					'found': TestCodes.REASON_FIXED_UNEXPECTED,
					'run': TestCodes.REASON_OKAY,
					}.get(self.versions.state, result.result)
		elif result.result == TestCodes.RESULT_SKIP:
			result.reason = TestCodes.REASON_SKIP
		else:
			if result.result in TestCodes.MESSAGE:
				result.reason = result.result
			else:
				result.reason = {
						'fixed': TestCodes.REASON_FAIL_UNEXPECTED,
						'found': TestCodes.REASON_FAIL_EXPECTED,
						'run': TestCodes.REASON_FAIL,
						}.get(self.versions.state, result.result)
		result.eofs = TestCodes.EOFS.get(result.reason, 'E')

	def run(self, result):
		"""Run the test case and fill in result."""
		base = os.path.basename(self.filename)
		dirname = os.path.dirname(self.filename)
		cmd = [self.exe.filename, base] + self.args

		time_start = time()

		# Protect wrapper from Ctrl-C as long as test case is running
		def handle_int(_signal, _frame):
			"""Handle Ctrl-C signal."""
			result.result = TestCodes.RESULT_SKIP
			result.reason = TestCodes.REASON_ABORT
		old_sig_int = signal.signal(signal.SIGINT, handle_int)

		def prepare_child():
			"""Setup child process."""
			signal.signal(signal.SIGINT, signal.SIG_IGN)

		try:
			TestCase.logger.debug('Running %r using %s in %s' % \
					(cmd, self.exe, dirname))
			try:
				print >> result.environment.log, \
						'*** BEGIN *** %r ***' % (cmd,)
				result.environment.log.flush()
				if result.environment.interactive:
					proc = Popen(cmd, executable=self.exe.filename,
							shell=False, stdout=PIPE, stderr=PIPE,
							close_fds=True, cwd=dirname)
					to_stdout, to_stderr = sys.stdout, sys.stderr
				else:
					devnull = open(os.path.devnull, 'r')
					try:
						proc = Popen(cmd, executable=self.exe.filename,
								shell=False, stdin=devnull,
								stdout=PIPE, stderr=PIPE, close_fds=True,
								cwd=dirname, preexec_fn=prepare_child)
					finally:
						devnull.close()
					to_stdout = to_stderr = result.environment.log

				TestCase._run_tee(proc, result, to_stdout, to_stderr)

				result.result = proc.wait()
				print >> result.environment.log, '*** END *** %d ***' % \
						(result.result,)
				result.environment.log.flush()
			except OSError:
				TestCase.logger.error('Failed to execute %r using %s in %s' % \
						(cmd, self.exe, dirname))
				raise
		finally:
			signal.signal(signal.SIGINT, old_sig_int)
			if result.reason == TestCodes.REASON_ABORT:
				raise KeyboardInterrupt()  # pylint: disable-msg=W1010

		time_end = time()

		result.duration = int(time_end * 1000.0 - time_start * 1000.0)
		TestCase.logger.info('Test %r using %s in %s returned %s in %s ms' % \
				(cmd, self.exe, dirname, result.result, result.duration))

		self._translate_result(result)


class TestResult(object):
	"""Test result from running a test case."""

	def __init__(self, case, environment=None):
		self.case = case
		self.environment = environment
		self.result = -1
		self.reason = None
		self.duration = 0
		self.artifacts = {}
		self.condition = None
		self.eofs = None

	def dump(self, stream=sys.stdout):
		"""Dump test result data."""
		print >> stream, 'Case: %s' % (self.case.uid,)
		print >> stream, 'Environment: %s' % (self.environment.hostname,)
		print >> stream, 'Result: %d %s' % (self.result, self.eofs)
		print >> stream, 'Reason: %s (%s)' % (self.reason,
				TestCodes.MESSAGE.get(self.reason, ''))
		print >> stream, 'Duration: %d' % (self.duration or 0,)
		for (key, (mime, content)) in self.artifacts.items():
			print 'Artifact[%s]: %s %r' % (key, mime, content)

	def attach(self, key, mime, content):
		"""Attach artifact 'content' of mime-type 'mime'."""
		self.artifacts[key] = (mime, content)

	def success(self, reason=TestCodes.REASON_OKAY):
		"""Mark result as successful."""
		self.result = TestCodes.RESULT_OKAY
		self.reason = reason
		self.eofs = 'O'

	def fail(self, reason=TestCodes.REASON_FAIL):
		"""Mark result as failed."""
		self.result = TestCodes.RESULT_FAIL
		self.reason = reason
		self.eofs = 'F'

	def skip(self, reason=TestCodes.REASON_INTERNAL):
		"""Mark result as skipped."""
		self.result = TestCodes.RESULT_SKIP
		self.reason = self.reason or reason
		self.eofs = 'S'

	def check(self):
		"""Test conditions to run test."""
		conditions = self.case.check(self.environment)
		self.attach('check', 'python', conditions)
		self.condition = reduce(and_, (bool(_) for _ in conditions), True)
		reasons = [c.reason for c in conditions if c.reason is not None]
		if reasons:
			self.reason = reasons[0]
		else:
			self.reason = None
		return self.condition

	def run(self):
		"""Return test."""
		if self.condition is None:
			self.check()
		if self.condition:
			self.case.run(self)
		else:
			self.skip()
		return self


class TestFormatInterface(object):  # pylint: disable-msg=R0921
	"""Format UCS Test result."""

	def __init__(self, stream=sys.stdout):
		self.stream = stream
		self.environment = None
		self.count = None
		self.section = None
		self.case = None
		self.prefix = None

	def begin_run(self, environment, count=1):
		"""Called before first test."""
		self.environment = environment
		self.count = count

	def begin_section(self, section):
		"""Called before each secion."""
		self.section = section

	def begin_test(self, case, prefix=''):
		"""Called before each test."""
		self.case = case
		self.prefix = prefix

	def end_test(self, result):
		"""Called after each test."""
		self.case = None
		self.prefix = None

	def end_section(self):
		"""Called after each secion."""
		self.section = None

	def end_run(self):
		"""Called after all test."""
		self.environment = None
		self.count = None

	def format(self, result):
		"""Format single test."""
		raise NotImplementedError()


def __run_test(filename):
	"""Run local test."""
	test_env = TestEnvironment()
	#test_env.dump()
	test_case = TestCase().load(filename)
#	try:
#		test_case.check(te)
#	except TestConditionError, ex:
#		for msg in ex:
#			print msg
	test_result = TestResult(test_case, test_env)
	test_result.dump()


if __name__ == '__main__':
	import doctest
	doctest.testmod()
	__run_test('tst3')
