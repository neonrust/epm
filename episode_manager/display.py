
import time
from datetime import date
from typing import Callable
import textwrap

from .config import debug
from .db import \
    meta_get, \
	meta_has, \
	meta_archived_key, \
	series_seen_unseen, \
	episode_key
from .utils import \
    strip_ansi, \
	now_datetime, \
	today_date, \
	plural
from .styles import _0, _00, _i, _b, _B, _c, _f, _K, _o, _g, _w, _EOL


list_index_style = '\x1b[3;38;2;160;140;60m'


def print_series_title(list_index:int|None, series:dict, width:int=0, imdb_id:str|None=None, gray:bool=False, tail: str|None=None, tail_style:str|None=None) -> None:

	# this function should never touch the BG color (b/c the list might have alternating bg color)

	left = ''    # parts relative to left edge (num, title, years)
	right = ''   # parts relative to right edge (IMDbID, tail)

	if list_index is not None:
		list_index_w = 5
		width -= list_index_w

		left = f'{list_index_style}{list_index:>{list_index_w}}{_0} '

	right_w = 0

	if imdb_id:
		id_w = 11
		right += f'  {_f}{imdb_id:<{id_w}}{_0}'
		width -= 2 + id_w
		right_w += 2 + id_w

	if tail:
		tail_style = tail_style or ''
		right += f'{tail_style}{tail}{_0}'
		width -= len(tail)
		right_w += len(tail)

	left += format_title(series, width=width)

	series_status = series.get('status')
	if series_status in ('ended', 'canceled'):
		width -= 2 + 5
		left += f'  {_w}{_i}{series_status}{_0}'

	if gray:
		# remove all escape sequences and print in faint-ish gray
		left = f'{_0}\x1b[38;5;246m%s' % strip_ansi(left)
		right = f'{_0}\x1b[38;5;246m%s' % strip_ansi(right)

	print(left, end='')
	# first move to the right edge, then 'right_w' left
	print(f'{_EOL}\x1b[{right_w}D{right}', end='')

	print(_K)


def print_episodes(series:dict, episodes:list[dict], width:int, pre_print:Callable|None=None, also_future:bool=False, limit:int|None=None) -> list[str]:

	seen, unseen = series_seen_unseen(series)
	seen_keys = {episode_key(ep) for ep in seen}

	indent = 6  # nice and also space to print the season "grouping labels"
	current_season = 0
	margin = 1

	ep_width = width - indent - margin

	keys:list[str] = []

	num_printed = 0
	stop_at_date_after = None

	for ep in episodes:

		if limit is not None and num_printed >= limit and stop_at_date_after is not None:
			break
		num_printed += 1

		if pre_print:
			pre_print()
			pre_print = None  # only once

		if stop_at_date_after is not None and stop_at_date_after != ep.get('date'):
			break

		has_seen = episode_key(ep) in seen_keys

		season = ep['season']
		if season != current_season:
			if season == 'S':
				print(f'{_b}%{indent}s {_0}\r' % 'SP ', end='')
			else:
				print(f'{_c}%{indent}s{_0}\r' % f'S{season}', end='')
			current_season = season

		s = format_episode_title(None, ep, include_season=False, width=ep_width, today=True, seen=has_seen)

		# moving cursor instead of writing spaces so we don't overwrite the season label
		print(f'\x1b[{indent + margin}C{s}')

		keys.append(episode_key(ep))

		if not (also_future or is_released(ep)):
			stop_at_date_after = ep.get('date')

	return keys


def print_archive_status(series:dict) -> None:
	if meta_has(series, meta_archived_key):
		print(f'{_f}       Archived', end='')
		seen, unseen = series_seen_unseen(series)
		if seen and unseen:  # some has been seen, but not all
		    print(' / Abandoned', end='')
		print('  ', meta_get(series, meta_archived_key).split()[0], end='')
		print(f'{_0}')


def print_seen_status(series:dict, gray:bool=False, summary:bool=True, next:bool=True, last:bool=True, include_future=False, width:int=0):
	ind = '       '

	seen, unseen = series_seen_unseen(series, before=now_datetime() if not include_future else None)
	all_seen = seen and len(seen) == len(series.get('episodes', []))

	s = ''

	if summary and (seen or unseen):
		s += f'\x1b[38;5;256m{ind}'

		if seen:
			seen_duration = sum((ep.get('runtime') or 0) for ep in seen)*60
			s += f'Seen: {len(seen)} {_f}{format_duration(seen_duration)}{_0}'
			if all_seen:
				s += f'  {_g}ALL{_0}'

		if seen and unseen:
			s += f' {_o}-{_0} '

		if unseen:
			unseen_duration = sum((ep.get('runtime') or 0) for ep in unseen)*60
			s += f'Unseen: {len(unseen)} {_f}{format_duration(unseen_duration)}{_0}'

		if seen or unseen:
			s += _0

		if gray:
			print(f'{_f}{strip_ansi(s)}{_0}')
		else:
			print(s)

	# print('title_width:', title_width)

	if last and seen:  # and not all_seen:
		# show the last *in sequence* episode marked as seen,
		# NOT the episode last *marked* as seen
		if gray:
			print(_f, end='')
		header = f'{ind}Last: '
		print(header, end='')
		print(format_episode_title('', seen[-1], today=True, width=width - len(header), gray=gray))

	if next and unseen:
		if not seen:
			header = f'{ind}First:'
		else:
			header = f'{ind}Next: '
		more = len(unseen) - 1
		s = format_episode_title('', unseen[0], gray=gray, today=True, width=width - len(header), more=more)
		if s:
			if gray:
				print(_f, end='')
			print(f'{header}{s}')


def format_title(series, width:int|None=None):

	title = series['title']
	if width is not None and len(title) > width: # title is too wide
	    # truncate and add ellipsis
		title = title[:width - 1] + '…'

	s = f'\x1b[38;5;253m{title}'

	years = series.get("year")
	if years is not None:
		s += f'  {_0}\x1b[38;5;245m({years[0]}-{years[1] if len(years) == 2 else ""})'

	s += _0

	return s


def format_episode_title(prefix:str|None, episode:dict, include_season:bool=True, include_time:bool=True, width:int=0, gray:bool=False, seen:bool|None=None, today:bool=False, more:int=0) -> str:

	# this function should never touch the BG color (b/c the list might have alternating bg color)

	#    A        B                        C        D       E
	# <s__e__> <title>      - - -      [+N more] [NN min] <date>
	# left-aligned --/                 \---------- right-aligned
	#
	# C is an option
	# D might be missing (no details available)
	# collapsible columns (b/c limited width), in order: D, C, E

	# TODO: see #33
	#   print_series_title() is a bit better

	episode_title_margin = 1

	ep = episode

	season = ep['season']
	episode = ep['episode']

	is_special = season == 'S'

	if include_season:
		s_ep_max_w = len('99:999')
		s_ep_w = len(f'{season}:{episode}')
	else:
		s_ep_max_w = len('999')
		s_ep_w = len(f'{episode}')

	# left-pad to fill the max width
	left_pad = ' '*(s_ep_max_w - s_ep_w)
	if include_season:
		if season == 'S':
			season_ep = f'{_b}SP {_0}\x1b[33m{_b}{episode}'
		else:
			season_ep = f'\x1b[33m{_b}{season}{_0}\x1b[33m:{_b}{episode}'

	elif is_special:
		season_ep = f'\x1b[33m{_b}{episode}'

	else:
		season_ep = f'\x1b[33m{_b}{episode}'

	season_ep = f'{left_pad}{_0}{season_ep}{_0}'
	width -= s_ep_max_w + episode_title_margin

	# Depending on episode release date:
	#   in the future    -> show how long until released
	#   in th past       -> show the date
	#   same date as now -> show 'TODAY'

	ep_date = ep.get('date')

	future = False
	if isinstance(ep_date, str):
		dt = date.fromisoformat(ep_date)
		now_date = now_datetime().date()
		diff = (dt - now_date).total_seconds()
		future = diff > 0

		if today:
			today = dt == now_date
			if today:
				future = False
	else:
		today = False

	# TODO: if 'ep_date' is "recent past" (configurable),
	#   show like "2 weeks ago", which, however, is wider (use "wks"/"mons" ?)

	ep_time_w = len('999 months')  # the longest variant of date or duration
	ep_time = None
	time_style = ''
	if future:
		ep_time = f'{dt}'
		time_style = '\x1b[38;5;244m'

		if diff > 24*3600:
			# longer than 24 hours
			ep_time_w = 16
			ep_time = format_duration(diff, roughly=True)
		else:
			ep_time = 'tomorrow'
			ep_time_w = 10

	elif today:
		ep_time = 'TODAY   '
		ep_time_w = 16
		time_style = _g

	elif isinstance(ep_date, str):
		ep_time = f'{ep_date}'
		time_style = ''

	if not ep_time or not include_time:
		ep_time = ''
		ep_time_w = 0

	if ep_time:
		width -= 1 + ep_time_w
		ep_time = f' {time_style}{ep_time:>{ep_time_w}}{_0}'

	runtime = ep.get('runtime')
	if runtime and isinstance(runtime, int):
		runtime_str = ' %dmin' % runtime  # could use fmt_duration() but we only want minutes here
		width -= len(runtime_str)
	else:
		runtime_str = ''

	more_eps = ''
	if more > 0:
		more_eps = '+%d more    ' % more
		width -= len(more_eps)

	s = ''
	if prefix and prefix is not None:
		s += f'{prefix}'
		width -= len(prefix)

	# not enough space: truncate & ellipt
	if len(ep['title']) > width:
		width -= 1
		ep['title'] = ep['title'][:width] + '…'
		# TODO: to fancy fade to black at the end ;)

	s += f'{season_ep:}{" "*episode_title_margin}{_o}{ep["title"]:{width}}{_0+_f}{more_eps}{_o+_f}{runtime_str}{_0}{ep_time}'

	if gray or seen:
		s = f'{_0}\x1b[38;5;246m%s{_0}' % strip_ansi(s)

	return s


def format_duration(seconds: int | float, roughly: bool=False):
	months = int(seconds//(3600*24*30.4366666))
	seconds -= months*3600*24*30.4366666
	weeks = int(seconds//(3600*24*7))
	seconds -= weeks*3600*24*7
	days = int(seconds//(3600*24))
	seconds -= days*3600*24
	hours = int(seconds//3600)
	seconds -= hours*3600
	minutes = int(seconds//60)
	seconds = 0 #int(seconds%60)

	units = {
	    'short': { 'm': 'm', 'w': 'w', 'd': 'd', 'h': 'h', 'min': 'min', 's': 's' },
		'long': {'m': 'month', 'w': 'week', 'd': 'day', 'h': 'hour', 'min': 'minute', 's': 'second' },
	}
	unit = units['long' if roughly else 'short']
	templ = '%d %s%s' if roughly else '%d%s%s'

	parts = []

	if months > 0:
		parts.append(templ % (months, unit['m'], plural(months if roughly else 1)))
	elif weeks > 0:
		parts.append(templ % (weeks, unit['w'], plural(weeks if roughly else 1)))

	if not roughly or (not months and not weeks):
		if days > 0:
			parts.append(templ % (days, unit['d'], plural(days if roughly else 1)))

	if not roughly:
		if hours > 0:
			parts.append(templ % (hours, unit['h'], plural(hours if roughly else 1)))
		if minutes or (hours > 0 or seconds > 0):
			parts.append(templ % (minutes, unit['min'], plural(minutes if roughly else 1)))
		if seconds:
			parts.append(templ % (seconds, unit['s'], plural(seconds if roughly else 1)))

	return ' '.join(parts)


def menu_select(items:list[dict], width:int, item_print:Callable, force_selection:int|None=None) -> int|None:

	# TODO: the printing of the "info box" should also be a callback, making this quite general :)

	def print_items(current):
		for idx, item in enumerate(items):
			print(_K, end='')
			item_print(idx, item, current=idx == current)
			print('\r', end='')

	def print_info(item):

		_box = _o + _f

		num_lines = 0

		print(f'{_box}┏%s{_0}' % ('━'*(width-1)), end=f'{_K}\n\r')
		print(f'{_box}┃{_0} {_o}Overview:{_0} ', end='')
		num_lines += 1  # overview lines counted below

		if not item.get('overview'):
			overview = [ f'{_i}{_f}no overview available{_0}' ]
			num_lines += 1
		else:
			overview = textwrap.wrap(item['overview'], width=width - 3, initial_indent=' '*11)
			if overview and len(overview[0]) > 11:
				overview[0] = overview[0][11:]

		for idx, line in enumerate(overview):
			num_lines += 1
			if idx > 0:
				print(f'{_box}┃{_0}  ', end='')
			print(line, end=f'{_K}\n\r')

		if 'genre' in item:
			print(f'{_box}┃{_0} {_o}Genre:{_0} ', end='')
			print(item['genre'], end=f'{_K}\n\r')
			num_lines += 1

		print(f'{_box}┃{_0} {_o}Episodes:{_0} ', end='')
		print('%d (%d season%s)' % (item['total_episodes'], item['total_seasons'], 's' if item['total_seasons'] != 1 else ''), end=f'{_K}\n\r')
		num_lines += 1

		print(f'{_box}┗%s{_0}' % ('━'*(width-1)), end=f'{_K}\n\r')
		num_lines += 1
		print(_00, end=_K)

		return num_lines

	selected_index:int|None = 0
	last_info_lines = None

	def draw_menu():
		clrline()

		nonlocal last_info_lines
		if last_info_lines is not None:
			# move up to beginning of menu
			print('\x1b[%dA' % (len(items) + last_info_lines), end='')

		print_items(selected_index)

		info_lines = print_info(items[selected_index])

		if last_info_lines is not None and info_lines < last_info_lines:
			# if the previous info box was longer, clear lines after this info box
			print('\r', end='')
			for n in range(info_lines, last_info_lines):
				print(f'{_K}\r\x1b[1B', end='')
			print('\x1b[%dA' % (last_info_lines - info_lines), end='', flush=True)

		last_info_lines = info_lines

		# print "status bar" at the  bottom
		print(' \x1b[48;2;50;50;70m ', end='')
		if len(items) > 1:
			print(f' {_B}🠕🠗{_0} Select   ', end='')

		if force_selection is None:
			print(f'{_B}Return{_0} Add   {_B}Escape{_0} Cancel', end='')
		else:
			print(f'{_B}Return{_0}/{_B}Escape{_0} Exit', end='')
		print(f'{_K}{_00}', end='\r')

	draw_menu()

	import sys, tty, termios, array, fcntl, select
	infd = sys.stdin.fileno()

	# some keys we want to detect
	UP = '\x1b[A'
	DOWN = '\x1b[B'
	RETURN = ('\x0a', '\x0d')
	CTRL_C = '\x03'
	HOME = '\x1b[H'
	END = '\x1b[F'
	ESC = '\x1b'

	old_settings = termios.tcgetattr(infd)
	try:
		tty.setraw(sys.stdin.fileno())
		avail_buf = array.array('i', [0])

		epoll = select.epoll()
		epoll.register(infd, select.EPOLLIN | select.EPOLLERR | select.EPOLLHUP | select.EPOLLPRI)

		while True:
			# wait for input on the file descriptor
			events = epoll.poll(1)
			if not events:
				time.sleep(1)
				continue

			# check how much is available to read
			fcntl.ioctl(infd, termios.FIONREAD, avail_buf, True)
			avail = avail_buf[0]
			if avail == 0:
				continue

			# TODO: append (and consume below)
			buf = sys.stdin.read(avail)

			if buf in (CTRL_C, ESC, 'q'):
				selected_index = None  # canceled

			if selected_index is None: # explicit type check for mypy
			    break

			if buf in RETURN:
				break

			prev_index = selected_index

			if buf == UP and selected_index > 0:
				selected_index -= 1

			elif buf == DOWN and selected_index < len(items) - 1:
				selected_index += 1

			elif buf == HOME and selected_index > 0:
				selected_index = 0

			elif buf == END and selected_index < len(items) - 1:
				selected_index = len(items) - 1

			if selected_index != prev_index:
				draw_menu()

	finally:
		epoll.close()
		termios.tcsetattr(infd, termios.TCSADRAIN, old_settings)

	print(_K)

	if force_selection is not None:
		return force_selection

	return selected_index


def is_released(target, fallback=True):
	release_date = target.get('date')
	if release_date is None:
		return fallback

	# already released or will be today
	return date.fromisoformat(release_date) <= today_date


def clrline():
	print(f'{_00}\r{_K}', end='')
