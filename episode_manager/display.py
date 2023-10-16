
from datetime import date
from typing import Callable

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
from .styles import _0, _i, _b, _c, _f, _K, _o, _g, _w, _EOL


list_index_style = '\x1b[3;38;2;200;160;100m'


def print_series_title(num:int|None, series:dict, width:int=0, imdb_id:str|None=None, gray:bool=False, tail: str|None=None, tail_style:str|None=None) -> None:

	# this function should never touch the BG color (b/c the list might have alternating bg color)

	left = ''    # parts relative to left edge (num, title, years)
	right = ''   # parts relative to right edge (IMDbID, tail)

	if num is not None:
		num_w = 5
		width -= num_w

		left = f'{list_index_style}{num:>{num_w}}{_0} '

	r_offset = 0

	if imdb_id:
		id_w = 11
		right += f'  {_f}{imdb_id:<{id_w}}{_0}'
		width -= 2 + id_w
		r_offset += 2 + id_w

	if tail:
		tail_style = tail_style or ''
		right += f'{tail_style}{tail}{_0}'
		width -= len(tail)
		r_offset += len(tail)

	left += format_title(series, width=width) #f' \x1b[38;5;253m{title}{_0}{years}'

	series_status = series.get('status')
	if series_status in ('ended', 'canceled'):
		width -= 2 + 5
		left += f'  {_w}{_i}{series_status}{_0}'

	if gray:
		# remove all escape sequences and print in faint-ish gray
		left = f'{_0}\x1b[38;5;246m%s' % strip_ansi(left)
		right = f'{_0}\x1b[38;5;246m%s' % strip_ansi(right)

	print(left, end='')
	# first move to the right edge, then 'r_offset' left
	print(f'{_EOL}\x1b[{r_offset}D{right}', end='')

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
				print(f'{_c}%{indent}s{_0}\r' % (f's{season}'), end='')
			current_season = season

		s = format_episode_title(None, ep, width=ep_width, today=True, seen=has_seen)

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


def print_seen_status(series:dict, gray:bool=False, summary:bool=True, next:bool=True, last:bool=True, width:int=0):
	ind = '       '

	seen, unseen = series_seen_unseen(series)
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
		print(format_episode_title('', seen[-1], gray=gray, include_season=True, today=True, width=width - len(header)))

	if next and unseen:
		if not seen:
			header = f'{ind}First:'
		else:
			header = f'{ind}Next: '
		more = len(unseen) - 1
		s = format_episode_title('', unseen[0], gray=gray, include_season=True, today=True, width=width - len(header), more=more)
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


def format_episode_title(prefix:str|None, episode:dict, include_season:bool=False, include_time:bool=True, width:int=0, gray:bool=False, seen:bool|None=None, today:bool=False, more:int=0) -> str:

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
		s_ep_max_w = len('s99e999')
		s_ep_w = len(f's{season}e{episode:02}')
	else:
		s_ep_max_w = len('e999')
		s_ep_w = len(f'e{episode:02}')

	# left-pad to fill the max width
	left_pad = ' '*(s_ep_max_w - s_ep_w)
	if include_season:
		if season == 'S':
			season_ep = f'{_b}SP {_0}\x1b[33m{_b}{episode}'
		else:
			season_ep = f'\x1b[33ms{_b}{season}{_0}\x1b[33me{_b}{episode:02}'

	elif is_special:
		season_ep = f'\x1b[33m{_b}{episode}'

	else:
		season_ep = f'\x1b[33me{_b}{episode:02}'

	season_ep = f'{left_pad}{_0}{season_ep}{_0}'
	width -= s_ep_max_w + episode_title_margin

	# Depending on episode release date:
	#   in the future    -> show how long until release (or nothing if only_released=True)
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


def is_released(target, fallback=True):
	release_date = target.get('date')
	if release_date is None:
		return fallback

	# already released or will be today
	return date.fromisoformat(release_date) <= today_date