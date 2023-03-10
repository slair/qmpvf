#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import logging

from mod_qmpvf import qmpvf_main

_DEBUG = True

opj = os.path.join

WIN32 = sys.platform == "win32"
LINUX = sys.platform == "linux"
tmpdir = tempfile.gettempdir()


def usp():
	print("Неизвестная платформа - '%s'" % sys.platform)
	sys.exit(-10)


#~ from transliterate import translit, get_available_language_codes
#~ get_available_language_codes()	# без этого заменяются языки
#~ import translit_pikabu_lp		# добавляем свой язык
#~ print(get_available_language_codes())

my_file_name = os.path.abspath(__file__)
if os.path.islink(my_file_name):
	my_file_name = os.readlink(my_file_name)
my_folder = os.path.dirname(my_file_name)
my_name = os.path.splitext(os.path.basename(my_file_name))[0]


log_file_name = opj(tmpdir, my_name + ".log")
print("log_file_name = %r" % log_file_name)

BASELOGFORMAT = "%(asctime)s%(levelname)9s %(funcName)s: %(message)s"
FLN = ""
BASEDTFORMAT = "%d.%m.%y %H:%M:%S"

try:
	if _DEBUG:
		#~ FLN = "\t" * 30 + '|	File "%(pathname)s", line %(lineno)d'
		FLN = "%(filename)s:%(lineno)d: "
		loglevel = logging.DEBUG
	else:
		loglevel = logging.INFO
except NameError:
	_DEBUG = False
	loglevel = logging.INFO

logger = logging.getLogger(my_name)
console_output_handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter(FLN + BASELOGFORMAT, BASEDTFORMAT)
console_output_handler.setFormatter(formatter)
logger.addHandler(console_output_handler)

fh = logging.FileHandler(log_file_name, encoding="utf-8")
formatter = logging.Formatter(FLN + BASELOGFORMAT, BASEDTFORMAT)
fh.setFormatter(formatter)
logger.addHandler(fh)

#~ logger.setLevel(logging.INFO)
logger.setLevel(logging.DEBUG)

logd = logger.debug
logi = logger.info
logw = logger.warning
loge = logger.error
logc = logger.critical


def logt(logf, text, frames=True, title="", skip_empty=True, sep="\n"):
	try:
		logf
	except NameError:
		logf = print
	mf = "%s"
	data = text.split(sep)
	if frames:
		maxlen = max(map(len, data))
		#~ for item in data:
			#~ if maxlen<len(item):
				#~ maxlen=len(item)
		if len(title) > 0:
			if len(title) > maxlen:
				logf("┌─ " + title[:len(title) - (maxlen + 5)] + " "
					+ "─" * (maxlen - len(title) - 1) + "┐")
			else:
				logf("┌─ " + title + " " + "─" * (maxlen - len(title) - 1)
					+ "┐")
		else:
			logf("┌" + "─" * (maxlen + 2) + "┐")
	for item in data:
		if item.strip() == "" and skip_empty:
			continue
		if frames:
			mf = "│ %" + "-%ss │" % (maxlen)
		logf(mf % item)
	if frames:
		logf("└" + "─" * (maxlen + 2) + "┘")


def my_excepthookt(excType, excValue, tb):
	logc("Logging an uncaught exception", exc_info=(excType, excValue, tb))
	QUIT(200)


sys.excepthook = my_excepthookt

logi("Starting")

pid_file_name = opj(tmpdir, my_name + ".pid")
logi("pid_file_name = %r", pid_file_name)

my_pid = os.getpid()
logi("my_pid = %d", my_pid)

if os.path.exists(pid_file_name):
	need_exit = False

	pf = open(pid_file_name, "r")
	try:
		data = pf.readlines()
	except PermissionError:
		data = None
	pf.close()

	if data:
		logd("data = %r", data)
	else:
		need_exit = True

	try:
		os.unlink(pid_file_name)
		logd("Deleted %r", pid_file_name)
		need_exit = False
	except PermissionError:
		logd("Can't delete %r", pid_file_name)
		need_exit = True

	if need_exit:
		logi("Already running! pid=%r", int(data[0]))
		if WIN32:
			logi("Use command: taskkill /pid %r", int(data[0]))
		if LINUX:
			logi("Use command: kill  %r", int(data[0]))
		logi("Exiting")
		sys.exit(22)


pf = open(pid_file_name, "w")
pf.write("%d" % my_pid)
pf.flush()
os.fsync(pf.fileno())


def QUIT(exitcode=0):

	logi("Exiting")
	logging.shutdown()

	pf.flush()
	os.fsync(pf.fileno())
	# Release the lock on the file.
	#~ unlock_file(pf)
	pf.close()
	os.unlink(pid_file_name)
	sys.exit(exitcode)


def main():
	logd("- main()")
	for var, value in globals().items():
		logd("%16s = %s", var, value)

	order = None
	if len(sys.argv) > 1:
		if sys.argv[1] == "-name":
			order = "name"

	qmpvf_main(order)

	QUIT()


if __name__ == '__main__':
	main()
