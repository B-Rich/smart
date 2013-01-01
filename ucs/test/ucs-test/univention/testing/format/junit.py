# vim: set fileencoding=utf-8 ft=python sw=4 ts=4 et :
"""Format UCS Test results as JUnit report."""
import sys
from univention.testing.data import TestFormatInterface
from univention.testing.codes import TestCodes
from xml.sax.saxutils import XMLGenerator
from codecs import encode
from datetime import datetime
import os
import errno

__all__ = ['Junit']


class Junit(TestFormatInterface):
	"""
	Create Junit report.
	<http://windyroad.org/dl/Open%20Source/JUnit.xsd>
	"""
	def __init__(self, stream=sys.stdout):
		super(Junit, self).__init__(stream)
		self.outdir = "test-reports"
		self.now = datetime.today()

	def begin_test(self, case, prefix=''):
		"""Called before each test."""
		super(Junit, self).begin_test(case, prefix)
		self.now = datetime.today()

	def end_test(self, result):
		"""Called after each test."""
		failures = errors = skipped = disabled = 0
		if result.eofs == 'O':
			pass
		elif result.eofs == 'S':
			skipped = 1
		elif result.eofs == 'F':
			failures = 1
		elif result.eofs == 'E':
			errors = 1
		else:
			errors = 1

		filename = os.path.join(self.outdir, '%s.xml' % (result.case.uid,))
		dirname = os.path.dirname(filename)
		try:
			os.makedirs(dirname)
		except OSError, ex:
			if ex.errno != errno.EEXIST:
				raise
		f_report = open(filename, 'w')
		try:
			xml = XMLGenerator(f_report, encoding='utf-8')
			xml.startDocument()
			xml.startElement('testsuite', {
				'name': encode(result.case.description or result.case.uid),
				'tests': '%d' % (1,),
				'failures': '%d' % (failures,),
				'errors': '%d' % (errors,),
				'time': '%0.3f' % (result.duration / 1000.0,),
				'disabled': '%d' % (disabled,),
				'skipped': '%d' % (skipped,),
				'timestamp': self.now.isoformat(),
				'hostname': os.uname()[1],
				'id': result.case.uid,
				'package': self.section,
				})

			xml.startElement('properties', {})
			xml.startElement('property', {
				'name': 'hostname',
				'value': result.environment.hostname,
				})
			xml.endElement('property')
			xml.startElement('property', {
				'name': 'architecture',
				'value': result.environment.architecture,
				})
			xml.endElement('property')
			xml.startElement('property', {
				'name': 'role',
				'value': result.environment.role,
				})
			xml.endElement('property')
			xml.startElement('property', {
				'name': 'version',
				'value': '%s' % (result.environment.ucs_version,),
				})
			xml.endElement('property')
			xml.endElement('properties')

			xml.startElement('testcase', {
				'name': encode(result.case.description or result.case.uid),
				#'assertions': '%d' % (0,),
				'time': '%0.3f' % (result.duration / 1000.0,),
				'classname': result.case.uid,
				#'status': '???',
				})

			if skipped:
				xml.startElement('skipped', {})
				try:
					mime, content = result.artifacts['check']
				except KeyError:
					pass
				else:
					msg = '\n'.join(['%s' % (c,) for c in content])
					xml.characters(msg)
				xml.endElement('skipped')
			elif errors:
				xml.startElement('error', {
					'type': 'TestError',
					'message': '%s' % (result.result,),
					})
				xml.endElement('error')
			elif failures:
				msg = TestCodes.MESSAGE.get(result.reason, '')
				xml.startElement('failure', {
					'type': 'TestFailure',
					'message': msg,
					})
				xml.endElement('failure')

			try:
				mime, content = result.artifacts['stdout']
			except KeyError:
				pass
			else:
				xml.startElement('system-out', {})
				xml.characters(content)
				xml.endElement('system-out')

			try:
				mime, content = result.artifacts['stderr']
			except KeyError:
				pass
			else:
				xml.startElement('system-err', {})
				xml.characters(content)
				xml.endElement('system-err')

			xml.endElement('testcase')
			xml.endElement('testsuite')
			xml.endDocument()
		finally:
			f_report.close()
		super(Junit, self).end_test(result)

	def format(self, result):
		"""
		>>> from univention.testing.data import TestCase, TestEnvironment, \
				TestResult
		>>> te = TestEnvironment()
		>>> tc = TestCase()
		>>> tc.uid = 'python/data.py'
		>>> tr = TestResult(tc, te)
		>>> tr.success()
		>>> Junit().format(tr)
		"""
		self.begin_run(result.environment)
		self.begin_section('')
		self.begin_test(result.case)
		self.end_test(result)
		self.end_section()
		self.end_run()

if __name__ == '__main__':
	import doctest
	doctest.testmod()
