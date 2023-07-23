#! /usr/bin/env python3
# -*- mode: python -*-
import re
import shlex
import time
import atexit
from datetime import datetime, date, timedelta
from os.path import basename
from calendar import Calendar, day_name, month_name, MONDAY, SUNDAY
import textwrap
import random

from typing import Callable, Any

from . import tmdb, progress, config, utils, db, db as m_db
from .context import Context, BadUsageError
from .config import Store, debug
from .utils import term_size, warning_prefix, plural, clrline, now_datetime, now_stamp
from .db import State, set_dirty, meta_get, meta_set, meta_has, meta_del, meta_copy, meta_seen_key, meta_archived_key, changelog_add, \
	meta_added_key, meta_update_check_key, meta_update_history_key, meta_rating_key, meta_rating_comment_key, meta_list_index_key, meta_next_list_index_key, meta_add_comment_key, \
	series_state, series_seen_unseen, episode_key, next_unseen_episode, last_seen_episode
from .styles import _0, _00, _0B, _c, _i, _b, _f, _fi, _K, _E, _o, _g, _u, _w, _EOL

import sys

PRG = basename(sys.argv[0])

VERSION = '0.19'
VERSION_DATE = '2023-07-23'


def start():
	config.load()
	# print(orjson.dumps(app_config, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode('utf-8'))
	atexit.register(config.save)

	api_key = config.get('lookup/api-key') or tmdb.key_from_env()
	if api_key:
		tmdb.set_api_key(api_key)

	# we set these functions to avoid import cycle
	ctx = Context(eat_option, resolve_cmd)

	try:
		ctx.parse_args(sys.argv[1: ])

	except BadUsageError:
		print_usage()

	ctx.configure_handler(known_commands)

	width, height = term_size()

	err = ctx.invoke(width=width)
	if err is not None:
		print(f'{warning_prefix(ctx.command)} {err}')
		sys.exit(1)


###############################################################################


def resolve_cmd(name:str, fail_ok=False) -> str|None:
	matching = []

	for primary in known_commands:
		cmd_def = known_commands[primary]
		aliases = cmd_def.get('alias')
		names:list[str] = [primary] + list(aliases if isinstance(aliases, tuple) else ())

		for alias in names:
			if name == alias:
				return primary  # direct match (case sensitive), just return
			if alias.startswith(name.lower()):
				matching.append(primary)
				# don't break, there might be an exact match for an alias

	if len(matching) == 1:
		return matching[0]

	if len(matching) > 1 and not fail_ok:
		ambiguous_cmd(name, matching)

	if not fail_ok:
		bad_cmd(name)

	return None


long_option_arg_ptn = re.compile(r'^(?P<option>--[^= ]+)(?:=(?P<arg>.*))$')

def eat_option(command:str|None, option:str, args:list[str], options:dict, unknown_ok=False) -> bool:
	if option in ('-h', '--help'):
		if command:
			print_cmd_help(command)
		else:
			print_usage()

	option_arg:str|None = None

	# check if it's a long option combined with an argument, i.e. --option=argument
	m = long_option_arg_ptn.search(option)
	if m:
		option = m.group('option')
		option_arg = m.groupdict().get('arg', None)

	# print('option:', option, 'arg:', option_arg)

	opt_def = option_def(command, option)

	# print('def:', opt_def)

	if not opt_def:
		if unknown_ok:
			return False
		bad_opt(command, option)

	key:str = opt_def['key']

	set_func = opt_def.get('func')
	if not set_func:
		def _set_opt(v, key, options):
			# print('OPT>', key, '=', v)
			options[key] = v
		set_func = _set_opt

	arg_type = opt_def.get('arg')

	# print('arg type:', arg_type.__name__)

	if not arg_type:  # no argument expected
		if option_arg:  # but an argument was supplied
			bad_opt_arg(command, option, option_arg, None)

		set_func(True, key, options)

	else:
		if m:
			# long option expecting argument (but none yet supplied)
			if option_arg is None and args:
				option_arg = args.pop(0)

		elif args:
			option_arg = args.pop(0)

		if option_arg is None:
			bad_opt_arg(command, option, None, arg_type)

		arg_str = str(option_arg)  # for mypy

		validator = opt_def.get('validator', lambda v: v)
		validator_explain = validator.__doc__ or ''

		if arg_type is date:
			try:
				d = date.fromisoformat(arg_str)
				d = validator(d)
				if d is None:
					raise ValueError
				err = set_func(d, key, options)
				if err:
					bad_opt_arg(command, option, arg_str, arg_type, explain=err)
			except ValueError:
				bad_opt_arg(command, option, arg_str, arg_type, explain=validator_explain)

		else:
			try:
				v = arg_type(arg_str)
				v = validator(v)
				if v is None:
					raise ValueError
				err = set_func(v, key, options)
				if err:
					bad_opt_arg(command, option, arg_str, arg_type, explain=err)
			except ValueError:
				bad_opt_arg(command, option, arg_str, arg_type, explain=validator_explain)

	return True


def bad_cmd(cmd:str) -> None:
	print(f'{warning_prefix()} Unknown command: {_E}%s{_00}' % cmd, file=sys.stderr)
	sys.exit(1)

def bad_opt(command:str|None, option:str) -> None:
	print(f'{warning_prefix(command)} Unknown option: {option}', file=sys.stderr)
	sys.exit(1)

def bad_opt_arg(command:str|None, option, arg, arg_type:Callable|None, explain:str|None=None) -> None:
	print(warning_prefix(command), end='', file=sys.stderr)

	expected = None
	if arg_type is not None:
		expected = arg_type.__name__

	if expected is None:
		print(f' Unexpected argument for {_o}{option}{_0}: {_b}{arg}{_0}', file=sys.stderr, end='')
	elif arg is None:
		explain = ('; %s' % explain) if explain else ''
		print(f' Required argument missing for {_o}{option}{_0}{explain}', file=sys.stderr, end='')
	else:
		print(f' Bad option argument for {_o}{option}{_0}: {_b}{arg}{_0}  ', file=sys.stderr, end='')
		if arg_type is str:
			print(f'(expected {explain})', file=sys.stderr, end='')
		else:
			explain = ('; %s' % explain) if explain else ''
			print(f'({expected} expected{explain})', file=sys.stderr, end='')

	print(file=sys.stderr)

	sys.exit(1)


def ambiguous_cmd(name:str, matching:list[str]) -> None:
	print(f'{warning_prefix()} Ambiguous command: {_E}%s{_00}  matches: %s' % (name, f'{_o},{_0} '.join(sorted(matching))), file=sys.stderr)
	sys.exit(1)


class Error(str):
	pass


###############################################################################
###############################################################################

def cmd_info(ctx:Context, width:int) -> Error|None:
	ctx.command_options['details'] = True
	if not ctx.command_arguments:
		return Error('Specify which series to show.')

	return cmd_show(ctx, width)

def _info_help() -> None:
	print_cmd_usage('info', '<series>')
	print(f'    {_o}<series>       {_0} Series to show')

setattr(cmd_info, 'help', _info_help)


def cmd_unseen(ctx:Context, width:int) -> Error|None:
	ctx.command_options['with-unseen'] = True
	ctx.command_options['next-episode'] = True
	ctx.command_options['no-seen-summary'] = True
	return cmd_show(ctx, width)

def _unseen_help() -> None:
	print_cmd_usage('unseen', '<options> [<series>]')
	print(f'    {_o}<series>            {_0} Show only specific series')

setattr(cmd_unseen, 'help', _unseen_help)


def cmd_show(ctx:Context, width:int) -> Error|None:
	# TODO: print header/columns

	list_all = ctx.has_option('all')
	only_archived = ctx.has_option('archived')
	only_started = ctx.has_option('started')
	only_planned = ctx.has_option('planned')
	only_abandoned = ctx.has_option('abandoned')
	with_unseen_eps = ctx.has_option('with-unseen')
	all_unseen_eps = ctx.has_option('all-episodes')
	future_eps = ctx.has_option('future-episodes')
	seen_eps = ctx.has_option('seen-episodes')
	show_next = ctx.has_option('next-episode')
	no_summary =  ctx.has_option('no-seen-summary')
	show_details = ctx.has_option('details')
	show_terse = ctx.has_option('terse')
	if show_terse:
		show_details = False

	if [only_started, only_planned, only_archived, only_abandoned].count(True) > 1:
		return Error('Specify only one of "started", "planned", "archived" and "abandoned"')

	if all_unseen_eps:
		show_next = False

	if debug:
		def _bool_color(b:bool) -> str:
			if b:
				return f'{_g}True{_0}'
			return f'\x1b[31;1mFalse{_0}'
		debug('  list_all:       ', _bool_color(list_all))
		debug('  only_archived:  ', _bool_color(only_archived))
		debug('  only_started:   ', _bool_color(only_started))
		debug('  only_planned:   ', _bool_color(only_planned))
		debug('  only_abandoned: ', _bool_color(only_abandoned))
		debug('  with_unseen_eps:', _bool_color(with_unseen_eps))
		debug('  all_unseen_eps: ', _bool_color(all_unseen_eps))
		debug('  future_eps:     ', _bool_color(future_eps))
		debug('  seen_eps:       ', _bool_color(seen_eps))
		debug('  show_next:      ', _bool_color(show_next))
		debug('  show_details:   ', _bool_color(show_details))
		debug('  show_terse:     ', _bool_color(show_terse))

	find_state:State|None = State.ACTIVE
	if list_all:
		find_state = None
	elif only_started:
		find_state = State.STARTED
	elif only_planned:
		find_state = State.PLANNED
	elif only_archived:
		find_state = State.ARCHIVED
	elif only_abandoned:
		find_state = State.ABANDONED

	filter_country = ctx.option('country')
	filter_director = ctx.option('director')
	filter_writer = ctx.option('writer')
	filter_cast = ctx.option('cast')
	filter_year = ctx.option('year')

	# NOTE: in the future, might support RE directly from the user
	if filter_country:
		# "us,se" -> "US|SE"
		filter_country = filter_country.upper().replace(',', '|')
		filter_country = re.compile(filter_country)
	if filter_director:
		filter_director = _substr_re(filter_director)
	if filter_writer:
		filter_writer = _substr_re(filter_writer)
	if filter_cast:
		filter_cast = _substr_re(filter_cast)
	if filter_year:
		try:
			filter_year = [int(y) for y in filter_year.split('-')]
		except:
			return Error('Bad year filter: %s (use: <start year>[-<end year>])' % filter_year)

	sort_key:Callable[[tuple[str,dict]],Any]|None = None

	sorting = ctx.command_options.get('sorting', [])
	if sorting:
		def _series_key(series:dict, key:str) -> str:
			# possible values are checked by _opt_sort_names
			if key == 'earliest':
				next_ep = next_unseen_episode(series)
				if not next_ep:
					return '\xff'
				return next_ep.get('date') or ''
			elif key == 'latest':
				last_ep, marked = last_seen_episode(series)
				if not last_ep or marked is None:
					return '\xff'
				return marked
			elif key in series:  # possible values are checked by _opt_sort_names
				return str(series[key])
			else:
				# possible values are checked by _opt_sort_names
				return meta_get(series, key) or ''

		def _sort_key(item:tuple[str,dict]) -> Any:
			index, series = item
			return tuple(
				_series_key(series, ord) for ord in sorting
			)
		sort_key = _sort_key

	# refresh everything
	modified = refresh_series(ctx.db, width=width)

	find_idx, match = find_idx_or_match(ctx.command_arguments, country=filter_country, director=filter_director, writer=filter_writer, cast=filter_cast, year=filter_year)
	series_list = db.indexed_series(ctx.db, state=find_state, index=find_idx, match=match, sort_key=sort_key)

	if not series_list:
		return no_series(ctx.db, filtered=bool(match or filter_director or filter_writer or filter_cast or filter_year))

	print(f'Listing ', end='')
	if only_started: print(f'{_u}started{_0} ', end='')
	elif only_planned: print(f'{_u}planned{_0} ', end='')
	elif only_archived: print(f'{_u}archived{_0} ', end='')
	elif only_abandoned: print(f'{_u}abandoned{_0} ', end='')
	else: print(f'{_u}non-archived{_0} ', end='')
	print('series', end='')
	if with_unseen_eps: print(f' with {_u}unseen{_0} episodes', end='')
	if match: print(', matching: %s' % getattr(match, 'styled_description'), end='')
	print(f'{_0}.')

	num_shown = 0
	num_archived = 0

	from_date = now_datetime() if not future_eps else None
	ep_limit = None
	if not all_unseen_eps:
		ep_limit = 1

	debug('  ep_limit:', ep_limit)
	debug('  episodes from date:', from_date)

	for index, series_id in series_list:
		series = ctx.db[series_id]
		is_archived = meta_has(series, meta_archived_key)

		seen, unseen = series_seen_unseen(series, from_date)
		# debug(f'{_f}"{series["title"]}" seen: {len(seen)} unseen: {len(unseen)}{_0}')

		if with_unseen_eps and not unseen:
			continue

		num_shown += 1

		# alternate styling odd/even rows
		hilite = (num_shown % 2) == 0
		if hilite:
			print(f'\x1b[48;5;234m{_K}\r', end='')

		if show_details:
			print_series_details(index, series,width=width, gray=is_archived and not only_archived)
		else:
			print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width, gray=is_archived and not only_archived)
			if not show_terse:
				print_archive_status(series)

		if not show_terse:
			# don't print "next" if we're printing all unseen episodes anyway
			print_seen_status(
				series,
				summary=(not show_next or not all_unseen_eps) and not no_summary,
				last=not show_next and not all_unseen_eps,
				next=show_next or not all_unseen_eps,
				width=width,
				gray=is_archived and not only_archived,
			)

			if seen_eps:
				print_episodes(series, seen, width=width)

			if all_unseen_eps or (future_eps and not show_next):
				print_episodes(series, unseen, width=width, limit=ep_limit, also_future=future_eps)

		if hilite:
			print(f'{_00}{_K}', end='')

	if max(modified) > 0:
		ctx.save()

	if num_shown == 0:
		if match:
			return Error('Nothing matched')

	print(f'{_00}{_K}', end='')
	print(f'{_b}\x1b[48;2;20;50;20m{_K}\r%d series {_fi} Total: %d   Archived: %d{_0}' % (num_shown, len(series_list), num_archived))

	return None

def _show_help() -> None:
	print_cmd_usage('show', '<options> [<series>]')
	print(f'    {_o}<series>     {_0} Show only matching series')

setattr(cmd_show, 'help', _show_help)


def cmd_calendar(ctx:Context, width:int) -> Error|None:

	# refresh everything
	modified = refresh_series(ctx.db, width=width)
	if max(modified) > 0:
		ctx.save()

	cal = Calendar(MONDAY)
	begin_date:date = date.today()
	num_weeks = 2

	if ctx.command_arguments:
		arg = ctx.command_arguments.pop(0)
		try:
			num_weeks = int(arg)
		except ValueError:
			try:
				begin_date = date.fromisoformat(arg)
			except ValueError:
				return Error(f'Unknown argument: {arg}')
	else:
		num_weeks = config.get_int('commands/calendar/num_weeks', 1)

	start_date:date = begin_date

	episodes_by_date:dict[date,list] = {}

	# collect episodes over num_weeks*7
	#   using margin of one extra week, because it's simpler
	end_date = start_date + timedelta(days=(num_weeks + 1)*7)
	for series_id in db.all_ids(ctx.db):
		series = ctx.db[series_id]

		if meta_has(series, meta_archived_key):
			continue

		# faster to loop backwards?
		for ep in series.get('episodes', []):
			ep_date_str = ep.get('date')
			if not ep_date_str:
				continue

			ep_date = date.fromisoformat(ep_date_str)
			if ep_date >= begin_date and ep_date < end_date:
				if ep_date not in episodes_by_date:
					episodes_by_date[ep_date] = []
				episodes_by_date[ep_date].append( (series, ep) )

	wday_idx = -1
	days_todo = num_weeks*7
	def ordinal_suffix(n):
		digit = n % 10
		return {1: 'st', 2: 'nd', 3: 'rd'}.get(digit, 'th')

	def print_month_divider(d):
		print(f'{_f}┏%s┥{_0} {_b}%s %s{_0}  {_f}week %d{_0}' % ('━' * 12, month_name[d.month], d.year, d.isocalendar()[1]))

	def print_week_divider(d):
		print(f'{_f}┠%s week %d{_0}' % ('─' * 8, d.isocalendar()[1]))

	print_month_divider(start_date)
	prev_month = start_date.month
	first = True  # to avoid printing week label the first loop

	# TODO: is there's nothing for a whole week, print just "nothing" (i.e. not each day)

	# until we've printed enough days, and always end at a full week
	while days_todo > 0 or wday_idx != SUNDAY:
		# print('print starting from:', start_date, days_todo)

		for mdate in cal.itermonthdates(start_date.year, start_date.month):
			wday_idx = (wday_idx + 1) % 7
			if mdate < begin_date:
				continue

			days_todo -= 1

			if mdate.month != prev_month:
				print_month_divider(mdate)
				prev_month = mdate.month
			elif wday_idx == MONDAY and not first:
				print_week_divider(mdate)
			first = False

			wday = day_name[wday_idx]
			print(f'{_f}┃{_0} {_i}{mdate.day:2}{_f}{ordinal_suffix(mdate.day)}{_0} {_o}{_i}{_f}{wday}{_0}')

			episodes = episodes_by_date.get(mdate, [])
			for series, ep in episodes:
				ep_title = format_episode_title(series['title'], ep, include_season=True, include_time=False, width=width - 9)
				print(f'{_f}┃{_0}      {_c}•{_0} {ep_title}')

			if days_todo <= 0 and wday_idx == SUNDAY:
				break

		start_date += timedelta(days=31)
		start_date = start_date.replace(day=1)

	return None

def _calendar_help():
	print_cmd_usage('calendar', '[<num weeks> | <start date>]')

setattr(cmd_calendar, 'help', _calendar_help)



year_ptn = re.compile(r'^(\d{4})|\((\d{4})\)$')  # 1968 or (1968)

def cmd_add(ctx:Context, width:int, add:bool=True) -> Error|None:
	if not ctx.command_arguments:
		return Error('required argument missing: <title> / <Series ID>')

	max_hits = int(ctx.option('max-hits', config.get_int('lookup/max-hits')))

	height = term_size()[1]
	# 'Found...' + divider above overview + divider below overview + "status bar"
	menu_padding = 1 + 1 + 1 + 1

	overview_limit = 8
	term_max_hits = height - menu_padding - overview_limit
	if term_max_hits < 1:
		return Error('Terminal too small')

	if max_hits > term_max_hits:
		max_hits = term_max_hits
		print(f'{warning_prefix(ctx.command)} limited hits to %d (resize terminal to fit more)' % max_hits)

	args = list(a for a in ' '.join(ctx.command_arguments).split())
	year = None
	if len(args) >= 2:
		# does the last word look like a year?
		m = year_ptn.match(args[-1])
		if m:
			y = int(m.group(1) or m.group(2))
			if y in range(1800, 2100):  # very rough valid range
				year = y
				args.pop()

	search = ' '.join(args)
	print(f'{_f}- Searching "{search}"', end='')
	if year:
		print(f' ({year})', end='')
	print(f' ... (max {max_hits} hits){_00}', end='', flush=True)

	hits:list[dict] = []
	page = 1

	while len(hits) < max_hits:
		page_hits, total = tmdb.search(search, year=year, page=page)
		hits.extend(page_hits)
		if not page_hits or total == len(hits):
			break

		page += 1

	clrline()

	if not hits:
		return Error('Nothing found. Try generalizing your search.')

	# exclude ones we already have in our config
	if add:
		already = list(filter(lambda H: H['id'] in ctx.db, hits))
		if already:
			print(f'{_f}Already added: %d{_0}' % len(already))
			for new_series in already:
				if meta_has(ctx.db[new_series['id']], meta_archived_key):
					arch_tail = f'  \x1b[33m(archived){_0}'
				else:
					arch_tail = None

				imdb_id = ctx.db[new_series['id']].get('imdb_id')
				print_series_title(None, ctx.db[new_series['id']], imdb_id=imdb_id, gray=True, tail=arch_tail, width=width)

		hits = list(filter(lambda H: H['id'] not in ctx.db, hits))

		if not hits:
			return Error('No new series found. Try generalizing your search.')

	if len(hits) > max_hits:
		hits = hits[: max_hits]

	print(f'{_g}Found {_00}{_b}%d{_00} {_g}series:{_00}' % len(hits))

	print(f'{_f}Enriching search hits...{_00}', end='', flush=True)
	hit_details = tmdb.details(hit['id'] for hit in hits)

	clrline()

	for idx, hit in enumerate(hits):
		hit.update(hit_details[idx])

	# print a menu and a prompt to select from it

	def print_menu_entry(idx:int, item:dict[str,Any], current:bool=False):
		imdb_id = item.get('imdb_id')
		tail = None
		if 'total_episodes' in item:
			if 'specials' in item:
				tail = '%5d eps/%d SP' % (item['total_episodes'], item['specials'])
			else:
				tail = '%5d episodes' % item['total_episodes']
		if current:
			print(f'\x1b[48;2;60;70;90m{_K}', end='')
		print_series_title(idx + 1, item, imdb_id=imdb_id, width=width, tail=tail)
		print(f'{_0B}{_K}', end='')

	selected = menu_select(hits, width, print_menu_entry, force_selection=-1 if not add else None)
	if selected == -1:
		return None


	if selected is None:
		return Error('Nothing selected or cancelled')

	# TODO: move actual "add" to a separate function

	new_series = hits[selected]
	series_id = new_series['id']

	meta_set(new_series, meta_seen_key, {})
	meta_set(new_series, meta_added_key, now_stamp())

	# assign 'list index', and advance the global
	next_list_index = meta_get(ctx.db, meta_next_list_index_key)
	meta_set(new_series, meta_list_index_key, next_list_index)
	meta_set(ctx.db, meta_next_list_index_key, next_list_index + 1)

	if ctx.option('comment'):
		comment = ctx.option('comment').strip()
	else:
		comment = input('Write a comment (empty to skip): ').strip()

	if comment:
		meta_set(new_series, meta_add_comment_key, comment)

	ctx.db[series_id] = new_series

	changelog_add(ctx.db, 'Added series', series_id)

	modified = refresh_series(ctx.db, width, subset=[series_id], force=True)
	if max(modified) > 0:
		ctx.save()

	print(f'{_b}Series added:{_00}')

	# need to loop to figure out its list index
	imdb_id = ctx.db[series_id].get('imdb_id')
	index = meta_get(ctx.db[series_id], meta_list_index_key)
	print_series_title(index, new_series, imdb_id=imdb_id, width=width, tail=f'  [{State.PLANNED.name.lower()}]')

	return None


def menu_select(items:list[dict], width:int, item_print:Callable, force_selection:int|None=None) -> int|None:

	def print_items(current):
		for idx, item in enumerate(items):
			is_current = idx == current
			print(_K, end='')
			item_print(idx, item, current=is_current)
			print('\r', end='')
			if is_current:
				print('\x1b[1A⯈\r\x1b[1B', end='') # move up, print, then down again

	def print_info(idx):
		print(f'{_f}┏%s{_0}' % ('━'*(width-1)), end=f'{_K}\n\r')
		print(f'{_f}┃{_0} {_o}Overview:{_0} ', end='')

		item = items[idx]

		if not item.get('overview'):
			overview = [ f'{_i}{_f}no overview available{_0}' ]
		else:
			overview = textwrap.wrap(item['overview'], width=width - 1, initial_indent=' '*11)
			if overview and len(overview[0]) > 11:
				overview[0] = overview[0][11:]

		for idx, line in enumerate(overview):
			if idx > 0:
				print(f'{_f}┃{_0}', end='')
			print(line, end=f'{_K}\n\r')

		if 'genre' in item:
			print(f'{_f}┃{_0} {_o}Genre:{_0} ', end='')
			print(item['genre'])

		print(f'{_f}┃{_0} {_o}Episodes:{_0} ', end='')
		print('%d (%d season%s)' % (item['total_episodes'], item['total_seasons'], 's' if item['total_seasons'] != 1 else ''))

		print(f'{_f}┗%s{_0}' % ('━'*(width-1)), end=f'{_K}\n\r')

		return 1 + len(overview) + 1

	selected:int|None = 0
	last_info_lines = None

	def draw_menu():
		nonlocal last_info_lines
		if last_info_lines is not None:
			# move up to beginning of menu
			print('\x1b[%dA' % (len(items) + last_info_lines), end='')

		print_items(selected)

		info_lines = print_info(selected)
		if last_info_lines is not None and info_lines < last_info_lines:
			print(_00, end=_K)
			for n in range(info_lines, last_info_lines):
				print(f'\n{_K}', end='')
			print('\x1b[%dA' % (last_info_lines - info_lines), end='', flush=True)
		last_info_lines = info_lines

		# print "status bar"
		print(f' \x1b[97;48;2;60;60;90m ', end='')
		if len(items) > 1:
			print(f' 🠕 and 🠗 keys to select   ', end='')

		if force_selection is None:
			print(f'[RET] to add   [ESC] to cancel', end='')
		else:
			print(f'[RET]/[ESC] to exit', end='')
		print(f'{_K}{_00}', end='\r')

	draw_menu()

	import sys, tty, termios, array
	infd = sys.stdin.fileno()

	# some keys we want to detect
	UP = '\x1b[A'
	DOWN = '\x1b[B'
	RETURN = ('\x0a', '\x0d')
	CTRL_C = '\x03'
	ESC = '\x1b'

	import fcntl
	old_settings = termios.tcgetattr(infd)
	try:
		tty.setraw(sys.stdin.fileno())
		avail_buf = array.array('i', [0])
		while True:
			fcntl.ioctl(infd, termios.FIONREAD, avail_buf, True)
			avail = avail_buf[0]
			if avail == 0:
				time.sleep(0.1)
				continue

			# TODO: append (and consume below)
			buf = sys.stdin.read(avail)

			if buf in (CTRL_C, ESC):
				selected = None  # canceled

			if selected is None: # explicit type check for mypy
				break

			if buf in RETURN:
				break

			if buf == UP and selected > 0:
				selected -= 1
				draw_menu()

			elif buf == DOWN and selected < len(items) - 1:
				selected += 1
				draw_menu()
	finally:
		termios.tcsetattr(infd, termios.TCSADRAIN, old_settings)

	print(_K)

	if force_selection is not None:
		return force_selection

	return selected


def _add_help() -> None:
	print_cmd_usage('add', '<title search> [<year>]')

setattr(cmd_add, 'help', _add_help)


def cmd_search(ctx:Context, width:int) -> Error|None:
	return cmd_add(ctx, width, add=False)

def _search_help() -> None:
	print_cmd_usage('search', '<title search> [<year>]')

setattr(cmd_search, 'help', _search_help)


def cmd_delete(ctx:Context, width:int) -> Error|None:
	if not ctx.command_arguments:
		return Error('Required argument missing: # / <IMDb ID>')

	index, series_id, err = db.find_single_series(ctx.db, ctx.command_arguments.pop(0))
	if series_id is None or err is not None:
		if isinstance(err, list):
			found = err
			# TODO: if more than 4, list the "closest" ones
			message = ', '.join(f'{list_index_style}{idx}{_0} %s' % format_title(ctx.db[sid]) for idx, sid in found[:4])
			return Error(f'Ambiguous ({len(found)}): %s' % message)
		return Error(err)

	series = ctx.db[series_id]

	print(f'{_b}Deleting series:{_00}')
	print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width)

	seen, unseen = series_seen_unseen(series)
	partly_seen = seen and unseen

	choices = ['yes']
	if partly_seen:
		print('You have seen %d episodes of %d.' % (len(seen), len(seen) + len(unseen)))
		choices.append('abandon')
		question = 'Delete permanently or mark abandoned?'
		full_answer_a = 'abandon'

	else:
		choices.append('archive')
		question = 'Delete permanently or archive?'
		full_answer_a = 'archive'

	answer = input(f'\x1b[41;37;1m{question}{_00} [No/{"/".join(choices)}] ').lower()
	if answer not in ('y', 'yes', 'a', full_answer_a):
		return Error('Cancelled')

	if answer in ('a', full_answer_a):
		return cmd_archive(ctx, width)  # also checks for abandon


	# delete it
	del ctx.db[series_id]

	changelog_add(ctx.db, 'Deleted series "%s"' % series['title'])

	# if we deleted the last series, roll back "next index"
	next_index = meta_get(ctx.db, meta_next_list_index_key)
	if index + 1 == next_index:
		meta_set(ctx.db, meta_next_list_index_key, index)

	ctx.save()

	print(f'{_b}Series deleted:{_b}')
	print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width)

	return None

def _delete_help() -> None:
	print_cmd_usage('delete', '<series>')
	print(f'    {_o}<series>{_0}')

setattr(cmd_delete, 'help', _delete_help)

def cmd_mark(ctx:Context, width:int, marking:bool=True) -> Error|None:

	if not ctx.command_arguments:
		return Error('Required argument missing: # / <IMDb ID>')

	find = ctx.command_arguments.pop(0)

	state_filter = State.PLANNED | State.STARTED
	if not marking:
		state_filter = State.STARTED | State.COMPLETED

	def filter_callback(series:dict) -> bool:
		return series_state(series) & state_filter > 0

	index, series_id, err = db.find_single_series(ctx.db, find, filter_callback)
	if series_id is None or err is not None:
		if isinstance(err, list):
			found = err
			# TODO: if more than 4, list the "closest" ones
			message = ', '.join(f'{list_index_style}{idx}{_0} %s' % format_title(ctx.db[sid]) for idx, sid in found[:4])
			return Error(f'Ambiguous ({len(found)}): %s' % message)
		return Error(err)

	# we've come upon a series that is stale, do a refresh
	modified = refresh_series(ctx.db, width, subset=[series_id])
	if max(modified) > 0:
		ctx.save()

	series = ctx.db[series_id]

	season:None|range|tuple = None
	episode:None|range|tuple = None

	ep_ptn = re.compile(r'^\s*(s\d+(-\d+)?)(e\d+(-\d+)?)\s*$')

	# supported syntaxes:
	#   nothing:                                (next episode)
	#   'next'                                  (next episode)
	#   'all'                                   (everything)
	#   'special'                               (next special)
	#   single numbers:              1 2        (season 1, episode 2)
	#   ranges:                      1-2 1-5    (seasons 1-2, episodes 1-5)
	#   season descriptor:           s1         (season 1, all episodes)
	#   "descriptor":                s1e2       (season 1, episode 2)
	#   "descriptor" spaces:         s1 e2      (season 1, episode 2)
	#   "descriptor" ranges:         s1-3e1-4   (seasons 1-3, episodes 1-4)
	#   "descriptor" spaced ranges:  s1-3 e1-4  (seasons 1-3, episodes 1-4)

	args = [*ctx.command_arguments]

	incremental = False

	if not args:
		if marking:   # no season/episode specifier is the same as 'next episode'
			args = ['next']
		else:
			args = ['last']

	if len(args) == 1 and marking and args[0] in ('next', 'n'):
		# mark next logical episode
		next_unseen = next_unseen_episode(series)
		if not next_unseen:
			return Error('there is no logical next episode')
		elif next_unseen == (0, 0):
			season = (1, )
			episode = (1, )
		else:
			season = (next_unseen.get('season'), )
			episode = (next_unseen.get('episode'), )
		incremental = True

	elif len(args) == 1 and not marking and args[0] in ('last', 'l'):
		# unmark the last marked episode
		last_seen, _ = db.last_seen_episode(series)
		if not last_seen:
			return Error('no episode marked')

		season = (last_seen.get('season'), )
		episode = (last_seen.get('episode'), )
		incremental = True

	elif len(args) == 1 and args[0].lower() == 'all':
		season = None
		episode = None
		incremental = True

	elif len(args) == 1 and args[0].lower() in ('special', 's'):
		season = ('S', )
		seen, unseen = db.series_seen_unseen(series)
		special_eps = [ep for ep in unseen if ep['season'] == 'S']
		if special_eps:
			episode = (special_eps[0]['episode'], )
		else:
			return Error('no episode marked')

	elif args:
		arg = args.pop(0)

		m = ep_ptn.search(arg)
		if m:
			args = [ m.group(1) ]
			if m.group(3):
				args.append(m.group(3))

		else:
			args.insert(0, arg)

		if args:
			season_str = args.pop(0)

			try:
				rng = [int(n) for n in season_str.lower().lstrip('s').split('-')]
				if len(rng) == 2:
					season = range(min(rng), max(rng) + 1)
				else:
					if rng[0].upper() == 'S':
						season = 'S'
					else:
						season = (int(rng[0]), )
			except ValueError:
				return Error(f'Bad season number/range: {season}')

		if args:
			episode_str = args.pop(0)

			try:
				rng = [int(n) for n in episode_str.lower().lstrip('e').split('-')]
				if len(rng) == 2:
					episode = range(min(rng), max(rng) + 1)
				else:
					episode = (int(rng[0]), )
			except ValueError:
				return Error(f'Bad episode number/range: {episode}')

		if args:
			return Error('Unexpected extra arguments: %s' % ' '.join(args))

	seen, unseen = series_seen_unseen(series)

	subset = unseen
	already_subset = seen

	if not marking:
		# reverse the subsets for below processing
		subset, already_subset = already_subset, subset

	already = [
		ep
		for ep in already_subset
		if (season is None or ep['season'] in season) and (episode is None or ep['episode'] in episode)
	]
	if already:
		if marking:
			print(f'{_f}Already marked:{_0}')
		else:
			print(f'{_f}Not marked:{_0}')
		for ep in already:
			print(format_episode_title('  ', ep, include_season=True, include_time=False, width=width, gray=True))


	state_before = series_state(series)

	seen_state = meta_get(series, meta_seen_key, {})
	num_marked_before = len(seen_state)

	touched_episodes = []
	episodes_runtime = 0
	now_time = now_stamp()

	for ep in subset:
		if (season is None or ep['season'] in season) and (episode is None or ep['episode'] in episode):
			key = episode_key(ep)

			if marking and key not in seen_state:
				seen_state[key] = now_time
			elif not marking and key in seen_state:
				del seen_state[key]

			touched_episodes.append(ep)
			episodes_runtime += ep.get('runtime') or 0


	if not touched_episodes:
		return Error(f'{_c}No episodes %smarked{_0}' % ('' if marking else 'un'))

	set_dirty()

	if marking:
		print('Marked ', end='')
	else:
		print('Unmarked ', end='')

	print(f'{_c}{len(touched_episodes)}{_00}', end='')
	print(f' episode{plural(touched_episodes)} as seen:  {_0}{_f}{format_duration(episodes_runtime)}{_0}')

	print_series_title(index, series, width, imdb_id=series.get('imdb_id'))

	for ep in touched_episodes:
		msg = msg = f'{"M" if marking else "Unm"}arked episode '
		if ep['season'] == 'S':
			msg += 'SP %d' % ep['episode']
		else:
			msg += 's%de%02d' % (ep['season'], ep['episode'])

		changelog_add(ctx.db, msg, series_id)
		print('  %s' % format_episode_title(None, ep, include_season=True, width=width - 2))


	if not incremental:
		# TODO: detect if a mark gap was created (e.g. marked eps 1, 2 and 4)
		pass

	is_archived = meta_has(series, meta_archived_key)

	state_after = series_state(series)  # will not cover the auto-archive/restore below

	if marking and num_marked_before == 0 and len(series['episodes']) > len(touched_episodes):
		print(f'{_c}First episode{plural(len(touched_episodes))} marked:{_0} {format_state_change(state_before, state_after)}')
	elif not marking and len(seen_state) == 0:
		print(f'{_c}No marked episode left:{_0} {format_state_change(state_before, state_after)}')


	if marking and series.get('status') in ('ended', 'canceled') and not is_archived:
		if len(seen_state) == len(series['episodes']): # all marked
			print()
			print(f'{_c}Last episode marked of an {series["status"]} series:{_0} {format_state_change(state_before, State.ARCHIVED)}')
			ctx.command_arguments = [str(index)]
			return cmd_archive(ctx, width, print_state_change=False)

	elif not marking and is_archived:
		print()
		print(f'{_c}Unmarked episode of archived series:{_0} {format_state_change(state_before, State.STARTED)}')
		ctx.command_arguments = [str(index)]
		return cmd_restore(ctx, width, print_state_change=False)

	ctx.save()

	return None

def _mark_help() -> None:
	print_cmd_usage('mark', '<series> [<season / episode specifier>]')
	print(f'    {_o}<series> [next]             {_0} Next logical episode')
	print(f'    {_o}<series> <season> <episode> {_0} Episodes')
	print(f'    {_o}<series> <season>           {_0} Seasons')
	print(f'    {_o}<series> all                {_0} Whole series')
	print('Also support ranges:')
	print('  > %s mark 42 1 1-5' % PRG)
	print('And episode specifiers (with ranges):')
	print('  > %s mark 42 s1e1-5' % PRG)

setattr(cmd_mark, 'help', _mark_help)


def cmd_unmark(*args, **kwargs) -> Error|None:
	kwargs['marking'] = False
	return cmd_mark(*args, **kwargs)

def _unmark_help() -> None:
	print_cmd_usage('unmark', '<series> [<season / episode specifier>]')
	print(f'    {_o}<series> [last]             {_0} Last marked episode')
	print(f'    {_o}<series> <season> <episode> {_0} Episodes')
	print(f'    {_o}<series> <season>           {_0} Seasons')
	print(f'    {_o}<series> all                {_0} Whole series')
	print('Also support ranges:')
	print('  > %s unmark 42 1 1-5' % PRG)
	print('And episode specifiers (with ranges):')
	print('  > %s unmark 42 s1e1-5' % PRG)

setattr(cmd_unmark, 'help', _unmark_help)


def cmd_archive(ctx:Context, width:int, mode:str|None=None, print_state_change:bool=True) -> Error|None:
	if not ctx.command_arguments:
		return Error('Required argument missing: # / <IMDb ID>')

	find_idx = ctx.command_arguments.pop(0)
	archiving = mode is None or mode == 'archiving'

	index, series_id, err = db.find_single_series(ctx.db, find_idx)
	if series_id is None or err is not None:
		if isinstance(err, list):
			found = err
			# TODO: if more than 4, list the "closest" ones
			message = ', '.join(f'{list_index_style}{idx}{_0} %s' % format_title(ctx.db[sid]) for idx, sid in found[:4])
			return Error(f'Ambiguous ({len(found)}): %s' % message)
		return Error(err)

	series = ctx.db[series_id]

	currently_archived = meta_has(series, meta_archived_key)

	if archiving == currently_archived:
		# TODO: better presentation of title
		if archiving:
			return Error('Already archived: %s' % format_title(series))
		else:
			return Error('Not archived: %s' % format_title(series))


	_do_archive(ctx.db, series_id, width, mode=mode, print_state_change=print_state_change)

	ctx.save()

	return None

def _archive_help() -> None:
	print_cmd_usage('archive', '<series>')
	print(f'    {_o}<series>{_0}')

setattr(cmd_archive, 'help', _archive_help)


def _do_archive(db:dict, series_id:str, width:int, mode:str|None=None, print_state_change:bool=True):
	series = db[series_id]

	state_before = series_state(series)
	seen, unseen = series_seen_unseen(series)
	partly_seen = seen and unseen
	archiving = mode is None or mode == 'archiving'

	if archiving:
		print(f'{_b}Series archived', end='')
		if partly_seen:
			print(' (abandoned)', end='')
		print(f':{_00}')
		meta_set(series, meta_archived_key, now_stamp())
		changelog_add(db, 'Archived series', series_id)

	else:
		print(f'{_b}Series restored', end='')
		if partly_seen:
			print(' (resumed)', end='')
		print(f':{_00}')
		meta_del(series, meta_archived_key)
		changelog_add(db, 'Restored series', series_id)
		refresh_series(db, width, subset=[series_id])

	index = meta_get(series, meta_list_index_key)
	print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width)

	if print_state_change:
		print(format_state_change(state_before, series_state(series)))


def cmd_restore(*args, **kwargs) -> Error|None:
	kwargs['mode'] = 'restore'
	return cmd_archive(*args, **kwargs)

def _restore_help() -> None:
	print_cmd_usage('restore', '<series>')
	print(f'    {_o}<series>{_0}')

setattr(cmd_restore, 'help', _restore_help)


def cmd_refresh(ctx:Context, width:int) -> Error|None:
	forced = bool(ctx.command_options.get('force'))

	find_idx, match = find_idx_or_match(ctx.command_arguments)

	# the user searched for something, they apparently mean it :)
	forced |= bool(find_idx or match)

	# only refresh non-archived series
	series_list = db.indexed_series(ctx.db, state=State.ACTIVE | State.COMPLETED, index=find_idx, match=match)

	if not series_list:
		return Error('Nothing matched')

	subset = [series_id for index, series_id in series_list]

	t0 = time.time()

	num_series, num_episodes = refresh_series(ctx.db, width, subset=subset, force=forced)
	if num_series > 0:  # can be 1 even if num_episodes is zero
		if num_episodes > 0:
			print(f'{_f}Refreshed %d episodes across %d series [%.1fs].{_0}' % (num_episodes, num_series, time.time() - t0), file=sys.stderr)

		ctx.save()

	if not num_series and not num_episodes:
		return Error(f'Nothing to update')

	return None


def _refresh_help() -> None:
	print_cmd_usage('refresh', '[<series>]')
	print(f'    {_o}<series>      {_0} Only the specified series')

setattr(cmd_refresh, 'help', _refresh_help)


def cmd_config(ctx:Context, width:int) -> Error|None:

	if not ctx.command_options and not ctx.command_arguments:
		config.print_current()
		return None

	command:str|None = None
	if ctx.command_arguments:
		command = ctx.command_arguments.pop(0)
		command = resolve_cmd(command)

	if command and not ctx.command_options:
		return Error(f'and...?')

	cmd_args = ctx.command_options.get('command-args')
	if cmd_args is not None:
		if not command:
			return Error(f'{warning_prefix(ctx.command)} "args" only possible for subcommand.')
		defctx = Context(eat_option, resolve_cmd)
		defctx.set_command(command, apply_args=False)
		args_list:list[str] = shlex.split(cmd_args)
		# validate arguments
		defctx.parse_args([*args_list])
		config.set('commands/%s/arguments' % command, args_list)
		print(f'Arguments for {_c}{command}{_0} set: {_b}{" ".join(args_list or [f"{_f}<none>{_0}"])}{_0}')

	default_cmd = ctx.command_options.get('default-command')
	if default_cmd is not None:
		if command:
			return Error(f'{warning_prefix(ctx.command)} bad option "default command" for "{command}".')

		config.set('commands/default', default_cmd)
		print(f'Default command set: {_c}{default_cmd}{_0}')

	default_args = ctx.command_options.get('default-arguments')
	if default_args is not None:
		if command:
			return Error(f'{warning_prefix(ctx.command)} bad option "default args" for "{command}".')
		defctx = Context(eat_option, resolve_cmd)
		cmd = config.get('commands/default')
		defctx.set_command(cmd, apply_args=False)  # type: ignore  # convince mypy 'cmd' is the correct type?
		args_list = shlex.split(default_args)
		# validate arguments
		defctx.parse_args([*args_list])
		# if we got here, the arguments are ok
		config.set('commands/%s/arguments' % cmd, args_list)
		print(f'Default arguments for {_c}{cmd}{_0} set: {_b}{" ".join(args_list or [f"{_f}<none>{_0}"])}{_0}')

	api_key = ctx.command_options.get('api-key')
	if api_key is not None:
		if command:
			return Error(f'{warning_prefix(ctx.command)} bad option "api key" for "{command}".')
		# TODO: "encrypt" ?
		config.set('lookup/api-key', api_key)
		print(f'API key set.')

	return None

def _config_help() -> None:
	print_cmd_usage('config', '[<command>] <options>')

setattr(cmd_config, 'load_db', False)
setattr(cmd_config, 'help', _config_help)


def cmd_undo(ctx:Context, *args, **kw) -> Error|None:
	remaining, message, changes = db.rollback()
	if remaining is None and message:
		return Error(message)

	print(f'{_c}Restored database from backup:{_0} {message}')

	if changes:
		print('These changes were reverted:')
		for message, series_id in changes:
			print(f'  - {_i}{_o}{message}', end='')
			if series_id:
				series = ctx.db[series_id]
				print(f'{_0}; {format_title(series)}')
			else:
				print(_0)

		print()

	print(f'Remaining backups: {remaining}')

def _undo_help() -> None:
	print_cmd_usage('undo')

setattr(cmd_undo, 'help', _undo_help)


def cmd_rate(ctx:Context, *args, **kw) -> Error|None:
	if len(ctx.command_arguments) < 2:
		return Error('Required arguments missing')

	index, series_id, err = db.find_single_series(ctx.db, ctx.command_arguments.pop(0))
	if series_id is None or err is not None:
		if isinstance(err, list):
			found = err
			# TODO: if more than 4, list the "closest" ones
			message = ', '.join(f'{list_index_style}{idx}{_0} %s' % format_title(ctx.db[sid]) for idx, sid in found[:4])
			return Error(f'Ambiguous ({len(found)}): %s' % message)
		return Error(err)

	series = ctx.db[series_id]
	if not meta_get(series, meta_archived_key):
		return Error('only archived series may be rated')

	rating = ctx.command_arguments.pop(0)
	try:
		rating = int(rating)
	except ValueError as ve:
		return Error(f'invalid rating: {ve}')

	meta_set(series, meta_rating_key, rating)
	changelog_add(ctx.db, 'Rated series', series_id)

	print(f'Rated {format_title(series)}: {_b}{rating}{_0}')

	comment = ctx.option('comment')
	if comment:
		meta_set(series, meta_rating_comment_key, comment)
		print(f'{_b}Comment:{_0} {comment}')
	else:
		comment = meta_get(series, meta_rating_comment_key)
		if comment:
			print(f'{_b}Existing comment:{_0} {comment}')

	ctx.save()

def _rate_help() -> None:
	print_cmd_usage('rate', '<series> <rating>')
	print(f'    {_o}<series>     {_0} Rate specified series')
	print(f'    {_o}<rating>     {_0} Number, 0 - 10')

setattr(cmd_rate, 'help', _rate_help)



def cmd_help(ctx:Context, *args, **kw) -> Error|None:
	if ctx.command_arguments:
		arg = ctx.command_arguments.pop(0)
		if arg in ('env', 'environment'):
			return print_env_help()

	return print_usage()


def _help_help() -> None:
	print_cmd_usage('help', '[<topic>]')
	print('Topics:')
	print(f'    {_o}env          {_0} Environment variables')
	print(f'    (none)    ▶   General usage')

setattr(cmd_help, 'help', _help_help)


# known commands with aliases
known_commands:dict[str,dict[str,tuple|Callable|str]] = {
	'search':  {
		'alias': ('s', ),
		'handler': cmd_search,
		'help': 'Search for a series.',
	},
 	'add': {
	    'alias': ('a', ),
	    'handler': cmd_add,
	    'help': 'Search for a series and (optionally) add it.',
    },
 	'delete': {   # shorthand for a destructive operation seems reckless
	    'alias': (),
	    'handler': cmd_delete,
	    'help': 'Remove a series from %s - permanently!' % PRG,
    },
 	'show': {
	    'alias': ('list', 'ls'),
	    'handler': cmd_show,
	    'help': 'Show/list series with optional details.',
    },
	'calendar': {
		'alias': ('c',),
		'handler': cmd_calendar,
		'help': 'Show episode releases by date.',
	},
	'info': {
		'alias': ('i',),
		'handler': cmd_info,
		'help': 'Show details series information.'
	},
	'unseen': {
		'alias': ('u', 'us'),
		'handler': cmd_unseen,
		'help': 'Show unseen episodes of series.',
	},
	'mark': {
		'alias': ('m', ),
		'handler': cmd_mark,
		'help': 'Mark as seen, a series, season or episode(s).',
	},
	'unmark': {
		'alias': ('M', 'um'),
		'handler': cmd_unmark,
		'help': f'Unmark a series/season/episode - reverse of {_c}mark{_0}.',
	},
	'archive': {
		'alias': ('A', ),
		'handler': cmd_archive,
		'help': 'Archving series - hides from default `list` and not refreshed.',
	},
	'rate': {
		'alias': ('comment', ),
		'handler': cmd_rate,
		'help': 'Rate archived series, with optional comment.',
	},
	'restore': {
		'alias': ('R', ),
		'handler': cmd_restore,
		'help': 'Restore an archived series - reverse of `archive`.',
	},
	'refresh': {
		'alias': ('r', ),
		'handler': cmd_refresh,
		'help': 'Refresh information of non-archived series (all or subset).',
	},
	'config': {
		'alias': (),
		'handler': cmd_config,
		'help': 'Configure aspects of %s, e.g. defaults.' % PRG,
	},
	'undo': {
		'alias': (),
		'handler': cmd_undo,
		'help': 'Undo last change.'
	},
	'help': {
		'alias': (),
		'handler': cmd_help,
		'help': 'Shows this help page.',
	},
}


def _opt_list(sep:str, valid:list[str]) -> Callable[[str, str, dict], str|None]:
	def _set(value:str, key:str, options:dict) -> str|None:
		values = options.get(key, [])
		adding_values = value.split(sep)
		if valid:
			for v in adding_values:
				if v not in valid:
					return ', '.join(valid)
		values.extend(adding_values)
		options[key] = values
		return None

	return _set


def _set_fake_date(value:date, key:str, options:dict) -> str|None:
	utils.fake_now(value)


def _disable_refresh(value:date, key:str, options:dict) -> str|None:
	config.set('refresh-enabled', False, store=Store.Memory)

def _valid_int(a:int, b:int) -> Callable[[int], int|None]:
	assert(a <= b)
	def verify(v:int) -> int|None:
		if v >= a and v <= b:
			return v
		return None
	verify.__doc__ = 'between %d and %d' % (a, b)
	return verify

def _valid_cmd(name:str) -> str|None:
	'valid command name'
	return resolve_cmd(name, fail_ok=True)

__opt_max_hits = {
	'max-hits': {
		'name': '-n',
		'arg': int,
		'validator': _valid_int(1, 40),
		'help': 'Limit number of hits [1-40] (default: %d)' % config.get_int('max-hits'),
	}
}

_opt_sort_names = _opt_list(',', ['title', 'year', 'earliest', 'latest', 'added', 'archived'])  # TODO: e.g. "earliest"

__opt_series_sorting = {
	'sorting': {
		'name': '--sort',
		'arg': str,
		'help': 'Sort series',
		'func': _opt_sort_names
	},
}

# TODO: merge with 'known_commands' ?  (at least for the command-specific options)

command_options = {
	None: { # i.e. global options
		'fake-now':          { 'name': '--fake-now', 'arg': date, 'help': 'Simulate a specific "today" date', 'func': _set_fake_date },
		'no-refresh':        { 'name': '--no-refresh',            'help': 'Don\'t refresh any series data', 'func': _disable_refresh },
	},
	'show': {
		'all':               { 'name': ('-a', '--all'),          'help': 'List also archived series' },
		'archived':          { 'name': ('-A', '--archived'),     'help': 'List only archived series' },
		'started':           { 'name': ('-s', '--started'),      'help': 'List only series with seen episodes' },
		'planned':           { 'name': ('-p', '--planned'),      'help': 'List only series without seen episodes' },
		'abandoned':         { 'name': '--abandoned',            'help': 'List only abandoned series' },
		'with-unseen':       { 'name': ('-u', '--unseen'),       'help': 'List only series with unseen episodes' },
		**__opt_series_sorting,

		'all-episodes':      { 'name': ('-e', '--episodes'),     'help': 'Show all unseen (released) episodes' },
		'future-episodes':   { 'name': ('-f', '--future'),       'help': 'Also show future episodes' },
		'seen-episodes':     { 'name': ('-S', '--seen'),         'help': 'Show seen episodes' },
		'next-episode':      { 'name': ('-N', '--next'),         'help': 'Show only next episode, no summary' },
		'no-seen-summary':   { 'name': '--no-summary',           'help': "Don't show seen summary" },

		'details':           { 'name': ('-I', '--details'),      'help': 'Show more details' },
		'terse':             { 'name': '-T',                     'help': 'Show less details' },

		'director':          { 'name': '--director', 'arg': str, 'help': 'Filter by director, substring match' },
		'writer':            { 'name': '--writer',  'arg': str,  'help': 'Filter by writer, substring match' },
		'cast':              { 'name': '--cast',    'arg': str,  'help': 'Filter by cast, substring match' },
		'year':              { 'name': '--year',    'arg': str,  'help': 'Filter by year, <start>[-<end>]' },
		'country':           { 'name': '--country', 'arg': str,  'help': 'Filter by country (two letters; ISO 3166)' },
	},
	'unseen': {
		'started':           { 'name': ('-s', '--started'),      'help': 'List only series with seen episodes' },
		'planned':           { 'name': ('-p', '--planned'),      'help': 'List only series without seen episodes' },
		'all-episodes':      { 'name': ('-e', '--episodes'),     'help': 'Show all unseen episodes (not only first)' },
		'future-episodes':   { 'name': ('-f', '--future'),       'help': 'Also shows (series with) future episodes' },
		**__opt_series_sorting,  # type: ignore  # not sure how to convince mypy here
	},
	'refresh': {
		'force':             { 'name': ('-f', '--force'),        'help': 'Refresh whether needed or not' },
	},
	'rate': {
		'comment':           { 'name': ('-c', '--comment'), 'arg': str, 'help': 'Add comment to rating' },
	},
	'add': {
		'comment':           { 'name': ('-c', '--comment'), 'arg': str, 'help': 'Set comment when adding series' },
		**__opt_max_hits,
	},
	'search': {
		**__opt_max_hits,
	},
	'config': {
		'command-args':      { 'name': '--args', 'arg': str,    'help': 'Set default arguments for <command>' },
		'default-command':   { 'name': '--default', 'arg': str, 'validator': _valid_cmd, 'help': 'Set command to run by default' },
		'default-arguments': { 'name': '--default-args', 'arg': str, 'help': 'Set arguments for the default command' },
		'api-key':           { 'name': '--api-key', 'arg': str, 'help': 'Set API key for backend (TMDb)' },
	},
}



def is_released(target, fallback=True):
	release_date = target.get('date')
	if release_date is None:
		return fallback

	# already released or will be today
	return date.fromisoformat(release_date) <= today_date


def format_state_change(before:State, after:State) -> str:
	return f'[\x1b[38;5;202m{before.name.lower()}{_0} ⯈ \x1b[38;5;112m{after.name.lower()}{_0}]'  # type: ignore  # todo: enum


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
				print(f'{_c}%{indent}s{_0}\r' % (f's%d' % season), end='')
			current_season = season

		s = format_episode_title(None, ep, width=ep_width, today=True, seen=has_seen)

		# moving cursor instead of writing spaces so we don't overwrite the season label
		print(f'\x1b[{indent + margin}C{s}')

		keys.append(episode_key(ep))

		if not (also_future or is_released(ep)):
			stop_at_date_after = ep.get('date')


	return keys


def find_idx_or_match(args, country:re.Pattern|None=None, director:re.Pattern|None=None, writer:re.Pattern|None=None, cast:re.Pattern|None=None, year:list[int]|None=None) -> tuple[int|None, Callable|None]:

	# print('FILTER title/idx:', (_c + ' '.join(args) + _0fg) if args else 'NONE')
	# print('          country:', (_c + country.pattern + _0fg) if country else 'NONE')
	# print('        director:', (_c + director.pattern + _0fg) if director else 'NONE')
	# print('          writer:', (_c + writer.pattern + _0fg) if writer else 'NONE')
	# print('            cast:', (_c + cast.pattern + _0fg) if cast else 'NONE')
	# print('            year:', (_c + '-'.join(year) + _0fg) if year else 'NONE')


	if not args and country is None and director is None and writer is None and cast is None and year is None:
		return None, None

	try:
		if not args:
			raise ValueError()

		find_idx = int(args[0])
		# we're looking for a single entry, by index: other arguments are ignored
		return find_idx, None

	except ValueError:
		title = None
		imdb_id = None

		if args:
			if len(args) == 1 and re.search('^tt[0-9]{7,}$', args[0]):
				imdb_id = args[0]
			else:
				title = re.compile('.*?'.join(re.escape(a) for a in ' '.join(args).split()), re.IGNORECASE)

		# print('FILTER     title:', (_c + title.pattern + _0) if title else 'NONE')
		# print('         IMDb ID:', (_c + imdb_id + _0) if imdb_id else 'NONE')
		# print('         country:', (_c + country.pattern + _0) if country else 'NONE')
		# print('        director:', (_c + director.pattern + _0) if director else 'NONE')
		# print('          writer:', (_c + writer.pattern + _0) if writer else 'NONE')
		# print('            cast:', (_c + cast.pattern + _0) if cast else 'NONE')
		# print('            year:', (_c + '-'.join(year) + _0) if year else 'NONE')

		# TODO: function should also take list index: (list_index, series) -> bool

		def match(series):
			ok = True

			if ok and title:
				ok = title.search(series['title']) is not None
			if ok and imdb_id:
				ok = imdb_id == series.get('imdb_id')
			if ok and country:
				ok = country.search(series.get('country', '')) is not None
			if ok and director:
				ok = _match_names(series, 'director', director)
			if ok and writer:
				ok = _match_names(series, 'writer', writer)
			if ok and cast:
				ok = _match_names(series, 'cast', cast)
			if ok and year:
				ok = _match_years(series, year)

			# if ok:
			# 	print(f'    match {_g}%s{_0}' % series['title'])
			# else:
			# 	print(f'    match {_f}%s{_0}' % series['title'])

			return ok

		filter_parts = {
			'title': title.pattern if title else None,
			'country': country.pattern if country else None,
			'director': director.pattern if director else None,
			'writer': writer.pattern if writer else None,
			'cast': cast.pattern if cast else None,
			'year': '-'.join(str(y) for y in year) if year else None,
		}
		setattr(match, 'description', ' '.join('%s=%s' % (n, v) for n, v in filter_parts.items() if v))
		setattr(match, 'styled_description', _c + ' '.join(f'%s{_g}={_0}{_b}%s{_0}' % (n, v) for n, v in filter_parts.items() if v))

		return None, match


def _substr_re(s:str):
	return re.compile('.*?' + re.escape(s.replace(' ', '.*?')) + '.*', re.IGNORECASE)


def _match_names(series:dict, attribute:str, pattern:re.Pattern):
	# print('match %s of "%s": %s' % (attribute, series['title'], pattern.pattern))
	for name in series.get(attribute, []):
		# print(' ?', name)
		if pattern.search(name):
			# print(' !')
			return True

	return False


def _match_years(series:dict, years:list[int]):
	s_year = series.get('year')
	if not s_year:
		# print(' "%s" no year' % series['title'])
		return False

	if len(s_year) == 1 and len(years) == 1:
		res = years[0] == s_year[0]
		# print(' "%s" %s == %s -> %s' % (series['title'], s_year[0], years[0], res))
		return res

	if len(years) == 1:
		res = years[0] in range(s_year[0], s_year[1] + 1)
		# print(' "%s" %s in %s-%s -> %s' % (series['title'], years[0], s_year[0], s_year[1], res))
		return res

	if len(s_year) == 1:
		res = s_year[0] in range(years[0], years[1] + 1)
		# print(' "%s" %s in %s-%s -> %s' % (series['title'], s_year[0], years[0], years[1], res))
		return res

	overlap = range(max(years[0], s_year[0]), min(years[1], s_year[1]) + 1)
	# print(' "%s" %s-%s overlaps %s-%s -> %s' % (series['title'], s_year[0], s_year[1], years[0], years[1], bool(overlap)))
	return bool(overlap)



def episodes_by_key(series:dict, keys:list) -> list:
	keys_to_index:dict[str, int] = {}
	episodes:list[dict] = series.get('episodes', [])
	for idx, ep in enumerate(episodes):
		keys_to_index[episode_key(ep)] = idx

	return [
		episodes[keys_to_index[key]]
		for key in keys
	]


def no_series(db:dict, filtered:bool=False) -> Error:

	if len(db) <= 1:
		return Error(f'No series added.  Use: {_b}%s add <title search...> [<year>]{_0}' % PRG)

	precision = ' matched (try -a)' if filtered else ''
	return Error('No series%s.' % precision)



def last_update(series:dict) -> datetime:
	updates = meta_get(series, meta_update_history_key)
	if updates:
		return datetime.fromisoformat(updates[-1])

	return now_datetime()


def refresh_series(db:dict, width:int, subset:list|None=None, force:bool=False, affected:dict|None=None) -> tuple[int, int]:
	if not config.get_bool('refresh-enabled', True):
		return 0, 0

	subset = subset or m_db.all_ids(db)

	if force:
		to_refresh = subset
	else:
		def check_expired(_, series:dict) -> bool:
			return m_db.should_update(series)
		to_refresh = list(m_db.filter_map(db, filter=check_expired, map=lambda sid, _: sid))

	to_refresh = list(sorted(to_refresh, key=int))

	# print('force:', force)
	# print('to_refresh:', len(to_refresh), '|', ' '.join(to_refresh))

	if not to_refresh:
		return 0, 0

	# set time of last check (regardless whether there actually were any updates)
	touched = 0
	for series_id in to_refresh:
		meta_set(db[series_id], meta_update_check_key, now_stamp())
		touched += 1

	def mk_prog(total):
		return progress.new(total, width=width - 2, bg_color=rgb('#404040'), bar_color=rgb('#686868'), text_color=rgb('#cccccc'))

	latest_update_time:datetime|None = None

	if not force:
		# check with TMDb if there actually are any updates
		prog_bar = mk_prog(len(to_refresh))
		clrline()
		# print('get changes:', len(to_refresh), '|', ' '.join(to_refresh))
		print(f'%s{_EOL}' % prog_bar('Checking %d series for updates...' % len(to_refresh)), end='', flush=True)

		def show_ch_progress(completed:int, *_) -> None:
			print(f'\r{_K}%s{_EOL}' % prog_bar(completed, text='Checking updates...'), end='', flush=True)

		oldest_refresh = min(
			last_update(db[sid])
			for sid in to_refresh
		)

		debug('changes since:', oldest_refresh)

		changes = tmdb.changes(to_refresh, oldest_refresh, include=include_changes, progress=show_ch_progress)

		clrline()

		for series_id, changes in zip(list(to_refresh), changes):
			series = db[series_id]
			debug(series_id, series['title'], 'changes:')
			for ch in changes:
				items = ch['items']
				debug('  %s (%d items)' % (ch['key'], len(ch['items'])))

			if not changes:
				to_refresh.remove(series_id)
			else:
				for chg in changes:
					items = chg.get('items', [])
					for item in items:
						chtime = item.get('time')
						if chtime:
							chtime = datetime.strptime(chtime, '%Y-%m-%d %H:%M:%S %Z')
							if latest_update_time is None or chtime < latest_update_time:
								latest_update_time = chtime



		if not to_refresh:
			# print('No updates')
			# sys.exit(42)
			if touched:
				return touched, 0  # only series affected, no episodes

			return 0, 0

	if latest_update_time is None:
		latest_update_time_str = now_stamp()
	else:
		debug('extracted latest update time:', latest_update_time)
		latest_update_time_str = latest_update_time.isoformat(' ')


	# print('with changes:', len(to_refresh), '|', ' '.join(to_refresh))
	# sys.exit(42)

	# remember each series status
	previous_status = {
		series_id: db[series_id].get('status')
		for series_id in to_refresh
	}


	prog_bar = mk_prog(len(to_refresh))
	clrline()
	print(f'%s{_EOL}' % prog_bar(f'Refreshing %d series...' % len(to_refresh)), end='', flush=True)
	# TODO: show 'spinner'

	def show_up_progress(completed:int, *_) -> None:
		clrline()
		print(f'%s{_EOL}' % prog_bar(completed, text='Refreshing...'), end='', flush=True)

	result = tmdb.episodes(to_refresh, with_details=True, progress=show_up_progress)

	clrline()

	num_episodes = 0
	max_history = config.get_int('num-update-history')

	for series_id, (details, episodes) in zip(to_refresh, result):

		changelog_add(db, 'Refreshed', series_id)

		series = details
		series['episodes'] = episodes
		meta_copy(db[series_id], series)

		# keep a list of last N updates
		update_history = meta_get(series, meta_update_history_key, [])
		update_history.append(latest_update_time_str)
		if len(update_history) > max_history:
			update_history.pop(0)
		meta_set(series, meta_update_history_key, update_history)

		# replace entry in DB
		db[series_id] = series

		if series_state(series) & State.ARCHIVED == 0:
			if previous_status[series_id] != 'ended' and series.get('status') == 'ended':
				# status changed to 'ended', have we seen all episodes?
				if len(series.get('episodes', [])) == len(meta_get(series, meta_seen_key, [])):
					# allright then, we have no further business with this series
					_do_archive(db, series_id, width=width)
					if affected is not None:
						affected[series_id] = State.ARCHIVED

		num_episodes += len(episodes)


	return len(to_refresh), num_episodes

list_index_style = '\x1b[3;38;2;200;160;100m'

def print_series_title(num:int|None, series:dict, width:int=0, imdb_id:str|None=None, gray:bool=False, tail: str|None=None, tail_style:str|None=None) -> None:

	# this function should never touch the BG color

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



def format_episode_title(prefix:str|None, episode:dict, include_season:bool=False, include_time:bool=True, width:int=0, gray:bool=False, seen:bool|None=None, today:bool=False) -> str:

	# this function should never touch the BG color

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
		time_style = _b

		if diff > 24*3600:  # longer than 24 hours
			ep_time = format_duration(diff, roughly=True)
			time_style = '\x1b[38;5;244m'

	elif today:
		ep_time = f'TODAY'
		time_style = _g

	elif isinstance(ep_date, str):
		ep_time = f'{ep_date}'
		#ep_time = ''
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

	s = ''
	if prefix and prefix is not None:
		s += f'{prefix}'
		width -= len(prefix)

	# not enough space: truncate & ellipt
	if len(ep['title']) > width:
		width -= 1
		ep['title'] = ep['title'][:width] + '…'
		# TODO: to fancy fade to black at the end ;)

	s += f'{season_ep:}{" "*episode_title_margin}{_o}{ep["title"]:{width}}{_f}{runtime_str}{_0}{ep_time}'

	if gray or seen:
		s = f'{_0}\x1b[38;5;246m%s{_0}' % strip_ansi(s)

	return s


def print_series_details(index:int, series:dict, width:int, gray:bool=False) -> None:

	tail = None
	if series.get('imdb_id'):
		tail = f'    {_o}{_u}%s{_0}' % (imdb_url_tmpl % series["imdb_id"])
	print_series_title(index, series, width, gray=gray, tail=tail)

	print_archive_status(series)

	overview = textwrap.wrap(series['overview'], width=width, initial_indent=' '*15)
	print(f'    {_o}Overview:{_0}  {_i}{_c}', end='')
	overview[0] = overview[0][15:]
	print('\n'.join(overview))
	print(_0, end='')

	# collect top-N writers and directors, and guest cast
	from collections import Counter
	episodes = series.get('episodes', [])
	all_writers = []
	all_directors = []
	all_guests = []

	for ep in episodes:
		all_writers.extend(ep.get('writer', []))
		all_directors.extend(ep.get('director', []))
		all_guests.extend(ep.get('guest_cast', []))

	writers_c = Counter(all_writers)
	writers = [name for name, _ in writers_c.most_common(5)]
	directors_c = Counter(all_directors)
	directors = [name for name, _ in directors_c.most_common(5)]
	guests_c = Counter(all_guests)
	guests = [name for name, _ in guests_c.most_common(10)]

	if directors:
		print(f'    {_o}Directors:{_0}', f'{_o},{_0} '.join(directors))
	if writers:
		print(f'    {_o}Writers:{_0}  ', f'{_o},{_0} '.join(writers))
	if series.get('cast'):
		print(f'    {_o}Cast:{_0}     ', f'{_o},{_0} '.join(series['cast']))
	if guests:
		print(f'    {_o}Guests:   {_0}', f'{_o},{_0} '.join(guests))

	if episodes:
		num_specials = len(list(filter(lambda ep: ep.get('season') == 'S', episodes)))
		num_seasons = max(ep.get('season', 0) if type(ep.get('season')) is int else 0 for ep in episodes)
		print(f'    {_o}Seasons: {_0}', num_seasons, end='')
		print(f'  {_f}/{_0}  {_o}Episodes: {_0}', len(episodes) - num_specials, end='')
		if num_specials:
			print(f'  {_f}/{_0}  {_o}Specials: {_0}', num_specials, end='')
		print()
		for season in range(1, num_seasons + 1):
			print(f'     {_c}{"s%d" % season:>3}{_0}', '%3d' % len(list(filter(lambda ep: ep.get('season') == season, episodes))), 'episodes')
	else:
		print(f'       {_c}{_i}no episodes{_0}')

	print(f'    {_o}Added:{_0}', meta_get(series, meta_added_key), end='')
	if meta_get(series, meta_add_comment_key):
		add_comment = meta_get(series, meta_add_comment_key)
		print(f'  {_g}{_i}"{add_comment}"{_0}')
	else:
		print()

	if meta_get(series, meta_archived_key):
		rating = meta_get(series, meta_rating_key)
		comment = meta_get(series, meta_rating_comment_key)
		if rating is not None:
			print(f'    {_o}Rating:{_0}  {_i}{_c}{rating}{_0}', end='')
		if comment:
			print(f'  "{_i}{comment}{_0}"')
		else:
			print()


def print_archive_status(series:dict) -> None:
	if meta_has(series, meta_archived_key):
		print(f'{_f}       Archived', end='')
		seen, unseen = series_seen_unseen(series)
		if seen and unseen:  # some has been seen, but not all
			print(' / Abandoned', end='')
		print('  ', meta_get(series, meta_archived_key).split()[0], end='')
		print(f'{_0}')


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




def strip_ansi(s: str):
	return re.sub('\x1b\\[[0-9;]*[mJ]', '', s)


def print_seen_status(series:dict, gray: bool=False, summary=True, next=True, last=True, width:int=0):
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
		s = format_episode_title('', unseen[0], gray=gray, include_season=True, today=True, width=width - len(header))
		if s:
			if gray:
				print(_f, end='')
			print(f'{header}{s}')


def option_def(command:str|None, option:str|None=None):
	cmd_opts = command_options.get(command)

	if not isinstance(cmd_opts, dict) or not cmd_opts:
		return None

	if option is None:
		return cmd_opts

	for key, opt in cmd_opts.items():
		if option in opt['name']:
			return { 'key': key, **opt }

	return None


def print_cmd_usage(command:str, syntax:str='') -> None:
	entry = known_commands[command]
	summary = entry.get('help')
	if summary:
		print(f'{_b}{summary}{_0}')
	aliases = entry.get('alias')
	if aliases:
		print(f'{_b}Alias:{_0} %s' % ', '.join(aliases))
	print(f'{_b}Usage:{_0} %s {_c}%s{_0} %s' % (PRG, command, syntax))


def print_cmd_option_help(command:str|None, print_label:bool=True) -> None:
	options = option_def(command)
	if options:
		if print_label:
			print(f'{_b}Options:{_0}')

		options = {
			name: opts
			for name, opts in options.items()
			if opts.get('hidden') != True
		}

		for opt in options.values():
			option = opt.get('name')
			if type(option) is tuple:
				option = ', '.join(option)

			arg_type = opt.get('arg')
			if arg_type is not None:
				arg_string = arg_placeholder(option, arg_type)
				option = '%s %s' % (option, arg_string)

			text = opt.get('help', '')
			print('   %-22s %s' % (option, text))


def arg_placeholder(option, arg_type):
	if arg_type is str:
		return 'string'
	if arg_type is int:
		return 'N'
	if arg_type is float:
		return 'F'
	if arg_type is date:
		return 'YYYY-MM-DD'

	raise RuntimeError(f'{option} argument placeholder type can not be %s' % arg_type.__name__)


def print_cmd_help_table():

	def hilite_alias(cmd, aliases) -> str:
		highlighted = ''
		for idx, ch in enumerate(cmd):
			matched = filter(lambda a: a.lower() == ch.lower(), aliases)
			try:
				highlighted += f'{_c}{next(matched)}{_0}' + cmd[idx + 1:]
				break
			except StopIteration:
				pass
			highlighted += ch

		return highlighted

	for cmd, cmd_info in known_commands.items():
		aliases = cmd_info['alias']
		summary = cmd_info['help']
		pad = ' '*(12 - len(cmd))
		cmd = hilite_alias(cmd, aliases)
		print(f'  {cmd}{pad}{summary}')


def print_usage(exit_code:int=0) -> None:
	default_command = config.get('commands/default')

	print(f'{_b}%s{_0} / {_b}Ep{_0}isode {_b}M{_0}anager / (c)2022 André Jonsson' % PRG)
	print('Version %s (%s) ' % (VERSION, VERSION_DATE))
	print(f'{_b}Usage:{_0} %s [<global options>] [<{_b}command{_0}>] [{_o}<args ...>{_0}]' % PRG)
	print()
	print(f'Where {_b}<global options>{_0} are:')
	print_cmd_option_help(None, print_label=False)
	print()
	print(f'Where {_b}<command>{_0} is:  {_f}(one-letter alias highlighted){_0}')
	print_cmd_help_table()
	print(f'  (none)  ▶  {_b}%s{_0}' % default_command)
	print()
	print(f'See: %s {_b}<command> --help{_0} for command-specific help.' % PRG)
	print()
	print('Remarks:')
	print(f'  # = Series listing number, e.g. as listed by the {_b}l{_0}ist command.')
	print(f'  If an argument does not match a command, it will be used as argument to the default command.')
	print(f'  Shortest unique prefix of a command is enough, e.g. "ar"  for "archive".')
	if utils.json_serializer() != 'json':
		print(f'  {_f}Using {_b}{utils.json_serializer()}{_0}{_f} for faster load/save.')
	else:
		print(f'  {_f}Install \'orjson\' for faster load/save{_0}')
	if db.compressor():
		print(f'  {_f}Using {_b}{db.compressor()}{_0}{_f} to compress database backups.')
	if not tmdb.ok():
		print(f'   {_c}NOTE: Need to set TMDb API key (TMDB_API_KEY environment){_0}')
	sys.exit(exit_code)


def print_env_help() -> None:
	print('Some defaults may be overriden by environment variables:')
	print(f'  {_b}{config.env_config_path:20}{_0} Path to configuration file')
	print(f'  {_b}{config.env_series_db_path:20}{_0} Path to series database file')


def print_cmd_help(command:str, exit_code:int=0) -> None:
	try:
		show_help = getattr(known_commands[command]['handler'], 'help')
	except KeyError:
		print('%s: No help for command: %s' % (PRG, command))
		sys.exit(1)

	show_help()
	print_cmd_aliases(command)
	print_cmd_option_help(command)

	sys.exit(exit_code)


def print_cmd_aliases(command:str) -> None:
	for cmd in known_commands:
		if cmd[0] == command and len(cmd) > 1:
			print(f'{_b}Aliases:{_0} %s' % ', '.join(cmd[1:]))
			return


def rgb(*args):
	if len(args) == 3 and isinstance(args[0], int) and isinstance(args[1], int) and isinstance(args[2], int):
		r, g, b = args

	elif len(args) == 1 and isinstance(args[0], str):
		c_hex = args[0]
		if c_hex[0] == '#':
			c_hex = c_hex[1:]
		assert len(c_hex) == 6, 'length of hex color string is not 6'
		r = int(c_hex[:2], 16)
		g = int(c_hex[2:4], 16)
		b = int(c_hex[4:6], 16)

	return f'8;2;{r};{g};{b}'


# https://github.com/sindresorhus/cli-spinners/blob/main/spinners.json
spinner_frames = [
	"⢀⠀",
	"⡀⠀",
	"⠄⠀",
	"⢂⠀",
	"⡂⠀",
	"⠅⠀",
	"⢃⠀",
	"⡃⠀",
	"⠍⠀",
	"⢋⠀",
	"⡋⠀",
	"⠍⠁",
	"⢋⠁",
	"⡋⠁",
	"⠍⠉",
	"⠋⠉",
	"⠋⠉",
	"⠉⠙",
	"⠉⠙",
	"⠉⠩",
	"⠈⢙",
	"⠈⡙",
	"⢈⠩",
	"⡀⢙",
	"⠄⡙",
	"⢂⠩",
	"⡂⢘",
	"⠅⡘",
	"⢃⠨",
	"⡃⢐",
	"⠍⡐",
	"⢋⠠",
	"⡋⢀",
	"⠍⡁",
	"⢋⠁",
	"⡋⠁",
	"⠍⠉",
	"⠋⠉",
	"⠋⠉",
	"⠉⠙",
	"⠉⠙",
	"⠉⠩",
	"⠈⢙",
	"⠈⡙",
	"⠈⠩",
	"⠀⢙",
	"⠀⡙",
	"⠀⠩",
	"⠀⢘",
	"⠀⡘",
	"⠀⠨",
	"⠀⢐",
	"⠀⡐",
	"⠀⠠",
	"⠀⢀",
	"⠀⡀"
]

imdb_url_tmpl = 'https://www.imdb.com/title/%s'

today_date = date.today()

ignore_changes = (
	'name',   # the name we want, in all likelyhood, already exists.
	'images',
	'videos',
	'production_companies',
	'season_regular',
	'crew',
	'tagline',
	'homepage',
	'user_review_count',
	'translations',
	'languages',
)
include_changes = (
	'season',
	#'overview',
)
# TODO: also ignore changes that are not in a language we're interested in (e.g. english)

def main():
	try:
		start()

	except tmdb.NoAPIKey:
		clrline()
		print(f'{_E}ERROR{_00} No TMDb API key.', file=sys.stderr)
		print(tmdb.api_key_help)
		print('OR: epm config --api-key <key>')
		sys.exit(0)

	except tmdb.APIAuthError:
		clrline()
		print(f'{_E}ERROR{_00} TMDb API key is not valid.', file=sys.stderr)
		print(tmdb.api_key_help)
		print('OR: epm config --api-key <key>')
		sys.exit(1)

	except tmdb.NetworkError as ne:
		clrline()
		print(f'{_E}ERROR{_00} TMDb API network error: {ne}')
		print('Please check internet connection and try again later.')
		sys.exit(1)

	except utils.FatalJSONError:
		sys.exit(1)

	except KeyboardInterrupt:
		print('** User beak', file=sys.stderr)
		sys.exit(1)

if __name__ == '__main__':
	main()
