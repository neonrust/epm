#! /usr/bin/env python3

import re
import sys
import shlex
import time
import atexit
import string
from datetime import datetime, date, timedelta
from os.path import basename
from calendar import Calendar, day_name, month_name, MONDAY, SUNDAY
import textwrap

from typing import Callable, Any, Pattern
from . import tmdb, progress, config, utils, db
m_db = db
from .db import Database
from .context import Context, BadUsageError
from .config import Store, debug
from .styles import _0, _00, _0B, _B, _c, _i, _b, _f, _fi, _K, _E, _o, _g, _u, _EOL
from .display import \
    print_series_title, \
	print_episodes, \
	print_archive_status, \
	print_seen_status, \
	list_index_style, \
	format_title, \
	format_episode_title, \
	format_duration, \
	format_state, \
	format_state_change, \
	format_year_range, \
	format_tag, \
	clrline, \
	menu_select, \
	user_confirm, \
	set_bg_color
from .utils import \
    term_size, \
	warning_prefix, \
	plural, \
	now_datetime, \
	now_stamp
from .db import \
    State, \
	set_dirty, \
	meta_set, \
	meta_del, \
	meta_seen_key, \
	meta_tags_key, \
	meta_archived_key, \
	meta_added_key, \
	meta_total_episodes_key, \
	meta_next_episode_key, \
	meta_last_episode_key, \
	meta_active_status_key, \
	meta_update_check_key, \
	meta_update_history_key, \
	meta_rating_key, \
	meta_rating_comment_key, \
	meta_list_index_key, \
	meta_add_comment_key,\
	changelog_add, \
	series_state, \
	series_num_seen_unseen, \
	series_seen_unseen, \
	episode_key, \
	next_unseen_episode, \
	last_seen_episode

PRG = basename(sys.argv[0])

VERSION = '0.24'
VERSION_DATE = '2024-09-26'


def start():
	config.load()
	# print(orjson.dumps(app_config, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode('utf-8'))
	atexit.register(config.save)

	api_key = config.get('lookup/api-key') or tmdb.key_from_env()
	if isinstance(api_key, str):
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

	if not arg_type:
		# no argument expected
		if option_arg:
			# but an argument was supplied
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

		# ---------------------------------------------------------------------------
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
	# ---------------------------------------------------------------------------

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
	filter_tags = ctx.option('tags')

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
	if filter_tags:
		tags = []
		for tag in filter_tags.split(','):
			tag_def = config.tag(tag)
			if isinstance(tag_def, dict):
				tag = tag_def['name']
				tags.append(tag)
			else:
				print(f'Unknown tag {_o}{tag}{_0} (ignored)')
		filter_tags = tags

	sort_key:Callable[[tuple[str,dict]],Any]|None = None

	sorting = ctx.command_options.get('sorting', [])
	if sorting:
		def _series_key(meta:dict, key:str) -> str:
			# possible values are checked by _opt_sort_names
			if key == 'earliest':
				next_ep = meta.get(meta_next_episode_key)
				if not next_ep:
					return '\xff'
				return next_ep.get('date') or ''

			elif key == 'latest':
				last_ep = meta.get(meta_last_episode_key)
				if not last_ep:
					return '\xff'
				return last_ep['seen']

			elif series and key in series:  # possible values are checked by _opt_sort_names
			    return str(series[key])
			else:
				# possible values are checked by _opt_sort_names
				return meta.get(key) or ''

		def _sort_key(item:tuple[str,dict]) -> Any:
			index, series = item
			return tuple(
		        _series_key(series, order_by) for order_by in sorting
			)
		sort_key = _sort_key


	ep_limit = None
	if not all_unseen_eps:
		ep_limit = 1

	now_dt = now_datetime()

	to_date = now_dt if not future_eps else None
	#to_date = new_datetime() if not future_eps else None
	debug('  ep_limit:', ep_limit)
	debug('  episodes up to date:', to_date)

	date_stamp = now_dt.date().isoformat()

	def match_series(series_id:str, meta:dict):
		if with_unseen_eps:
			_, num_unseen = series_num_seen_unseen(meta)
			if not num_unseen:
				return False

			if not future_eps:
				# TODO: can we do this without fetching the series data?  maybe not... :(
				series = ctx.db.series(series_id)
				if series:
					_, unseen = series_seen_unseen(series, meta)
					for ep in unseen:
						ep_date = ep.get('date')
						if ep_date and ep_date <= date_stamp:
							debug(f'  {_c}', meta['title'], f'{_0}has unseen:', ep['season'], ep['episode'])
							return True # at least one episode already released
				return False  # no episodes already released

		return True

	# refresh everything
	modified = refresh_series(ctx.db, width=width)

	find_idx, match = find_idx_or_match(ctx.command_arguments, country=filter_country, director=filter_director, writer=filter_writer, cast=filter_cast, year=filter_year, tags=filter_tags, match=match_series)

	if find_idx is not None:
		find_state = State.ALL
	series_list = db.indexed_series(ctx.db, state=find_state, index=find_idx, match=match, sort_key=sort_key)

	if not series_list:
		return no_series(ctx.db, filtered=bool(match or filter_director or filter_writer or filter_cast or filter_year))

	if len(series_list) == 1:
		all_unseen_eps = True

	print('Listing ', end='')
	if only_started: print(f'{_u}started{_0} ', end='')
	elif only_planned: print(f'{_u}planned{_0} ', end='')
	elif only_archived: print(f'{_u}archived{_0} ', end='')
	elif only_abandoned: print(f'{_u}abandoned{_0} ', end='')
	else: print(f'{_u}non-archived{_0} ', end='')
	print('series', end='')
	if with_unseen_eps: print(f' with {_u}unseen{_0} episodes', end='')
	if match and getattr(match, 'styled_description', None): print(', matching: %s' % getattr(match, 'styled_description'), end='')
	print(f'{_0}.')

	num_shown = 0
	num_archived = 0

	for index, series_id in series_list:
		meta = ctx.db[series_id]
		is_archived = meta_archived_key in meta

		series = ctx.db.series(series_id)
		# debug(f'{_f}"{series["title"]}" seen: {len(seen)} unseen: {len(unseen)}{_0}')

		#if with_unseen_eps and not unseen:
		#	continue

		num_shown += 1

		# alternate styling odd/even rows
		hilite = (num_shown % 2) == 0
		if hilite:
			set_bg_color('\x1b[48;5;234m')
			print(f'\x1b[48;5;234m{_K}\r', end='')

		grey_color = is_archived and not only_archived

		if show_details:
			print_series_details(index, series, meta, width=width, grey=grey_color, show_tags=True)
		else:
			print_series_title(index, meta, width=width, grey=grey_color, show_tags=True)
			if not show_terse:
				print_archive_status(meta)

		if not show_terse:
			if only_planned:
				no_summary = True
			# don't print "next" if we're printing all unseen episodes anyway
			print_seen_status(
			    series,
				meta,
				summary=(not show_next or not all_unseen_eps) and not no_summary,
				last=not show_next and not all_unseen_eps,
				next=show_next or not all_unseen_eps,
				include_future=future_eps,
				width=width,
				grey=is_archived and not only_archived,
			)

			seen, unseen = series_seen_unseen(series, meta, to_date)
			if seen_eps:
				print_episodes(series, meta, seen, width=width)

			if all_unseen_eps or (future_eps and not show_next):
				print_episodes(series, meta, unseen, width=width, limit=ep_limit, also_future=future_eps)

		if hilite:
			print(f'{_00}{_K}', end='')
			set_bg_color(None)

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
	begin_date:date = now_datetime().date()
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
	for series_id, meta in ctx.db.items():

		if meta_archived_key in meta:
			continue

		series = ctx.db.series(series_id)

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
		if n in range(10, 20):  # the teens is an exception to the rule
		    return 'th'
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
				ep_title = format_episode_title(series['title'], ep, include_time=False, width=width - 9)
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

	year_now = date.today().year
	args = list(a for a in ' '.join(ctx.command_arguments).split())
	year = None
	if len(args) >= 2:
		# does the last word look like a year?
		m = year_ptn.match(args[-1])
		if m:
			y = int(m.group(1) or m.group(2))
			# very rough valid range
			if y in range(1800, year_now + 10):
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

	exists_in_db = list(filter(lambda H: H['id'] in ctx.db, hits))

	if exists_in_db:
		if add:
			print(f'{_c}Already added series (%d):{_0}' % len(exists_in_db))
		else:
			print(f'{_c}Exists in the database: %d{_0}' % len(exists_in_db))

		for new_series in exists_in_db:
			series_id = new_series['id']
			meta = ctx.db[series_id]
			if meta_archived_key in meta:
				arch_tail = f'  \x1b[33m(archived){_0}'
			else:
				arch_tail = None

			imdb_id = ctx.db[new_series['id']].get('imdb_id')
			print('  ', end='')
			print_series_title(None, ctx.db[new_series['id']], imdb_id=imdb_id, tail=arch_tail, width=width - 2)

		if add:
			# exclude ones we already have in our config
			hits = list(filter(lambda H: H['id'] not in ctx.db, hits))

		if add and not hits:
			return Error('No new series found. Try generalizing your search.')

	if len(hits) > max_hits:
		hits = hits[: max_hits]

	print(f'{_b}\x1b[48;2;50;70;50mSearch "%s"; found {_0}{_B}%d{_0} {_b}series:{_0}{_K}{_00}' % (search, len(hits)))

	print(f'{_f}Enriching search hits...{_00}', end='', flush=True)
	hit_details = tmdb.details(hit['id'] for hit in hits)
	if not hit_details:
		return Error('Failed to get title details for all hits (%s)' % ', '.join(hit['id'] for hit in hits))

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
			print(f'\x1b[48;2;50;50;70m{_K}⯈', end='')
		else:
			print(' ', end='')
		print_series_title(idx + 1, item, imdb_id=imdb_id, width=width - 1, tail=tail)
		print(f'{_0B}{_K}', end='')

	selected_index = menu_select(hits, width, print_menu_entry, force_selection=-1 if not add else None)
	if selected_index == -1:
		return None


	if selected_index is None:
		return Error('Nothing selected or cancelled')

	# TODO: move actual "add" to a separate function

	new_series = hits[selected_index]
	series_id = new_series['id']

	series_index = ctx.db.next_list_index
	ctx.db.next_list_index = series_index + 1

	if ctx.option('comment'):
		comment = ctx.option('comment').strip()
	else:
		comment = input('Write a comment (optional): ').strip()

	# add series meta to db (enough to refresh_series can fetch the series data)
	meta = {
	    'title': new_series['title'],
		meta_added_key: now_stamp(),
		meta_list_index_key: series_index,
	}
	if 'year' in new_series:
		meta['year'] = new_series['year'],
	if comment:
		meta[meta_add_comment_key] = comment

	ctx.db[series_id] = meta

	changelog_add(ctx.db, 'Added series', series_id)

	modified = refresh_series(ctx.db, width, subset=[series_id], force=True)
	if max(modified) > 0:
		ctx.save()

	print(f'{_b}Series added:{_00} [{format_state(series_state(meta))}]')

	# fetch the newly computed meta
	meta = ctx.db[series_id]

	# need to loop to figure out its list index
	print_series_title(series_index, meta, imdb_id=meta.get('imdb_id'), width=width, tail=f'  [{State.PLANNED.name.lower()}]')

	return None


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
	if index is None or series_id is None or err is not None:
		if isinstance(err, list):
			found = err
			# TODO: if more than 4, list the "closest" ones
			message = ', '.join(f'{list_index_style}{idx}{_0} %s' % format_title(ctx.db[sid]) for idx, sid in found[:4])
			return Error(f'Ambiguous ({len(found)}): %s' % message)
		return Error(err)

	meta = ctx.db[series_id]

	print(f'{_b}Deleting series:{_00}')
	print_series_title(index, meta, imdb_id=meta.get('imdb_id'), width=width)

	num_seen, num_unseen = series_num_seen_unseen(meta)
	partly_seen = num_seen > 0 and num_unseen > 0

	choices = ['yes']
	if partly_seen:
		print('You have seen %d episodes of %d.' % (num_seen, num_seen + num_unseen))
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


	# delete it, permanently
	ctx.db.remove(series_id)

	changelog_add(ctx.db, 'Deleted series "%s" (%s)' % (meta['title'], format_year_range(meta['year'])))

	# niche case: if we happened to delete the last series, we can easily re-use its list index by "rolling back
	next_index = ctx.db.next_list_index
	if index + 1 == next_index:
		ctx.db.next_list_index = index

	ctx.save()

	print(f'{_b}Series deleted:{_b}')
	print_series_title(index, meta, imdb_id=meta.get('imdb_id'), width=width)

	return None

def _delete_help() -> None:
	print_cmd_usage('delete', '<series>')
	print(f'    {_o}<series>{_0}')

setattr(cmd_delete, 'help', _delete_help)

def cmd_mark(ctx:Context, width:int, marking:bool=True) -> Error|None:

	if not ctx.command_arguments:
		return Error('Required argument missing: # / <IMDb ID>')

	find = ctx.command_arguments.pop(0)

	def filter_callback(series_id:str, meta:dict) -> bool:
		ser_state = series_state(meta)

		if marking and (ser_state & State.ACTIVE) == 0:
			return False
		elif not marking and ser_state & (State.STARTED | State.COMPLETED) == 0:
			return False

		if marking:
			_, num_unseen = series_num_seen_unseen(meta)
			return num_unseen > 0

		return meta.get(meta_last_episode_key) is not None


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

	meta = ctx.db[series_id]
	series = ctx.db.series(series_id)

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
		next_unseen = next_unseen_episode(series, meta)
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
		last_seen, _ = last_seen_episode(series, meta)
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
		seen, unseen = series_seen_unseen(series, meta)
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
					if rng[0] == 'S' or rng[0] == 's':
						season = ('S', )
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

	seen, unseen = series_seen_unseen(series, meta)

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
			print(format_episode_title('  ', ep, include_time=False, width=width, grey=True))


	state_before = series_state(meta)

	seen_state = meta.get(meta_seen_key, {})
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

	meta[meta_seen_key] = seen_state

	ctx.db.recalc_meta(series_id)
	set_dirty()

	if marking:
		print('Marked ', end='')
	else:
		print('Unmarked ', end='')

	print(f'{_c}{len(touched_episodes)}{_00}', end='')
	print(f' episode{plural(touched_episodes)} as seen:  {_0}{_f}{format_duration(episodes_runtime)}{_0}')

	print_series_title(index, meta, width, imdb_id=meta.get('imdb_id'))

	for ep in touched_episodes:
		msg = msg = f'{"M" if marking else "Unm"}arked episode '
		if ep['season'] == 'S':
			msg += 'SP %d' % ep['episode']
		else:
			msg += 's%de%02d' % (ep['season'], ep['episode'])

		changelog_add(ctx.db, msg, series_id)

		print('    %s' % format_episode_title(None, ep, width=width - 4))


	if not incremental:
		# TODO: detect if a mark gap was created (e.g. marked eps 1, 2 and 4)
		pass

	is_archived = meta_archived_key in meta
	state_after = series_state(meta)  # will not cover the auto-archive/restore below

	if marking and num_marked_before == 0 and meta.get(meta_total_episodes_key) > len(touched_episodes):
		print(f'{_c}First episode{plural(len(touched_episodes))} marked!{_0}   {format_state_change(state_before, state_after)}')
	elif not marking and len(seen_state) == 0:
		print(f'{_c}No marked episode left:{_0} {format_state_change(state_before, state_after)}')


	if marking and meta.get(meta_active_status_key) in ('ended', 'canceled') and not is_archived:
		# all seen?
		if len(seen_state) == len(series['episodes']):
			print()
			print(f'{_c}Last episode marked of an {series["active_status"]} series:{_0} {format_state_change(state_before, State.ARCHIVED)}')
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

	meta = ctx.db[series_id]

	currently_archived = meta_archived_key in meta

	if archiving == currently_archived:
		# TODO: better presentation of title
		if archiving:
			return Error('Already archived: %s' % format_title(meta))
		else:
			return Error('Not archived: %s' % format_title(meta))


	_do_archive(ctx.db, series_id, width, mode=mode, print_state_change=print_state_change)

	ctx.save()

	return None

def _archive_help() -> None:
	print_cmd_usage('archive', '<series>')
	print(f'    {_o}<series>{_0}')

setattr(cmd_archive, 'help', _archive_help)


def _do_archive(db:db.Database, series_id:str, width:int, mode:str|None=None, print_state_change:bool=True):
	meta = db[series_id]

	state_before = series_state(meta)

	num_seen, num_unseen = series_num_seen_unseen(meta)
	partly_seen = num_seen > 0 and num_unseen > 0
	archiving = mode is None or mode == 'archiving'

	if archiving:
		print(f'{_b}Series archived', end='')
		if partly_seen:
			print(' (abandoned)', end='')
		print(f':{_00}')
		meta_set(meta, meta_archived_key, now_stamp())
		db.remove_series(series_id)
		changelog_add(db, 'Archived series', series_id)

	else:
		print(f'{_b}Series restored', end='')
		if partly_seen:
			print(' (resumed)', end='')
		print(f':{_00}')
		meta_del(meta, meta_archived_key)
		changelog_add(db, 'Restored series', series_id)
		refresh_series(db, width, subset=[series_id], force=True)

	index = meta.get(meta_list_index_key)
	print_series_title(index, meta, imdb_id=meta.get('imdb_id'), width=width)

	if print_state_change:
		print(format_state_change(state_before, series_state(meta)))


def cmd_restore(*args, **kwargs) -> Error|None:
	kwargs['mode'] = 'restore'
	return cmd_archive(*args, **kwargs)

def _restore_help() -> None:
	print_cmd_usage('restore', '<series>')
	print(f'    {_o}<series>{_0}')

setattr(cmd_restore, 'help', _restore_help)


def cmd_refresh(ctx:Context, width:int) -> Error|None:
	forced = ctx.has_option('force')
	refresh_all = ctx.has_option('all')

	find_idx, match = find_idx_or_match(ctx.command_arguments)

	# the user searched for something, they apparently mean it :)
	forced |= bool(find_idx or match)

	find_states = State.ACTIVE | State.COMPLETED
	if refresh_all:
		find_states |= State.ARCHIVED

	# only refresh non-archived series
	series_list = db.indexed_series(ctx.db, state=find_states, index=find_idx, match=match)

	if not series_list:
		return Error('Nothing matched')

	id_list = [
	    series_id
		for index, series_id in series_list
	]

	t0 = time.time()

	num_series, num_episodes = refresh_series(ctx.db, width, subset=id_list, force=forced)
	# can be 1 even if num_episodes is zero
	if num_series > 0:
		if num_episodes > 0:
			print(f'{_f}Refreshed %d episodes across %d series [%.1fs].{_0}' % (num_episodes, num_series, time.time() - t0), file=sys.stderr)

		ctx.save()

	if not num_series and not num_episodes:
		return Error('Nothing to update')

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
		return Error('and...?')

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
		print('API key set.')

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
	return None

def _undo_help() -> None:
	print_cmd_usage('undo')

setattr(cmd_undo, 'help', _undo_help)


def cmd_audit(ctx:Context, *args, **kw) -> Error|None:
	pass

def _audit_help() -> None:
	print_cmd_usage('audit')

setattr(cmd_audit, 'help', _audit_help)


def cmd_tag(ctx:Context, *args, width:int, mode='tag', **kw) -> Error|None:
	if len(ctx.command_arguments) < 2:
		return Error('<tag> and <series> arguments are required')

	tag_name = ctx.command_arguments.pop(0)
	tag = config.tag(tag_name)
	if not tag:
		return Error(f'Unknown tag: {tag_name}')
	tag_name = tag['name']

	states = State.ACTIVE
	find_idx, match = find_idx_or_match(ctx.command_arguments)
	found_series = db.indexed_series(ctx.db, state=states, index=find_idx, match=match)

	modified = []
	for index, series_id in found_series:
		meta = ctx.db[series_id]
		all_tags = meta.get( meta_tags_key, [])
		if mode == 'tag':
			if tag_name not in all_tags:
				modified.append(series_id)
				all_tags.append(tag_name)
				meta_set(meta, meta_tags_key, all_tags)
		elif tag_name in all_tags:
			modified.append(series_id)
			del all_tags[all_tags.index(tag_name)]
			meta_set(meta, meta_tags_key, all_tags)

	print(format_tag(tag), 'Series %sged:' % mode, len(modified))

	for series_id in modified:
		print_series_title(None, ctx.db[series_id], width=width, show_progress=False)

	if modified:
		ctx.save()


def _tag_help() -> None:
	print_cmd_usage('tag', '<tag> <series>')

setattr(cmd_tag, 'help', _tag_help)


def cmd_untag(ctx:Context, *args, **kw) -> Error|None:
	return cmd_tag(ctx, *args, mode='untag', **kw)

def _untag_help() -> None:
	print_cmd_usage('untag', '<tag> <series>')

setattr(cmd_untag, 'help', _untag_help)


TAG_MAX_LENGTH = 10

def list_tags(ctx:Context, width:int|None=None):
	tags = config.get('tags')
	if not tags:
		print('No tags defined.')
		print(f'Try: {_b}tags{_0} {_o}<name> <color> {_f}[<description>]{_0}')
		return

	if not isinstance(tags, dict):
		return Error('Bad config: "tags"; not dict: %s' % type(tags).__name__)

	print('Listing %d tag%s:' % (len(tags), 's' if len(tags) != 1 else ''))
	def by_name(item):
		return item[0].lower()

	for tag_name, tag_def in sorted(tags.items(), key=by_name):
		pad = TAG_MAX_LENGTH - len(tag_name)
		print('  %s%s' % (format_tag(tag_def, tag_name), ' '*pad), end='')
		if tag_def.get('description'):
			print(f' {_f}%s{_0}' % tag_def.get('description'), end='')

		tagged_series = db.indexed_series(ctx.db, tags=[tag_name], state=State.ALL)
		if tagged_series:
			print(' %d series' % len(tagged_series), end='')
		print()


def cmd_tags(ctx:Context, *args, width:int|None=None, **kw) -> Error|None:
	if not ctx.command_arguments or ctx.command_arguments[0] == 'list':
		if ctx.command_arguments:
			ctx.command_arguments.pop(0)
		return list_tags(ctx, width=width)

	sub_cmd = ctx.command_arguments.pop(0)

	if sub_cmd == 'delete':
		# delete tag
		use_force = ctx.has_option('-f')
		name = ctx.command_arguments[0]
		existing = config.tag(name)
		if not existing:
			return Error('No such tag: %s' % name)

		name = existing['name']  # get the correct name

		tagged_series = db.indexed_series(ctx.db, tags=[name], state=State.ALL)
		if tagged_series:
			print('%d series has this tag (tag will be removed)' % len(tagged_series))

		if not user_confirm(f'Delete tag {_b}{name}{_0}?'):
			return Error('Cancelled')

		for index, series_id in tagged_series:
			meta = ctx.db[series_id]
			all_tags = meta.get(meta_tags_key)
			del all_tags[all_tags.index(name)]
			meta_set(meta, meta_tags_key, all_tags)

		config.remove(f'tags/{name}')

		if tagged_series:
			ctx.save()

	elif sub_cmd == 'set':
		# add/replace tag
		if len(ctx.command_arguments) < 2:
			return Error('<name> and <color> arguments are required.')

		name = ctx.command_arguments.pop(0)
		color = ctx.command_arguments.pop(0)
		description = ctx.command_arguments.pop(0) if ctx.command_arguments else None

		if not name or len(name) > TAG_MAX_LENGTH:
			return Error(f'Tag name "{name}" is not valid. (length: 1 - {TAG_MAX_LENGTH})')
		for c in name:
			if not c.isalnum():
				return Error(f'Tag name "{name}" is not valid. (only letters and numbers)')

		existing = config.tag(name)
		if existing and isinstance(existing, dict):
			name = existing['name']
			if not description:
				description = existing.get('description')

		action_verb = 'Added' if not existing else 'Updated'

		if len(color) != 6:
			return Error(f'Tag color {color}" is invalid (rrggbb).')
		for c in color:
			if c not in string.hexdigits:
				return Error(f'Tag color {color}" is invalid (rrggbb).')

		tag_config = {
			'color': color,
			**({'description': description} if description else {})
		}
		config.set(f'tags/{name}', tag_config)

		print('%s tag -> %s' % (action_verb, format_tag(tag_config, name)), end='')
		if description:
			print(f' {_f}%s{_0}' % description, end='')
		print()

	else:
		return Error("Unknown sub command: %s" % sub_cmd)


def _tags_help() -> None:
	print_cmd_usage('tags', [
		'[list]',
		'set <tag> [rrggbb] [description]',
		'delete <tag>'
	])

setattr(cmd_tags, 'help', _tags_help)


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

	meta = ctx.db[series_id]
	if meta_archived_key not in meta:
		return Error('only archived series may be rated')

	rating_str = ctx.command_arguments.pop(0)
	try:
		rating = int(rating_str)

		meta_set(meta, meta_rating_key, rating)
		changelog_add(ctx.db, 'Rated series', series_id)

	except ValueError as ve:
		return Error(f'invalid rating: {ve}')


	print(f'Rated {format_title(meta)}: {_b}{rating}{_0}')

	comment = ctx.option('comment')
	if comment:
		meta_set(meta, meta_rating_comment_key, comment)
		print(f'{_b}Comment:{_0} {comment}')
	else:
		comment = meta.get(meta_rating_comment_key)
		if comment:
			print(f'{_b}Existing comment:{_0} {comment}')

	ctx.save()
	return None

def _rate_help() -> None:
	print_cmd_usage('rate', '<series> <rating>')
	print(f'    {_o}<series>     {_0} Rate specified series')
	print(f'    {_o}<rating>     {_0} Number, 0 - 10')

setattr(cmd_rate, 'help', _rate_help)



def cmd_help(ctx:Context, *args, **kw) -> Error|None:
	if ctx.command_arguments:
		arg = ctx.command_arguments.pop(0)
		if arg in ('env', 'environment'):
			print_env_help()
			return None

	print_usage()
	return None


def _help_help() -> None:
	print_cmd_usage('help', '[<topic>]')
	print('Topics:')
	print(f'    {_o}env          {_0} Environment variables')
	print('    (none)    ▶   General usage')

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
		'help': f'Remove a series from %s (use {_o}undo{_0} to restore)' % PRG,
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
		'help': f'Unmark a series/season/episode - reverse of {_b}mark{_0}.',
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
		'help': f'Undo last change.  {_c}permanent!{_0}'
	},
	'audit': {
	    'alias': (),
		'handler': cmd_audit,
		'help': 'List recent changes.'
	},
	'tag': {
		'alias': ('t', ),
		'handler': cmd_tag,
		'help': 'Add a tag to one or more series'
	},
	'untag': {
		'alias': ('T',),
		'handler': cmd_untag,
		'help': 'Remove a tag from one or more series'
	},
	'tags': {
		'alias': (),
		'handler': cmd_tags,
		'help': 'Manage defined tags'
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
	return None


def _disable_refresh(value:date, key:str, options:dict) -> str|None:
	config.set('refresh-enabled', False, store=Store.Memory)
	return None

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

_opt_sort_names = _opt_list(',', ['title', 'year', 'earliest', 'latest', 'added', 'archived'])

__opt_series_sorting = {
    'sorting': {
	    'name': '--sort',
		'arg': str,
		'help': 'Sort series',
		'func': _opt_sort_names
	},
}

__opt_tags = {
	'tags': {
		'name': '--tags',
		'arg': str,
		'help': 'Filter by tags'
	}
 }

# TODO: merge with 'known_commands' ?  (at least for the command-specific options)

command_options = {
    None: { # i.e. global options
	    'fake-now':          { 'name': '--fake-now', 'arg': date, 'help': 'Simulate a specific "today" date', 'func': _set_fake_date },
		'no-refresh':        { 'name': '--no-refresh',            'help': 'Don\'t refresh any series data', 'func': _disable_refresh },
	},
	'show': {
	    'all':               { 'name': ('-a', '--all'),          'help': 'List all series (including archived)' },
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
		**__opt_tags,
	},
	'unseen': {
	    'started':           { 'name': ('-s', '--started'),      'help': 'List only series with seen episodes' },
		'planned':           { 'name': ('-p', '--planned'),      'help': 'List only series without seen episodes' },
		'all-episodes':      { 'name': ('-e', '--episodes'),     'help': 'Show all unseen episodes (not only first)' },
		'future-episodes':   { 'name': ('-f', '--future'),       'help': 'Also shows (series with) future episodes' },
		**__opt_series_sorting,  # type: ignore  # how to convince mypy here?
		**__opt_tags,
	},
	'refresh': {
	    'force':             { 'name': ('-f', '--force'),        'help': 'Refresh whether needed or not' },
		'all':               { 'name': ('-a', '--all'),          'help': 'Refresh regardless of state (e.g. archived)' },
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


def find_idx_or_match(args, country:re.Pattern|None=None, director:re.Pattern|None=None, writer:re.Pattern|None=None, cast:re.Pattern|None=None, year:list[int]|None=None, tags:list[str]|None=None, match:Callable[[str,dict],bool]|None=None) -> tuple[int|None, Callable|None]:

	# print('FILTER title/idx:', (_c + ' '.join(args) + _0fg) if args else 'NONE')
	# print('          country:', (_c + country.pattern + _0fg) if country else 'NONE')
	# print('        director:', (_c + director.pattern + _0fg) if director else 'NONE')
	# print('          writer:', (_c + writer.pattern + _0fg) if writer else 'NONE')
	# print('            cast:', (_c + cast.pattern + _0fg) if cast else 'NONE')
	# print('            year:', (_c + '-'.join(year) + _0fg) if year else 'NONE')


	if not args and not country and not director and not writer and not cast and not year and not match:
		return None, None

	match_callback = match

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
		# print('            tags:', (_c + ', '.join(tags) + _0) if tags else 'NONE')

		# TODO: function should also take list index: (list_index, series) -> bool

		def find_match(db:Database, series_id:str, meta:dict):
			ok = True

			if ok and title:
				ok = title.search(meta.get('title', '')) is not None
			if ok and year:
				ok = _match_years(meta, year)
			if ok and tags:
				ok = _match_tags(meta, tags)
			if ok and imdb_id:
				ok = imdb_id == db.series(series_id).get('imdb_id')
			if ok and country:
				ok = country.search(db.series(series_id).get('country', '')) is not None
			if ok and director:
				ok = _match_names(db.series(series_id), 'director', director)
			if ok and writer:
				ok = _match_names(db.series(series_id), 'writer', writer)
			if ok and cast:
				ok = _match_names(db.series(series_id), 'cast', cast)
			if ok and match_callback:
				ok = match_callback(series_id, meta)

			# if ok:
			# 	print(f'    match {_g}%s{_0}' % series['title'])
			# else:
			# 	print(f'    match {_f}%s{_0}' % series['title'])

			return ok

		filter_context = {
		    'title': title.pattern if title else None,
			'country': country.pattern if country else None,
			'director': director.pattern if director else None,
			'writer': writer.pattern if writer else None,
			'cast': cast.pattern if cast else None,
			'year': '-'.join(str(y) for y in year) if year else None,
		}
		setattr(find_match, 'description', ' '.join('%s=%s' % (n, v) for n, v in filter_context.items() if v))

		if filter_context:
			filter_parts = list((n, v) for n, v in filter_context.items() if v)

			if filter_parts:
				setattr(find_match, 'styled_description', _c + ' '.join(f'%s{_g}={_0}{_b}%s{_0}' % (n, v) for n, v in filter_parts))

		return None, find_match


def _substr_re(s:str) -> Pattern:
	return re.compile('.*?' + re.escape(s.replace(' ', '.*?')) + '.*', re.IGNORECASE)


def _match_names(series:dict, attribute:str, pattern:re.Pattern) -> bool:
	# print('match %s of "%s": %s' % (attribute, series['title'], pattern.pattern))
	for name in series.get(attribute, []):
		# print(' ?', name)
		if pattern.search(name):
			# print(' !')
			return True

	return False


def _match_years(meta:dict, years:list[int]) -> bool:
	s_year = meta.get('year')
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

def _match_tags(meta:dict, tags:list[str]) -> bool:
	series_tags = meta.get(meta_tags_key)
	if isinstance(series_tags, list):
		for tag in tags:
			if tag in series_tags:
				return True

	return False

def episodes_by_key(series:dict, keys:list) -> list:
	keys_to_index:dict[str, int] = {}
	episodes:list[dict] = series.get('episodes', [])
	for idx, ep in enumerate(episodes):
		keys_to_index[episode_key(ep)] = idx

	return [
        episodes[keys_to_index[key]]
		for key in keys
	]


def no_series(db:Database, filtered:bool=False) -> Error:

	if not db:
		return Error(f'No series added.  Use: {_b}%s add <title search...> [<year>]{_0}' % PRG)

	precision = ' matched (try -a)' if filtered else ''
	return Error('No series%s.' % precision)



def last_update(meta:dict) -> datetime|None:
	updates = meta.get(meta_update_history_key)
	if updates:
		return datetime.fromisoformat(updates[-1])

	return None


def refresh_series(db:Database, width:int, subset:list|None=None, force:bool=False, affected:dict|None=None) -> tuple[int, int]:
	if not config.get_bool('refresh-enabled', True):
		return 0, 0

	if subset is None:
		subset = list(
		    series_id
			for series_id, _ in db.items()
		)

	if not force:
		# only refresh if there's currently any data stored
		before = len(subset)
		subset = list(
		    series_id
			for series_id in subset
			if db.has_data(series_id)
		)
		after = len(subset)
		if after < before:
			debug(f'{before - after} series removed from refresh; no data stored')

	if force:
		to_refresh = subset
	else:
		def check_expired(_, meta:dict) -> bool:
			return m_db.should_update(meta)
		to_refresh = list(m_db.filter_map(db, filter=check_expired, map=lambda sid, _: sid))

	to_refresh = list(sorted(to_refresh, key=int))

	if not to_refresh:
		return 0, 0

	debug('to_refresh (maybe):', len(to_refresh))
	for series_id in to_refresh:
		meta = db[series_id]
		debug('   %s [%s]' % (meta['title'], meta.get(meta_list_index_key)))

	# set time of last check (regardless whether there actually were any updates)
	touched = 0
	for series_id in to_refresh:
		meta = db[series_id]
		meta[meta_update_check_key] = now_stamp()
		touched += 1

	def mk_prog(total):
		return progress.new(total, width=width - 2, bg_color=rgb('#404040'), bar_color=rgb('#686868'), text_color=rgb('#cccccc'))

	latest_update_time:datetime|None = None

	if not force:
		# check with TMDb if there actually are any updates
		prog_bar = mk_prog(len(to_refresh))
		clrline()
		print(f'%s{_EOL}' % prog_bar('Checking %d series for updates...' % len(to_refresh)), end='', flush=True)

		def show_ch_progress(completed:int, *_) -> None:
			print(f'\r{_K}%s{_EOL}' % prog_bar(completed, text='Checking updates...'), end='', flush=True)


		oldest_refresh:datetime = min(
		    last_update(db[sid]) or datetime.now()
			for sid in to_refresh
		)

		debug('changes since:', oldest_refresh)

		changes = tmdb.changes(to_refresh, oldest_refresh, include=include_changes, progress=show_ch_progress)

		clrline()

		for series_id, changes in zip(list(to_refresh), changes):
			meta = db[series_id]

			debug(series_id, meta['title'], 'changes:')
			for ch in changes:
				items = ch['items']
				debug('  %s (%d items)' % (ch['key'], len(ch['items'])))

			if not changes:
				last_update_time = last_update(meta)
				if last_update_time:
					update_age = datetime.now() - last_update_time
					if update_age.total_seconds() < 2*m_db.WEEK:
						# no changes, but there was an update within the age cap, so we can wait a bit more
						to_refresh.remove(series_id)

					else:
						debug('no changes, but update too old: %s [%s]  %s (%s days ago)' % (meta['title'], meta.get(meta_list_index_key), last_update_time.isoformat(' '), update_age.days))

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


	# remember each series status before we do the refresh (to detect whether the status changed after)
	previous_status = {
	    series_id: db[series_id].get(meta_active_status_key)
		for series_id in to_refresh
	}

	debug('to_refresh (for real):', len(to_refresh))
	for series_id in to_refresh:
		meta = db[series_id]
		debug('   %s [%s]' % (meta['title'], meta.get(meta_list_index_key)))

	prog_bar = mk_prog(len(to_refresh))
	clrline()
	print(f'%s{_EOL}' % prog_bar('Refreshing %d series...' % len(to_refresh)), end='', flush=True)
	# TODO: show 'spinner'

	def show_progress(completed:int, *_) -> None:
		clrline()
		print(f'%s{_EOL}' % prog_bar(completed, text='Refreshing...'), end='', flush=True)

	# fetch updates to all eligible series and their episodes
	result = tmdb.episodes(to_refresh, with_details=True, progress=show_progress)

	clrline()

	num_episodes = 0

	for series_id, (series, episodes) in zip(to_refresh, result):

		changelog_add(db, 'Refreshed', series_id)

		series['episodes'] = episodes
		# replace entry in DB
		db.set_series(series_id, series)

		# update meta
		meta = db[series_id]
		# keep a list of last N updates
		db.add_updated_log(series_id, latest_update_time_str)

		# if series changed atatus to non-active; archive if all episodes are seen
		if series_state(meta) & State.ARCHIVED == 0:
			all_seen = len(episodes) == len(meta.get(meta_seen_key, []))
			if all_seen and previous_status[series_id] == 'active' and meta.get(meta_active_status_key) != 'active':
				# status changed to non-active, have we seen all episodes?
				# allright then, we have no further business with this series
				_do_archive(db, series_id, width=width)
				if affected is not None:
					affected[series_id] = State.ARCHIVED

		num_episodes += len(episodes)

		set_dirty()


	return len(to_refresh), num_episodes



def print_series_details(index:int, series:dict, meta:dict, width:int, grey:bool=False, show_tags:bool=False) -> None:

	tail = None
	if series.get('imdb_id'):
		tail = imdb_url_tmpl % series["imdb_id"]
		tail_style = f'{_o}{_u}'
	print_series_title(index, meta, width, grey=grey, tail=tail, tail_style=tail_style, show_tags=show_tags)

	print_archive_status(meta)

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

	print(f'    {_o}Added:{_0}', meta.get(meta_added_key), end='')
	if meta_add_comment_key in meta:
		add_comment = meta[meta_add_comment_key]
		print(f'  {_g}{_i}"{add_comment}"{_0}')
	else:
		print()

	if meta_archived_key in meta:
		rating = meta.get(meta_rating_key)
		comment = meta.get(meta_rating_comment_key)
		if rating is not None:
			print(f'    {_o}Rating:{_0}  {_i}{_c}{rating}{_0}', end='')
		if comment:
			print(f'  "{_i}{comment}{_0}"')
		else:
			print()

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


def print_cmd_usage(command:str, syntax:str|list[str]='') -> None:
	entry = known_commands[command]

	summary = entry.get('help')
	if summary:
		print(f'{_b}{summary}{_0}')

	aliases = entry.get('alias')
	if aliases and isinstance(aliases, tuple):
		print(f'{_b}Alias:{_0} %s' % ', '.join(aliases))

	if isinstance(syntax, str):
		syntax = [syntax]

	for stx in syntax:
		print(f'{_b}Usage:{_0} %s {_c}%s{_0} %s' % (PRG, command, stx))


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
	print( '  If an argument does not match a command, it will be used as argument to the default command.')
	print( '  Shortest unique prefix of a command is enough, e.g. "ar"  for "archive".')
	if utils.json_serializer() != 'json':
		print(f'  {_f}Using {_b}{utils.json_serializer()}{_0}{_f} for faster load/save.')
	else:
		print(f'  {_f}Install \'orjson\' for faster load/save{_0}')
	from . import compression
	if compression.method():
		print(f'  {_f}Using {_b}{compression.compressor()}{_0}{_f} for compressing data files.')
	if not tmdb.ok():
		print(f'   {_c}NOTE: Need to set TMDb API key (TMDB_API_KEY environment){_0}')
	sys.exit(exit_code)
	return None


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
