# -*- coding: utf-8 -*-

try:
	import univention.ucslint.base as uub
except ImportError:
	import ucslint.base as uub
import re
import subprocess


class UniventionPackageCheck(uub.UniventionPackageCheckDebian):
	def __init__(self):
		super(UniventionPackageCheck, self).__init__()
		self.name = '0013-bashism'

	def getMsgIds(self):
		return { '0013-1': [ uub.RESULT_WARN,  'failed to open file' ],
				 '0013-2': [ uub.RESULT_ERROR, 'possible bashism found' ],
				 '0013-3': [ uub.RESULT_WARN,  'cannot parse output of "checkbashism"' ],
				 }

	def postinit(self, path):
		""" checks to be run before real check or to create precalculated data for several runs. Only called once! """
		pass

	def check(self, path):
		""" the real check """
		super(UniventionPackageCheck, self).check(path)

		reBashism = re.compile(r'^.*?\s+line\s+(\d+)\s+[(](.*?)[)][:]\n([^\n]+)$')

		for fn in uub.FilteredDirWalkGenerator( path,
												ignore_suffixes=['~','.py','.bak','.po'],
												reHashBang=re.compile('^#![ \t]*/bin/sh')):
			self.debug('Testing file %s' % fn)
			p = subprocess.Popen(['checkbashisms', fn], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			stdout, stderr = p.communicate()
			# 2 = file is no shell script or file is already bash script
			# 1 = bashism found
			# 0 = everything is posix compliant
			if p.returncode == 1:
				for item in stderr.split('possible bashism in '):
					item = item.strip()
					if not item:
						continue

					match = reBashism.search(item)
					if not match:
						self.addmsg('0013-3', 'cannot parse checkbashism output:\n"%s"' % item.replace('\n','\\n').replace('\r','\\r'), filename=fn)
						continue

					line = int(match.group(1))
					msg = match.group(2)
					code = match.group(3)

					self.addmsg('0013-2', 'possible bashism (%s):\n%s' % (msg, code), filename=fn, line=line)
