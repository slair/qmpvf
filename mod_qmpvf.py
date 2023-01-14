#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import tempfile
import logging
import glob
import re
import string
import subprocess
from threading import Thread

from psutil import process_iter
from ahk import AHK
from ahk.window import Window

# pylint: disable=E0611
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QListWidgetItem
#~ from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer
from PyQt5 import uic
# pylint: disable=

from saymod import snd_play_async

WIN32 = sys.platform == "win32"
LINUX = sys.platform == "linux"

opj = os.path.join
tpc = time.perf_counter
tmpdir = tempfile.gettempdir()

my_file_name = os.path.abspath(__file__)
if os.path.islink(my_file_name):
	my_file_name = os.readlink(my_file_name)
my_folder = os.path.dirname(my_file_name)
my_name = os.path.splitext(os.path.basename(my_file_name))[0]

logger = logging.getLogger("qmpvf")
logd = logger.debug
logi = logger.info
logw = logger.warning
loge = logger.error
logc = logger.critical

try:
	import mod_qmpvf_res
except ModuleNotFoundError:
	fp_res = opj(my_folder, "mod_qmpvf.qrc")
	fp_res_py = opj(my_folder, "mod_qmpvf_res.py")
	make_res_cmd = 'pyrcc5 "%s" -o "%s"' % (fp_res, fp_res_py)
	logd("generating %r from %r" % (fp_res_py, fp_res))
	os.system(make_res_cmd)

try:
	import mod_qmpvf_res		# noqa
except ModuleNotFoundError:
	logd("generating %r from %r failed" % (fp_res_py, fp_res))

from transliterate import translit	# noqa
# , get_available_language_codes

MAX_QUEUE_LEN = 16
SEC_TO_EXIT = 10				# seconds
TIMER_INTERVAL = 1000			# milliseconds
WAIT_FOR_PLAYER_START = 5		# seconds
WAIT_BEFORE_RENAME = 3			# seconds
WAIT_AFTER_RENAME = 2			# seconds
PARTSEP = "=#="
PL_EXE = "mpv.exe"
txtPause = "Пауза"
txtPlay = "Продолжить"
txtName = "По имени"
txtSize = "По размеру"

audio_filer = "--af=lavfi=[loudnorm=I=-16:TP=-1:LRA=2] "
audio_filer = ""

PLAYCMD = 'c:\\windows\\system32\\cmd.exe /c start C:\\apps\\mpv\\' \
	+ PL_EXE + ' -fs --fs-screen=0' \
	+ ' --softvol-max=500 --brightness=10 ' \
	+ audio_filer \
	+ '-- "%s"'
	# --aid=1


ahk = AHK()


def asnc(func):
	def wrapper(*args, **kwargs):
		thr = Thread(target=func, args=args, kwargs=kwargs)
		thr.start()
	return wrapper


@asnc
def do_command(cmd):
	subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE
		, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def get_procs_count(exe_fn):
	pc = 0
	for p in process_iter(['name']):
		if p.info['name'] == exe_fn:
			pc += 1
	return pc


def get_player_pid(exe_fn):
	#~ pc = 0
	for p in process_iter(['name']):
		if p.info['name'] == exe_fn:
			return p.pid
	return None


def mc(odin, dva, mnogo, num):
	# остаток
	mod = num % 10
	num = num % 100
	if (num > 10) and (num < 20):
		form = 3
	elif mod == 1:
		form = 1
	elif (mod > 1) and (mod < 5):
		form = 2
	else:
		form = 3
	if form == 1:
		return odin
	elif form == 2:
		return dva
	else:
		return mnogo


def strip_above_0xffff(s):
	r = ""
	for c in s:
		if ord(c) <= 0xffff:
			r += c
	return r


def strip_right_digits(s):
	r = s
	while len(r) and (str.isdigit(r[-1])):
		r = r[:-1]
	return r


def untranslit_word(w):
	#~ r = translit(w, "ru")
	r = translit(w, "pikabu.ru")
	return r


def untranslit(s):
	res = []
	words = s.split()
	for word in words:
		res.append(untranslit_word(word))
	res = " ".join(res)
	return res[0].upper() + res[1:]


def get_video_title(s):
	#~ s = strip_above_0xffff(s)

	if "Й" in s:
		s = s.replace("Й", "Й")
	if "й" in s:
		s = s.replace("й", "й")

	ls = s.lower()
	if ls.endswith(".mp4") or ls.endswith(".avi") or ls.endswith(".mov") \
		or ls.endswith(".mkv"):
		s = s[:-4]

	if " - " in s:
		s = s.replace(" - ", "\n")

	if " _ " in s:
		s = s.replace(" _ ", "\n")

	if "_" in s:
		s = s.replace("_", " ")

	#~ s = re.sub(r"\(\d\)", "", s)

	s = re.sub(" +", " ", s)

	if "." in s:
		s = s.replace(".", " ")

	s = s.strip()

	if s.count(PARTSEP) == 2:
		dt, title, _ = s.split(PARTSEP)

		title = re.sub(r'(?<=\d)[_](?=\d)', ":", title)

		return title

	elif s.count(PARTSEP) == 1:
		dt, title = s.split(PARTSEP)
		title = title[:title.rfind(".")]

		if title.split()[-1].isdigit():
			title = title[:title.rfind(" ")]

		return untranslit(title)

	else:
		return s


class MainWindow(QMainWindow):
	start_perf_counter = tpc()
	videos = []
	videos_dirty = True
	order_by = "size"
	start_next = True
	video_to_play = None
	player_pid = None
	ts_video_stopped = None
	ts_video_renamed = None
	tpc_no_videos = None
	sec_remains = SEC_TO_EXIT
	no_catch_PL_EXE = False
	win_player = None
	label_current_video_ss = None
	all_chars = string.ascii_lowercase + string.digits + "/*"
	rename_on_stop = True

	def __init__(self):
		super(MainWindow, self).__init__()

		self.load_ui()

		self.label_current_video_ss = self.label_current_video.styleSheet()
		logd("self.label_current_video_ss = %r"
			, self.label_current_video_ss)

		self.pb_1.setText(txtPause)
		self.pb_2.setText(txtName)
		self.pb_1.setEnabled(False)
		self.pb_kill_player.setVisible(False)
		self.get_videos()
		self.player_pid = get_player_pid(PL_EXE)
		self.start_video()

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.on_timeout)
		self.timer.start(TIMER_INTERVAL)
		logd("TIMER_INTERVAL=%r msec Passed %.6f sec"
			, TIMER_INTERVAL, tpc() - self.start_perf_counter)

	def keyPressEvent(self, event):
		logd("event.key()=%r", event.key())

		QWidget.keyPressEvent(self, event)

		if not event.isAccepted() and event.key() == Qt.Key_Escape:
			self.close()

		if not self.win_player or self.win_player.id == "":
			return

		if event.key() > 255:
			return

		_char = chr(event.key()).lower()
		if _char in self.all_chars:
			self.win_player.send(_char)
			logd("sent %r to %r", _char, self.win_player)

	def load_ui(self):
		logd("my_folder=%r", my_folder)
		path = opj(my_folder, "mod_qmpvf.ui")
		uic.loadUi(path, self)

	def activate(self):
		self.setFocus(True)
		self.setWindowState(Qt.WindowMaximized)
		self.activateWindow()
		self.raise_()
		self.showMaximized()
		self.pb_1.setFocus(True)

	def on_timeout(self):

		#~ logd("self.ts_video_stopped = %r", self.ts_video_stopped)
		#~ logd("self.ts_video_renamed = %r", self.ts_video_renamed)
		#~ logd("self.player_pid = %r", self.player_pid)
		#~ logd("self.win_player = %r", self.win_player)

		ts = tpc()

		now = time.strftime("%H:%M:%S")
		self.label_clock.setText(now)

		if get_procs_count(PL_EXE) == 0 and self.ts_video_stopped is None \
			and not (self.player_pid is None):

			self.player_pid = None
			self.win_player = None
			self.ts_video_stopped = tpc()
			logd("video stopped at %.6f", self.ts_video_stopped)
			self.activate()

		if self.player_pid is None:
			#~ logd("searching %r", PL_EXE)
			self.player_pid = get_player_pid(PL_EXE)

		if self.player_pid:
			if not self.no_catch_PL_EXE:

				if self.win_player is None or self.win_player.id == "":
					self.win_player = Window.from_pid(ahk
						, pid=str(self.player_pid))
					if self.win_player.id != "":
						logd("Found player_pid=%r win_player.id=%r"
							, self.player_pid, self.win_player.id)
					#~ else:
						#~ logd("Can't get win_player.id")

				if not self.pb_kill_player.isVisible():
					self.pb_kill_player.setText(
						"Закрыть\n%r" % self.player_pid)
					self.pb_1.setText(txtPause)

				if self.win_player and self.win_player.id != "":
					self.pb_1.setEnabled(True)
					self.pb_1.setFocus(True)
					self.pb_kill_player.setVisible(True)
		else:
			self.pb_1.setText(txtPause)
			self.pb_1.setEnabled(False)
			self.pb_kill_player.setVisible(False)

		if self.ts_video_stopped \
			and (tpc() - self.ts_video_stopped) > WAIT_BEFORE_RENAME:
			if self.rename_on_stop:
				self.rename_video()
			else:
				self.label_current_video.setText(" ")
				self.get_videos()
				self.rename_on_stop = True
				self.ts_video_stopped = None
				self.ts_video_renamed = tpc()

		if self.ts_video_renamed \
			and (tpc() - self.ts_video_renamed) > WAIT_AFTER_RENAME:
			self.start_video()

		if self.tpc_no_videos:
			self.no_catch_PL_EXE = True
			self.get_videos()
			self.label_video_remains.setText("Выход через %d "
				% self.sec_remains
				+ mc("секунду", "секунды", "секунд", self.sec_remains))
			self.sec_remains -= 1
			snd_play_async("C:\\slair\\share\\sounds\\click-6.ogg")

			if self.sec_remains <= -1:
				snd_play_async("C:\\slair\\share\\sounds\\drum.mp3")
				self.close()

		duration = tpc() - ts
		if duration > TIMER_INTERVAL:
			logd("on_timeout(%r): duration=%.6f", self, duration)

	def rename_video(self):
		if not self.start_next:
			return
		if self.video_to_play and os.path.exists(self.video_to_play):
			#~ new_item = self.video_to_play[:self.video_to_play.rfind(".")] \
				#~ + ".seen"
			new_item = self.video_to_play + ".seen"

			logd("renaming %r to %r" % (self.video_to_play, new_item))

			rename_status = "<переименовано>"
			try:
				os.rename(self.video_to_play, new_item)
			except PermissionError:
				rename_status = "<не удалось переименовать>"
			except FileExistsError:
				rename_status = "<не удалось переименовать>"

			self.label_current_video.setText(rename_status)
			self.label_current_video.setStyleSheet("color:#c01000;")

			video_name = self.video_to_play[:self.video_to_play.rfind(".")]

			if os.path.exists(video_name + ".srt"):
				try:
					os.rename(video_name + ".srt", video_name + ".srt.seen")
				except PermissionError:
					loge("renaming %r to %r failed", video_name + ".srt"
						, video_name + ".srt.seen")

			if os.path.exists(video_name + ".ru.vtt"):
				try:
					os.rename(video_name + ".ru.vtt", video_name
						+ ".ru.vtt.seen")
				except PermissionError:
					loge("renaming %r to %r failed", video_name + ".ru.vtt"
						, video_name + ".ru.vtt.seen")

			self.ts_video_stopped = None
			self.ts_video_renamed = tpc()

			self.get_videos()

	def sort_videos(self):
		if self.order_by == "size":
			self.videos.sort(key=lambda x: x[1])
			self.videos.reverse()
			logd("sort by size")
		else:
			self.videos.sort(key=lambda x: x[0].lower())
			logd("sort by name")
		logd(self.videos)

		self.videos_dirty = True
		#~ for item in self.videos:
			#~ logd(item)
		self.update_videos()

	def get_videos(self):
		_ = glob.glob("*.mp4")
		_ += glob.glob("*.mkv")
		_ += glob.glob("*.avi")
		_ += glob.glob("*.webm")
		_ += glob.glob("*.m4v")
		_ += glob.glob("*.mov")
		self.videos = []
		for fn in _:
			fsize = os.stat(fn).st_size
			if fsize == 0:
				try:
					os.unlink(fn)
				except PermissionError:
					self.videos.append((fn + " Пустой файл! Не могу удалить!"
						, fsize))
			else:
				self.videos.append((fn, fsize))
		logd("%r videos found", len(self.videos))
		self.sort_videos()
		if len(self.videos) > 0:
			self.sec_remains = SEC_TO_EXIT
			self.tpc_no_videos = None

	def update_videos(self):
		if not self.videos_dirty:
			return

		self.lw_videos.clear()
		self.lw_videos.setItemAlignment(Qt.AlignCenter)
		for i in range(min(MAX_QUEUE_LEN, len(self.videos))):
			new_lw_item = QListWidgetItem(get_video_title(self.videos[i][0])
				, self.lw_videos)
			new_lw_item.setTextAlignment(Qt.AlignCenter)

		self.videos_dirty = False

	def start_video(self):
		if len(self.videos) > 0 and self.start_next \
			and self.player_pid is None:

			self.video_to_play = self.videos.pop(0)[0]
			self.label_video_remains.setText(
				"Осталось %d видео" % (len(self.videos) + 1))
			self.videos_dirty = True
			self.label_current_video.setStyleSheet("")
			self.label_current_video.setText(
				get_video_title(self.video_to_play))

			logd("starting '%s'", PLAYCMD % self.video_to_play)
			self.no_catch_PL_EXE = False
			do_command(PLAYCMD % self.video_to_play)
			self.player_pid = get_player_pid(PL_EXE)

			_start_wait = time.perf_counter()
			while self.player_pid is None or get_procs_count(PL_EXE) == 0:
				#~ logd("WAIT_FOR_PLAYER_START")
				self.player_pid = get_player_pid(PL_EXE)
				if self.player_pid is not None:
					logd("player started self.player_pid = %r"
						, self.player_pid)
					break

				logd("time.perf_counter() - _start_wait = %r"
					, time.perf_counter() - _start_wait)

				if time.perf_counter() - _start_wait > WAIT_FOR_PLAYER_START:
					logw("player not started for %r seconds"
						, WAIT_FOR_PLAYER_START)
					self.player_pid = 0
					break

				time.sleep(0.2)

			logd("self.player_pid = %r, get_procs_count(PL_EXE) = %r"
				, self.player_pid, get_procs_count(PL_EXE))

			self.ts_video_stopped = None
			self.ts_video_renamed = None
			self.update_videos()

		elif len(self.videos) == 0 and self.player_pid is None:
			if self.tpc_no_videos is None:
				self.tpc_no_videos = tpc()
				self.label_current_video.setStyleSheet("color:#000000;")
				self.label_current_video.setText("Видео закончились")
				self.tpc_no_videos = tpc()

		else:
			self.label_video_remains.setText(
				"Осталось %d видео" % (len(self.videos)))
			#~ self.player_pid = get_player_pid(PL_EXE)
			self.label_current_video.setText("<что-то воспроизводится>")

	def kill_player(self):
		if not self.player_pid:
			return

		os.kill(self.player_pid, 9)

	def pb_1_clicked(self):
		if not self.win_player or self.win_player.id == "":
			return

		if self.pb_1.text() == txtPause:
			self.win_player.send("p")
			self.pb_1.setText(txtPlay)
			logd("sent 'p' to %r", self.win_player)
			return
		elif self.pb_1.text() == txtPlay:
			self.win_player.send("p")
			self.pb_1.setText(txtPause)
			logd("sent 'p' to %r", self.win_player)
			return

	def pb_2_clicked(self):
		self.rename_on_stop = False
		logd("self.order_by=%r", self.order_by)
		if self.order_by is None:
			self.order_by = "size"
			self.pb_2.setText(txtName)
			self.kill_player()
			return
		elif self.order_by == "size":
			self.order_by = None
			self.pb_2.setText(txtSize)
			self.kill_player()
			return

	def pb_3_clicked(self):
		...
		return


def qmpvf_main(*args, **kwargs):
	logd("- qmpvf_main(%s, %s)" % (args, kwargs))
	for var, value in globals().items():
		if var not in ("__builtins__"):
			logd("%16s = %s", var, value)

	app = QApplication([])
	widget = MainWindow()

	#~ if not RESOURCES:
	widget.showMaximized()

	exitcode = app.exec_()

	logi("app.exec_() = %r", exitcode)


def main():
	logd("- main()", __name__)
	for var, value in globals().items():
		logd("%16s = %s" % (var, value))
	qmpvf_main()


if __name__ == '__main__':
	main()
