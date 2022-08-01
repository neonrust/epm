#! /usr/bin/env python3
# -*- mode: python -*-

import os.path
import re
import time
from datetime import datetime, date, timedelta
from tempfile import mkstemp
from os.path import basename, dirname, expandvars, expanduser, exists as pexists, getsize as psize
from calendar import Calendar, day_name, month_name, MONDAY, SUNDAY
import textwrap

from typing import Callable, Any
from types import ModuleType as Module

import sys
# use orjson if available
orjson:Module|None = None
try:
	import orjson as _orjson
	orjson = _orjson
except ImportError:
	orjson = None

# always import std json (useful for debugging sometimes)
import json

VERSION = '0.9'
VERSION_DATE = '2022-08-01'


def start():
	load_config()
	# print(orjson.dumps(app_config, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode('utf-8'))

	api_key = config_get('lookup/api-key')
	if api_key:
		tmdb.set_api_key(api_key)

	ctx = context(sys.argv[1: ])

	err = ctx.invoke(width=term_width())
	if err is not None:
		print(f'{warning_prefix(ctx.command)} {err}')
		sys.exit(1)


class context:
	def __init__(self, args:list[str]):
		self.global_options = {
			'debug': config_bool('debug', 0),
		}
		self.command:str|None = None
		self.command_options:dict = {
			'max-age': config_int('max-age'),
		}
		self.command_arguments:list = []
		self._parse_args(args)

		if self.command is not None:
			self.handler:Callable = known_commands[self.command]['handler']


	def invoke(self, width:int) -> str|None:
		if not load_series_db(self):
			print(f'{_E}ERROR{_00} Could not load series db!', file=sys.stderr)
			sys.exit(1)

		return self.handler(self, width=width)


	def _set_command(self, name:str) -> None:
		self.command = name

		# insert configured default arguments and options
		args = config_get('commands/%s/default_arguments' % self.command, [])
		if args and isinstance(args, list):
			self.command_arguments = args

		opts = config_get('commands/%s/default_options' % self.command, [])
		while isinstance(opts, list) and opts:
			eat_option(self.command, opts.pop(0), opts, self.command_options)


	def _add_argument(self, argument:str) -> None:
		self.command_arguments.append(argument)


	def _parse_args(self, args:list) -> None:

		default_command = str(config_get('commands/default', 'unseen'))

		while args:
			arg = args.pop(0)

			# print('check arg: "%s"' % arg)

			if arg.startswith('-'):
				if not self.command:
					if arg in '--help':
						print_usage()

					# attempt to interpret as a global option
					# print('  try global opt: "%s"' % arg)
					if eat_option(None, arg, args, self.global_options, unknown_ok=True):
						# print('  -> global opt:', arg)
						continue

					self._set_command(default_command)
					# print('  -> cmd: %s (default)' % self.command)

				# print('  opt:', arg, '(cmd: %s)' % self.command)
				eat_option(self.command, arg, args, self.command_options)  # will exit if not correct
				continue

			if not self.command and not arg.startswith('.'):
				# print('  try cmd: "%s"' % arg)
				cmd = resolve_cmd(arg)
				if cmd:
					self._set_command(cmd)
					# print('  -> cmd = %s' % self.command)
					continue

			if not self.command:
				if arg.startswith('.'):
					arg = arg[1: ]

				self._set_command(default_command)
				# print('  -> cmd = %s (default)' % self.command)

			if self.command:
				self._add_argument(arg)
				# print('  -> "%s" [%s]' % (self.command, ' '.join(self.command_arguments)))

			else:
				raise RuntimeError('Bug: unhandled argument: "%s"' % arg)


		if not self.command:
			self._set_command(default_command)

		if self.command == 'help':
			print_usage()


def resolve_cmd(name:str) -> str|None:
	matching = []

	for primary in known_commands:
		aliases = [primary] + list(known_commands[primary]['alias'])
		for alias in aliases:
			if name == alias:
				return primary  # direct match (case sensitive), just return
			if alias.startswith(name.lower()):
				matching.append(primary)
				# don't break, there might be an exact match for an alias

	if len(matching) == 1:
		return matching[0]

	if len(matching) > 1:
		ambiguous_cmd(name, matching)

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
		def _set_opt(v):
			# print('OPT>', key, '=', v)
			options[key] = v
		set_func = _set_opt

	arg_type = opt_def.get('arg')

	# print('arg type:', arg_type.__name__)

	if not arg_type:
		if option_arg:
			bad_opt_arg(command, option, option_arg, None)

		set_func(True)

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

		validator = opt_def.get('validator', lambda _: True)

		if arg_type is str:
			set_func(arg_str)

		elif arg_type is int:
			try:
				v = int(arg_str)
				if not validator(v):
					bad_opt_arg(command, option, arg_str, arg_type, validator.__doc__)
				set_func(v)
			except ValueError:
				bad_opt_arg(command, option, arg_str, arg_type)

		elif arg_type is datetime:
			try:
				v = datetime.fromisoformat(arg_str)
				if not validator(v):
					bad_opt_arg(command, option, arg_str, arg_type, validator.__doc__)
				set_func(v)
			except ValueError:
				bad_opt_arg(command, option, arg_str, arg_type)

		elif not validator(arg_str):
			bad_opt_arg(command, option, arg_str, arg_type, validator.__doc__)

		else:
			raise NotImplementedError('Argument type %s' % arg_type.__name__)


	return True


###############################################################################
###############################################################################


def cmd_unseen(ctx:context, width:int) -> str | None:
	refresh_series(ctx, width)

	# TODO: print header/columns

	also_future = 'unseen:future' in ctx.command_options
	only_started = 'unseen:started' in ctx.command_options
	only_planned = 'unseen:planned' in ctx.command_options
	all_unseen = 'unseen:all_episodes' in ctx.command_options

	if only_started and only_planned:
		return 'Can\'t specify "started" and "planned" at the same time (try "list" command)'

	find_idx, match = find_idx_or_match(ctx.command_arguments)
	series_list = get_series(ctx.db, archived=False, index=find_idx, match=match)

	print(f'Listing {_0}', end='')
	if only_started: print('started ', end='')
	elif only_planned: print('planned ', end='')
	print(f'series with unseen episodes', end='')
	if match: print(', matching: %s' % match.styled_description, end='')
	print(f'{_0}.')

	if not series_list:
		return no_series(ctx.db)

	series_unseen = []
	for index, series_id in series_list:
		series = ctx.db[series_id]
		_, unseen = seen_unseen_episodes(series)
		if unseen:
			series_unseen.append((index, series_id, series, unseen))

	if not series_unseen:
		if match:
			return 'Nothing matched: %s (or everything already seen)' % match.pattern
		return 'Everything has been seen, better add some series!'


	# TODO: optionally sort series by "earliest" episode in summary mode

	num_shown = 0
	total_episodes = 0
	total_duration = 0

	for index, series_id, series, unseen in series_unseen:

		any_episodes_seen = bool(get_meta(series, 'seen', {}))

		if only_started and not any_episodes_seen:
			continue
		if only_planned and any_episodes_seen:
			continue

		# alternate styling odd/even rows
		hilite = (num_shown % 2) == 0

		tail = None
		if not all_unseen:
			tail = f' %3d unseen' % len(unseen)

		series_printed = False
		def print_series():
			if hilite:
				print(f'\x1b[48;5;234m{_K}', end='')

			print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width, tail=tail, tail_style=_f)
			nonlocal series_printed
			series_printed = True

		if all_unseen:
			_, unseen = seen_unseen_episodes(series)
			printed_keys = print_episodes(series, unseen, width=width, pre_print=print_series, also_future=also_future)
			if printed_keys:
				num_shown += 1

			total_episodes += len(printed_keys)
			total_duration += sum(ep.get('runtime') or 0 for ep in episodes_by_key(series, printed_keys))

		else:
			# print first episode
			if not (also_future or is_released(unseen[0])):
				continue

			print_series()
			print_seen_status(series, summary=False, last=False, next=True, width=width)

			num_shown += 1
			total_episodes += 1
			total_duration += unseen[0].get('runtime') or 0

		if hilite:
			print(f'{_00}{_K}', end='')

	# this is wildly incorrect!
	#print(f'{_b}\x1b[48;2;20;50;20m%d series{_0}' % num_shown)
	print(f'{_b}\x1b[48;2;20;50;20m{_K}\rSeries: {num_shown}', end='')
	if all_unseen:
		print(f' {_fi} Episodes: \x1b[1m{total_episodes}{_0}', end='')
		if total_duration:
			print(f'  {_f}{fmt_duration(total_duration*60)}{_0}', end='')
	print()

	return None

def _unseen_help() -> None:
	print_cmd_usage('unseen', '<options> <search...>')
	print(f'    {_o}# / <IMDb ID>       {_00} Show only specific')
	print(f'    {_o}[<pattern>]         {_00} Show only matching')

setattr(cmd_unseen, 'help', _unseen_help)

def cmd_show(ctx:context, width:int) -> str|None:
	refresh_series(ctx, width)

	# TODO: print header/columns

	list_all = 'show:all' in ctx.command_options
	only_archived = 'show:archived' in ctx.command_options
	only_started = 'show:started' in ctx.command_options
	only_planned = 'show:planned' in ctx.command_options
	only_abandoned = 'show:abandoned' in ctx.command_options
	all_unseen = 'show:all_episodes' in ctx.command_options
	seen_episodes = 'show:seen_episodes' in ctx.command_options
	show_details = 'show:details' in ctx.command_options

	if [only_started, only_planned, only_archived, only_abandoned].count(True) > 1:
		return 'Specify only one of "started", "planned", "archived" and "abandoned"'

	filter_director = ctx.command_options.get('show:director')
	filter_writer = ctx.command_options.get('show:writer')
	filter_cast = ctx.command_options.get('show:cast')
	filter_year = ctx.command_options.get('show:year')

	# NOTE: in the future, might support RE directly from the user
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
			return 'Bad year filter: %s (use: <start year>[-<end year>])' % filter_year

	find_idx, match = find_idx_or_match(ctx.command_arguments, director=filter_director, writer=filter_writer, cast=filter_cast, year=filter_year)
	series_list = get_series(ctx.db, index=find_idx, match=match)

	print(f'Listing ', end='')
	if only_started: print('started ', end='')
	elif only_planned: print('planned ', end='')
	elif only_archived: print('archived ', end='')
	elif only_abandoned: print('abandoned ', end='')
	else: print('non-archived ', end='')
	print('series', end='')
	if match: print(', matching: %s' % match.styled_description, end='')
	print(f'{_0}.')

	if not series_list:
		return no_series(ctx.db, filtering=match or filter_director or filter_writer or filter_cast or filter_year)


	num_shown = 0
	num_archived = 0

	for index, series_id in series_list:
		series = ctx.db[series_id]
		is_archived = has_meta(series, 'archived')

		if is_archived:
			num_archived += 1
		if is_archived and not (list_all or only_archived or only_abandoned):
			continue
		if not is_archived and only_archived:
			continue
		has_episodes_seen = len(get_meta(series, 'seen', {})) > 0
		if only_started and not has_episodes_seen:
			continue
		if only_planned and has_episodes_seen:
			continue
		if only_abandoned and not is_archived:
			continue

		seen, unseen = seen_unseen_episodes(series)
		if only_abandoned:
			if len(unseen) == 0:
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

			#if only_archived:
			print_archive_status(series)

		# don't print "next" if we're printing all unseen episodes anyway
		print_seen_status(series, gray=is_archived and not only_archived, next=not all_unseen, width=width)

		if seen_episodes:
			print_episodes(series, seen, width=width)

		if all_unseen:
			print_episodes(series, unseen, width=width)

		if hilite:
			print(f'{_00}{_K}', end='')

	if num_shown == 0:
		if match:
			return 'Nothing matched'

	print(f'{_00}{_K}', end='')
	print(f'{_b}\x1b[48;2;20;50;20m{_K}\r%d series {_fi} Total: %d   Archived: %d{_00}' % (num_shown, len(series_list), num_archived))

	return None

def _show_help() -> None:
	print_cmd_usage('show', '<options> [<title search>...]')
	print(f'    {_o}[<title search>]     {_00} Show only matching series')

setattr(cmd_show, 'help', _show_help)


def cmd_calendar(ctx:context, width:int) -> str|None:
	refresh_series(ctx, width)

	num_weeks = int(ctx.command_arguments[0]) if ctx.command_arguments else config_int('commands/calendar/num_weeks', 1)

	cal = Calendar(MONDAY)
	today = date.today()
	start_date = today

	episodes_by_date = {}

	# collect episodes over num_weeks*7
	#   using margin of one extra week, b/c it's simpler
	end_date = today + timedelta(days=(num_weeks+1)*7)
	for series_id, series in ctx.db.items():
		if has_meta(series, 'archived'):
			continue

		# faster to loop backwards?
		for ep in series.get('episodes', []):
			ep_date_str = ep.get('date')
			if not ep_date_str:
				continue

			ep_date = date.fromisoformat(ep_date_str)
			if ep_date >= today and ep_date < end_date:
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

	# until we've printed enough days, and always end at a full week
	while days_todo > 0 or wday_idx != SUNDAY:
		# print('print starting from:', start_date, days_todo)
		month_days = cal.itermonthdates(start_date.year, start_date.month)

		for mdate in month_days:
			wday_idx = (wday_idx + 1) % 7
			if mdate < today:
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

		start_date = (today + timedelta(days=31)).replace(day=1)
		month_days = cal.itermonthdates(start_date.year, start_date.month)

def _calendar_help():
	print_cmd_usage('calendar', '[<full weeks>]')

setattr(cmd_calendar, 'help', _calendar_help)



year_ptn = re.compile(r'^(\d{4})|\((\d{4})\)$')  # 1968 or (1968)

def cmd_add(ctx:context, width:int, add:bool=True) -> str | None:
	if not ctx.command_arguments:
		return 'required argument missing: <title> / <Series ID>'

	max_hits = int(ctx.command_options.get('search:max-hits') or 0) or config_int('lookup/max-hits')

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

	print(f'{_f}- Searching "%s"' % search, end='')
	if year:
		print(' (%d)' % year, end='')
	print(f' ...{_00}', end='', flush=True)

	hits = []
	page = 1

	while len(hits) < max_hits:
		page_hits, total = tmdb.search(search, year=year, page=page)
		hits.extend(page_hits)
		if not page_hits or total == len(hits):
			break

		page += 1

	if len(hits) > max_hits:
		hits = hits[: max_hits]

	print(f'\r{_K}', end='')
	if not hits:
		return 'Nothing found. Try generalizing your search.'

	if not add or len(hits) > 1:
		# exclude ones we already have in our config
		already = list(filter(lambda H: H['id'] in ctx.db, hits))
		if already:
			print(f'{_f}Already added: %d{_00}' % len(already))
			for hit in already:
				if has_meta(ctx.db[hit['id']], 'archived'):
					arch_tail = f'  \x1b[33m(archived){_00}'
				else:
					arch_tail = None

				imdb_id = ctx.db[hit['id']].get('imdb_id')
				print_series_title(None, ctx.db[hit['id']], imdb_id=imdb_id, gray=True, tail=arch_tail, width=width)

		hits = list(filter(lambda H: H['id'] not in ctx.db, hits))
		print(f'{_g}Found {_00}{_b}%d{_00} {_g}series:{_00}' % len(hits))

		print(f'{_f}Enriching search hits...{_00}', end='', flush=True)
		hit_details = tmdb.details(hit['id'] for hit in hits)
		print(f'\r{_K}', end='')

		# print a menu and a prompt to select from it

		def print_menu_entry(idx, item):
			if hit_details[idx]:
				item.update(hit_details[idx])
			imdb_id = item.get('imdb_id')
			tail = None
			if 'total_episodes' in item:
				tail = '%5d episodes' % item['total_episodes']
			print_series_title(idx + 1, item, imdb_id=imdb_id, width=width, tail=tail)

		prompt = f'\x1b[44;97;1mSelect series (1 - %d) to add -->{_00} ' % len(hits)

		selected = menu_select(hits, prompt, print_menu_entry, force_selection=-1 if not add else None)
		if selected == -1:
			return

		if selected is None:
			return 'Nothing selected, cancelled'

	else:
		selected = 0

	hit = hits[selected]
	series_id = hit['id']

	hit[meta_key] = {}
	set_meta(hit, 'seen', {})
	set_meta(hit, 'added', now())

	hit.pop('id', None)

	ctx.db[series_id] = hit


	num_s, num_eps = refresh_series(ctx, width, subset=[series_id], max_age=-1)

	# TODO: offer to mark seasons as seen?

	save_series_db(ctx)

	print(f'{_b}Series added:{_00}   {_f}(series list has been renumbered){_00}')

	# need to loop to figure out its list index
	imdb_id = ctx.db[series_id].get('imdb_id')
	index = find_list_index(ctx.db, series_id)
	print_series_title(index, hit, imdb_id=imdb_id, width=width)

	return None


def menu_select(items:list[dict], prompt:str, item_print:Callable, force_selection:int|None=None) -> int|None:
	for idx, item in enumerate(items):
		item_print(idx, item)

	if force_selection is not None:
		return force_selection

	last_num = len(items)
	while True:
		try:
			answer = input(prompt).lstrip('#')
		except (KeyboardInterrupt, EOFError):
			print()
			return None

		try:
			selected = int(answer)
			if selected <= 0 or selected > last_num:
				raise ValueError()
		except ValueError:
			print(f'{_E}*** Bad selection, try again ***{_00}', file=sys.stderr)
			continue

		selected -= 1
		break

	return selected


def _add_help() -> None:
	print_cmd_usage('add', '<title search> [<year>]')

setattr(cmd_add, 'help', _add_help)


def cmd_search(ctx:context, width:int) -> str | None:
	return cmd_add(ctx, width, add=False)

def _search_help() -> None:
	print_cmd_usage('search', '<title search> [<year>]')

setattr(cmd_search, 'help', _search_help)


def cmd_delete(ctx:context, width:int) -> str | None:
	if not ctx.command_arguments:
		return 'Required argument missing: # / <IMDb ID>'

	index, series_id, series, err = find_series(ctx.db, ctx.command_arguments.pop(0))
	if err is not None or series is None:
		return err

	print(f'{_b}Deleting series:{_00}')
	print_series_title(None, series, imdb_id=series.get('imdb_id'), width=width)

	seen, unseen = seen_unseen_episodes(series)
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
		return 'Cancelled'

	if answer in ('a', full_answer_a):
		return cmd_archive(ctx, width)  # also checks for abandon


	# delete it

	del ctx.db[series_id]
	save_series_db(ctx)

	print(f'{_b}Series deleted:{_b}   {_f}(series list has been renumbered){_00}')
	print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width)

	return None

def _delete_help() -> None:
	print_cmd_usage('delete', '# / <IMDb ID>')
	print(f'    {_o}# / <IMDb ID>{_00}')

setattr(cmd_delete, 'help', _delete_help)

def cmd_mark(ctx:context, width:int, marking:bool=True) -> str | None:
	refresh_series(ctx, width)

	if not ctx.command_arguments:
		return 'Required argument missing: # / <IMDb ID>'

	find_id = ctx.command_arguments.pop(0)

	index, series_id, series, err = find_series(ctx.db, find_id)
	if err is not None or series is None:
		return err

	season:None|range|tuple = None
	episode:None|range|tuple = None

	ep_ptn = re.compile(r'^\s*(s\d+(-\d+)?)(e\d+(-\d+)?)\s*$')

	# supported syntaxes:
	#   nothing:                                (all seasons, all episodes)
	#   single numbers:              1 2        (season 1, episode 2)
	#   ranges:                      1-2 1-5    (seasons 1-2, episodes 1-5)
	#   season descriptor:           s1         (season 1, all episodes)
	#   "descriptor":                s1e2       (season 1, episode 2)
	#   "descriptor" spaces:         s1 e2      (season 1, episode 2)
	#   "descriptor" ranges:         s1-3e1-4   (seasons 1-3, episodes 1-4)
	#   "descriptor" spaced ranges:  s1-3 e1-4  (seasons 1-3, episodes 1-4)

	args = [*ctx.command_arguments]
	if args:
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
				season = (int(rng[0]), )
		except ValueError as ve:
			return f'Bad season number/range: {season}'

	if args:
		episode_str = args.pop(0)

		try:
			rng = [int(n) for n in episode_str.lower().lstrip('e').split('-')]
			if len(rng) == 2:
				episode = range(min(rng), max(rng) + 1)
			else:
				episode = (int(rng[0]), )
		except:
			return f'Bad episode number/range: {episode}'

	seen = get_meta(series, 'seen', {})

	episodes = []
	episodes_runtime = 0

	for ep in series.get('episodes', []):
		if (season is None or ep['season'] in season) and (episode is None or ep['episode'] in episode):
			key = _ep_key(ep)

			if marking and key not in seen:
				seen[key] = now()
				episodes.append(ep)
				episodes_runtime += ep.get('runtime') or 0

			elif not marking and key in seen:
				del seen[key]
				episodes.append(ep)
				episodes_runtime += ep.get('runtime') or 0

	if not episodes:
		print(f'{_c}No episodes %smarked{_00}' % ('' if marking else 'un'))
		return None

	if marking:
		print('Marked ', end='')
	else:
		print('Unmarked ', end='')

	print(f'{_c}{len(episodes)}{_00}', end='')
	print(f' episode{_plural(episodes)} as seen:  {_00}{_f}{fmt_duration(episodes_runtime)}{_00}')

	print_series_title(index, series, width, imdb_id=series.get('imdb_id'))

	# TODO: print series title first and then just the episode titles

	for ep in episodes:
		print('  %s' % format_episode_title(None, ep, include_season=True, width=width - 2))

	is_archived = has_meta(series, 'archived')

	if marking and series.get('status') in ('ended', 'canceled') and not is_archived:
		seen, unseen = seen_unseen_episodes(series)
		if not unseen:
			print()
			print(f'{_c}Last episode marked of %s series.{_00}' % series['status'])
			ctx.command_arguments = [find_id]
			return cmd_archive(ctx, width)

	elif not marking and is_archived:
		print()
		print(f'{_c}Unmarked episode of archived series.{_00}')
		ctx.command_arguments = [find_id]
		return cmd_restore(ctx, width)

	save_series_db(ctx)

	return None

def _mark_help() -> None:
	print_cmd_usage('mark', '# / <IMDb ID> [<season / episode specifier>]')
	print(f'    {_o}# / <IMDb ID> <season> <episode> {_00} Episodes')
	print(f'    {_o}# / <IMDb ID> <season>           {_00} Seasons')
	print(f'    {_o}# / <IMDb ID>                    {_00} Whole series')
	print('Also support ranges:')
	print('  > %s .mark 42 1 1-5' % PRG)
	print('And episode specifiers (with ranges):')
	print('  > %s unmark 42 s1e1-5' % PRG)

setattr(cmd_mark, 'help', _mark_help)


def cmd_unmark(*args, **kwargs):
	return cmd_mark(*args, **kwargs, marking=False)

def _unmark_help() -> None:
	print_cmd_usage('unmark', '# / <IMDb ID> [<season / episode specifier>]')
	print(f'    {_o}# / <IMDb ID> <season> <episode> {_00} Episodes')
	print(f'    {_o}# / <IMDb ID> <season>           {_00} Seasons')
	print(f'    {_o}# / <IMDb ID>                    {_00} Whole series')
	print('Also support ranges:')
	print('  > %s unmark 42 1 1-5' % PRG)
	print('And episode specifiers (with ranges):')
	print('  > %s unmark 42 s1e1-5' % PRG)

setattr(cmd_unmark, 'help', _unmark_help)


def cmd_archive(ctx:context, width:int, archiving:bool=True) -> str | None:
	if not ctx.command_arguments:
		return 'Required argument missing: # / <IMDb ID>'

	find_id = ctx.command_arguments.pop(0)

	index, series_id, series, err = find_series(ctx.db, find_id)
	if err is not None or series is None:
		return err

	currently_archived = has_meta(series, 'archived')


	if archiving == currently_archived:
		# TODO: better presentation of title
		if archiving:
			return 'Already archived: %s' % series['title']
		else:
			return 'Not archived: %s' % series['title']

	seen, unseen = seen_unseen_episodes(series)
	partly_seen = seen and unseen

	if archiving:
		print(f'{_b}Series archived', end='')
		if partly_seen:
			print(' (abandoned)', end='')
		print(f':{_00}')
		set_meta(series, 'archived', now())

	else:
		print(f'{_b}Series restored', end='')
		if partly_seen:
			print(' (resumed)', end='')
		print(f':{_00}')
		del_meta(series, 'archived')

	print_series_title(index, series, imdb_id=series.get('imdb_id'), width=width)

	save_series_db(ctx)

	return None

def _archive_help() -> None:
	print_cmd_usage('archive', '# / <IMDb ID>')
	print(f'    {_o}# / <IMDb ID>{_00}')

setattr(cmd_archive, 'help', _archive_help)


def cmd_restore(*args, **kwargs) -> str|None:
	kwargs['archiving'] = False
	return cmd_archive(*args, **kwargs)

def _restore_help() -> None:
	print_cmd_usage('restore', '# / <IMDb ID>')
	print(f'    {_o}# / <IMDb ID>{_00}')

setattr(cmd_restore, 'help', _restore_help)


def cmd_refresh(ctx:context, width:int) -> str|None:

	max_age = ctx.command_options.get('max-age', default_max_refresh_age)
	if max_age <= 0:
		max_age = config_int('max-age')

	forced = bool(ctx.command_options.get('refresh:force'))

	find_idx, match = find_idx_or_match(ctx.command_arguments)
	series_list = get_series(ctx.db, archived=False, index=find_idx, match=match)

	subset = [series_id for index, series_id in series_list]

	if not subset:
		return 'Nothing matched: %s' % (match.pattern if match else find_idx)

	t0 = time.time()

	num_series, num_episodes = refresh_series(ctx, width, subset=subset, max_age=max_age if not forced else -1)
	if not num_episodes:
		return 'Nothing to update (max age: %d days)' % (max_age/(3600*24))

	if num_series > 0:  # can be 1 even if num_episodes is zero
		if num_episodes > 0:
			print(f'{_f}Refreshed %d episodes across %d series [%.1fs].{_00}' % (num_episodes, num_series, time.time() - t0))

		save_series_db(ctx)

	return None


def _refresh_help() -> None:
	print_cmd_usage('refresh', '# / <IMDb ID> {_o}|{_n} <pattern>')
	print(f'    {_o}[# / <IMDb ID>]     {_00} Only the specified series')
	print(f'    {_o}[<pattern>]         {_00} Only matching series')

setattr(cmd_refresh, 'help', _refresh_help)


def cmd_config(ctx:context, width:int) -> str|None:
	return 'Not implemented'

def _config_help() -> None:
	print_cmd_usage('config', '<args>')

setattr(cmd_config, 'help', _config_help)


def cmd_help(*args, **kw):
	print_usage()

def _help_help() -> None:
	print_cmd_usage('help')

setattr(cmd_help, 'help', _help_help)


def get_meta(series:dict, key: str, def_value=None) -> Any:
	return series.get(meta_key, {}).get(key, def_value)

def has_meta(series:dict, key: str) -> bool:
	return get_meta(series, key, None) is not None

def set_meta(series:dict, key: str, value) -> None:
	series[meta_key][key] = value

def del_meta(series:dict, key: str) -> None:
	series[meta_key].pop(key, None)


PRG = basename(sys.argv[0])

default_max_refresh_age = 2  # days
default_max_hits = 10

default_configuration = {
		'paths': {
				'series-db': None,  # defaulted in load_config()
		},
		'commands': {
				'default': 'unseen',
				'calendar': {
					'num_weeks': 1,
				},
		},
		'max-age': default_max_refresh_age,
		'lookup': {
				'api-key': None,
				'max-hits': default_max_hits,
		},
		'debug': 0,
}

# type alias for type hints (should be recursive, but mypy doesn't support it)
ConfigValue = str|int|float|dict|list

def config_get(path:str, default_value:ConfigValue|None=None, convert=None) -> ConfigValue|None:
	# path: key/key/key
	keys = path.split('/')

	scope:dict|list|str|int|float|None = app_config
	current:list[str] = []
	for key in keys:
		# print('cfg: %s + %s' % ('/'.join(current), key))
		if not isinstance(scope, dict):
			raise RuntimeError('Invalid path "%s"; not object at "%s", got %s (%s)' % (path, '/'.join(current), scope, type(scope).__name__))

		scope = scope.get(key)
		if scope is None:
			break

		current.append(key)

	if scope is None:
		scope = default_value

	if convert is not None:
		scope = convert(scope)

	return scope

def config_int(path:str, default_value:int=0) -> int|None:
	return int(config_get(path, default_value or 0))

def config_bool(path:str, default_value:int=False) -> bool|None:
	return bool(config_get(path, default_value or False))


def config_set(path:str, value:Any) -> None:
	keys = path.split('/')

	ValueType = dict[str, Any]|list|str|int|float|None  # mypy doesn't support recursive type hints

	scope:ValueType = app_config
	if not isinstance(scope, dict): # to shut mypy up
		return None

	current:list[str] = []
	while keys:
		key = keys.pop(0)

		if not keys:  # leaf key
			scope[key] = value
			break

		new_scope = scope.get(key)
		if new_scope is None:  # missing key object
			scope[key] = {}

		if not isinstance(new_scope, dict): # exists, but is not an object
			raise RuntimeError('Invalid path "%s"; not object at "%s", got %s (%s)' % (path, '/'.join(current), scope, type(new_scope).__name__))

		scope = new_scope
		current.append(key)


# known commands with aliases
known_commands = {
	'search':  { 'alias': ('s', ),      'handler': cmd_search,   'help': 'Search for a series.' },
 	'add':     { 'alias': ('a', ),      'handler': cmd_add,      'help': 'Search for a series and (optionally) add it.' },
 	'delete':  { 'alias': (),           'handler': cmd_delete,   'help': 'Completely remove a series - permanently!' },
 	'show':    { 'alias': ('list', 'ls'), 'handler': cmd_show,   'help': 'Show/list series'},
	'calendar': { 'alias': (),          'handler': cmd_calendar, 'help': 'Show episode releases by date' },
	'unseen':  { 'alias': ('u', 'us'),  'handler': cmd_unseen,   'help': 'Show unseen episodes of series' },
	'mark':    { 'alias': ('m', ),      'handler': cmd_mark,     'help': 'Mark a series, season or specific episode as seen.' },
	'unmark':  { 'alias': ('M', 'um'),  'handler': cmd_unmark,   'help': 'Unmark a series/season/episode - reverse of mark command.' },
	'archive': { 'alias': ('A', ),      'handler': cmd_archive,  'help': 'Archving series - hides from normal list command.' },
	'restore': { 'alias': ('R', ),      'handler': cmd_restore,  'help': 'Restore series - reverse of archive command.' },
	'refresh': { 'alias': ('r', ),      'handler': cmd_refresh,  'help': 'Refresh episode data of all non-archived series.' },
	'config':  { 'alias': (),           'handler': cmd_config,   'help': 'Configure.' },
	'help':    { 'alias': (),           'handler': cmd_help,     'help': 'Shows this help page.' },
}


def _set_debug(value):
	config_set('debug', bool(value))

def _valid_int(a:int, b:int) -> Callable[[int], bool]:
	assert(a <= b)
	def verify(v:int):
		return v >= a and v <= b
	verify.__doc__ = 'between %d and %d' % (a, b)
	return verify

# TODO: merge with 'known_commands' ?  (at least for the command-specific options)

__opt_max_hits = {
	'name': ( '-n',),
	'arg': int,
	'validator': _valid_int(1, 40),
	'help': 'Limit number of hits [1-40] (default: %d)' % default_max_hits,
}

command_options = {
	None: { # i.e. global options
		'debug': { 'name': ('--debug',),  'help': 'Enable debug mode', 'func': _set_debug },
	},
	'show': {
		'show:all':           { 'name': ('-a', '--all'),         'help': 'List also archived series' },
		'show:archived':      { 'name': ('-A', '--archived'),    'help': 'List only archived series' },
		'show:started':       { 'name': ('-s', '--started'),     'help': 'List only series with seen episodes' },
		'show:planned':       { 'name': ('-p', '--planned'),     'help': 'List only series without seen episodes' },
		'show:all_episodes':  { 'name': ('-e', '--episodes'),    'help': 'Show all unseen episodes (not only first)' },
		'show:seen_episodes': { 'name': ('-S', '--seen'),        'help': 'Show seen episodes' },
		'show:abandoned':     { 'name': '--abandoned',           'help': 'List only abandoned series' },
		'show:details':       { 'name': ('-I', '--details'),     'help': 'Show more details' },
		'show:director':      { 'name': '--director', 'arg': str, 'help': 'Filter by director, substring match' },
		'show:writer':        { 'name': '--writer',  'arg': str, 'help': 'Filter by writer, substring match' },
		'show:cast':          { 'name': '--cast',    'arg': str, 'help': 'Filter by cast, substring match' },
		'show:year':          { 'name': '--year',    'arg': str, 'help': 'Filter by year, <start>[-<end>]' },
	},
	'unseen': {
		'unseen:future':         { 'name': ('-f', '--future'),        'help': 'Show also future/unreleased episodes' },
		#'unseen:not_future':     { 'name': ('+f', '--not-future'),    'help': 'Don\'t show future/unreleased episodes' },
		'unseen:started':        { 'name': ('-s', '--started'),       'help': 'List only series with seen episodes' },
		'unseen:planned':        { 'name': ('-p', '--planned'),       'help': 'List only series without seen episodes' },
		'unseen:all_episodes':   { 'name': ('-e', '--episodes'),      'help': 'Show all unseen episodes (not only first)' },
		#'unseen:1st_episodes':   { 'name': ('+e', '--first-episode'), 'help': 'Show only first unseen episodes' },
	},
	'refresh': {
		'refresh:force': { 'name': ('-f', '--force'),         'help': 'Refresh whether needed or not' },
		'max-age':       { 'name': '--max-age',  'arg': int,  'help': 'Refresh older than N days (default: %s)' % default_max_refresh_age },
	},
	'add': {
		'search:max-hits': __opt_max_hits,
	},
	'search': {
		'search:max-hits': __opt_max_hits,
	}
}


def find_series(db:dict, find_id:str) -> tuple[int | None, str | None, dict | None, str | None]:
	nothing_found = None, None, None, f'Series not found: {find_id}'

	# if it starts with 'tt' (and rest numerical), search by IMDb ID
	# else search listing index (as dictated by get_series())

	if not find_id:
		return nothing_found

	try:
		find_index = int(find_id)
	except:
		find_index = None
		if find_id[0] == 'tt':
			find_id = find_id[1:]
		else:
			return nothing_found

	for index, series_id in get_series(db):
		series = db[series_id]
		if find_index is not None and find_index == index:
			return index, series_id, series, None
		elif series.get('imdb_id') == find_id:
			return index, series_id, series, None

	return nothing_found


def find_list_index(db, series_id):
	for index, sid in get_series(db):
		if sid == series_id:
			return index
	return None


def is_released(target, fallback=True):
	release_date = target.get('date')
	if release_date is None:
		return fallback

	# already released or will be today
	return date.fromisoformat(release_date) <= today_date


def print_episodes(series:dict, episodes:list[dict], width:int, pre_print:Callable|None=None, also_future=False) -> list[str]:

	seen, unseen = seen_unseen_episodes(series)
	seen_keys = {_ep_key(ep) for ep in seen}

	indent = 6  # nice and also space to print the season "grouping labels"
	current_season = 0
	margin = 1

	ep_width = width - indent - margin

	keys:list[str] = []

	for ep in episodes:

		if pre_print:
			pre_print()
			pre_print = None  # only once

		has_seen = _ep_key(ep) in seen_keys

		s = format_episode_title(None, ep, width=ep_width, today=True, seen=has_seen)

		season = ep['season']
		if season != current_season:
			print(f'{_c}%{indent}s{_0}\r' % (f's%d' % season), end='')
			current_season = season

		# use cursor move instead of writing spaces, so we don't overwrite the season label
		print(f'\x1b[{indent + margin}C{s}')

		keys.append(_ep_key(ep))

		if not (also_future or is_released(ep)):
			break

	return keys


def find_idx_or_match(args, director:re.Pattern|None=None, writer:re.Pattern|None=None, cast:re.Pattern|None=None, year:list[int]|None=None):

	# print('FILTER title/idx:', (_c + ' '.join(args) + _0fg) if args else 'NONE')
	# print('        director:', (_c + director.pattern + _0fg) if director else 'NONE')
	# print('          writer:', (_c + writer.pattern + _0fg) if writer else 'NONE')
	# print('            cast:', (_c + cast.pattern + _0fg) if cast else 'NONE')
	# print('            year:', (_c + '-'.join(year) + _0fg) if year else 'NONE')


	if not args and director is None and writer is None and cast is None and year is None:
		return None, None

	try:
		if not args:
			raise ValueError()

		find_id = int(args[0])
		# wr're looking tor aa single entry, by ID: other arguments are irrelevant
		return find_id, None

	except ValueError:
		title = None
		if args:
			title = re.compile('.*?'.join(re.escape(a) for a in ' '.join(args).split()), re.IGNORECASE)

		# print('FILTER     title:', (_c + title.pattern + _0fg) if title else 'NONE')
		# print('        director:', (_c + director.pattern + _0fg) if director else 'NONE')
		# print('          writer:', (_c + writer.pattern + _0fg) if writer else 'NONE')
		# print('            cast:', (_c + cast.pattern + _0fg) if cast else 'NONE')
		# print('            year:', (_c + '-'.join(year) + _0fg) if year else 'NONE')

		# TODO: function should also take list index: (list_index, series) -> bool

		def match(series):
			ok = True
			if title:
				ok = title.search(series['title']) is not None
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
			'director': director.pattern if director else None,
			'writer': writer.pattern if writer else None,
			'cast': cast.pattern if cast else None,
			'year': '-'.join(str(y) for y in year) if year else None,
		}
		match.description = ' '.join('%s=%s' % (n, v) for n, v in filter_parts.items() if v)
		match.styled_description = _c + ' '.join(f'%s{_g}={_0}{_b}%s{_0}' % (n, v) for n, v in filter_parts.items() if v)

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
		keys_to_index[_ep_key(ep)] = idx

	return [
		episodes[keys_to_index[key]]
		for key in keys
	]


def no_series(db:dict, filtering:bool=False) -> str:
	num_archived = series_num_archived(db)
	suffix = f'Use: {_b}%s add <title search...> [<year>]{_00}' % PRG
	precision = 'matched ' if filtering else ''
	if num_archived:
		return 'No series %s[%d archived]. %s' % (precision, num_archived, suffix)
	else:
		return 'No series added. %s' % suffix


def refresh_series(ctx:context, width:int, subset:list|None=None, max_age:int|None=None) -> tuple[int, int]:

	db = ctx.db

	subset = subset or list(db.keys())
	max_age = (max_age or config_int('max-age'))*3600*24

	forced = max_age < 0

	# print('max_age:', max_age, forced)

	to_refresh = {}

	now_dt = now_datetime()
	def age(dt):
		return (now_dt - datetime.fromisoformat(dt)).total_seconds()

	earliest_refresh = None  # can never be earlier than this

	for series_id in subset:
		series = db[series_id]
		last_refresh = get_meta(series, updated_key)

		if forced or (not last_refresh or age(last_refresh) > max_age):
			last_refresh = last_refresh or now()
			to_refresh[series_id] = last_refresh

			if not earliest_refresh or last_refresh < earliest_refresh:
				earliest_refresh = last_refresh

	if not to_refresh:
		return 0, 0

	touched = 0
	if not forced:
		print(f'\r{_f}Checking for updates (%d series)...{_00}{_K}' % len(to_refresh), end='', flush=True)

		prog_bar = new_progress(len(to_refresh), width=width - 2)
		completed = 0
		def show_progress(*_):
			nonlocal completed
			completed += 1
			print(f'\r{_K}%s{_EOL}' % prog_bar(completed, text='Checking updates...'), end='', flush=True)

		to_refresh_keys = list(to_refresh.keys())
		changes = tmdb.changes(to_refresh_keys, datetime.fromisoformat(earliest_refresh), ignore=ignore_changes, progress=show_progress)

		print(f'\r{_K}', end='', flush=True)

		for series_id, changes in zip(to_refresh_keys, changes):
			if not changes:
				# to_refresh.remove(series_id)
				del to_refresh[series_id]
				# remember last update check
				set_meta(db[series_id], updated_key, now())
				touched += 1

	if not to_refresh:
		if touched:
			return touched, 0  # only series affected, no episodes
		return 0, 0

	print(f'{_f}Refreshing %d series...{_00}' % len(to_refresh), end='', flush=True)

	prog_bar = new_progress(len(to_refresh), width=width - 2)
	completed = 0
	def show_progress(*_):
		nonlocal completed
		completed += 1
		print(f'\r{_00}{_K}%s{_EOL}' % prog_bar(completed, text='Refreshing...'), end='', flush=True)

	to_refresh_keys = list(to_refresh.keys())
	result = tmdb.episodes(to_refresh_keys, with_details=True, progress=show_progress)
	# 'result' is a list of (details, episodes)-tuples

	print(f'\r{_00}{_K}', end='', flush=True)

	num_episodes = 0
	now_time = now()

	for series_id, (details, episodes) in zip(to_refresh_keys, result):
		series = details
		series['episodes'] = episodes
		series[meta_key] = db[series_id].get(meta_key, {})

		set_meta(series, updated_key, now_time)

		db[series_id] = series

		num_episodes += len(episodes)


	if to_refresh:
		save_series_db(ctx)

	return len(to_refresh), num_episodes


def print_series_title(num:int|None, series:dict, width:int=0, imdb_id:str=None, gray:bool=False, tail: str|None=None, tail_style:str|None=None) -> None:

	# this function should never touch the BG color

	left = ''  # parts relative to left edge (num, title, years)
	right = ''  # parts relative to right edge (IMDbID, tail)
	if num is not None:
		num_w = 5
		width -= num_w

		left = f'\x1b[3;38;2;200;160;100m{num:>{num_w}}{_0}'

	if 'year' in series:
		year_a = str(series['year'][0])
		year_b = series['year'][1] if len(series['year']) > 1 else ''
		years = '  (%s-%s)' % (year_a, year_b)
		width -= len(years)
		years = f'\x1b[38;5;245m{years:<11}{_0}'
	else:
		years = ''

	#added = get_meta(infop, 'added').split()[0]  # add date
	#s = f' {_g}%(added)s{_0fg}  \x1b[38;5;253m%(title)s{_0fg}  \x1b[38;5;245m%(year)-9s{_0fg}' % infop

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

	title = series['title']
	if len(title) > width:
		# elipt title if too wide
		width -= 1
		title = title[:width] + '…'

	left += f' \x1b[38;5;253m{title}{_0}{years}'

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

	# print('width 0:  ', width)

	episode_title_margin = 1

	ep = episode

	season = ep['season']
	episode = ep['episode']
	if include_season:
		s_ep_max_w = len('s99e999')
		s_ep_w = len(f's{season}e{episode:02}')
	else:
		s_ep_max_w = len('e999')
		s_ep_w = len(f'e{episode:02}')

	# left-pad to fill the max width
	left_pad = ' '*(s_ep_max_w - s_ep_w)
	if include_season:
		season_ep = f'\x1b[33ms{_b}{season}{_0}\x1b[33me{_b}{episode:02}'
	else:
		season_ep = f'\x1b[33me{_b}{episode:02}'

	season_ep = f'{left_pad}{_0}{season_ep}{_0}'
	width -= s_ep_max_w + episode_title_margin

	# print('width S.E:', width, len(left_pad), s_ep_w, s_ep_max_w)

	# Depending on episode release date:
	#   in the future    -> show how long until release (or nothing if only_released=True)
	#   in th past       -> show the date
	#   same date as now -> show 'TODAY'


	ep_date = ep.get('date')

	future = False
	if isinstance(ep_date, str):
		# ep['date'] = '2026-11-11'
		# ep['date'] = (now_datetime().date() + timedelta(days=-2)).isoformat()

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
	#   show like "2 weeks ago"
	#   do note that this is longer/wider (use "wks"/"mons" ?)

	# print('date:', ep['date'])
	# print('future:', future)
	# print('today:', today)

	ep_time_w = len('999 months')  # the longest variant of date or duration
	ep_time = None
	time_style = ''
	if future:
		ep_time = f'{dt}'
		time_style = _b

		if diff > 24*3600:  # longer than 24 hours
			ep_time = fmt_duration(diff, roughly=True)
			time_style = '\x1b[38;5;244m'

	elif today:
		ep_time = f'TODAY'
		time_style = _g

	elif isinstance(ep_date, str):
		ep_time = f'{ep_date}'
		time_style = ''

	# print('width 2:', width)

	if not ep_time or not include_time:
		ep_time = ''
		ep_time_w = 0

	if ep_time:
		width -= 1 + ep_time_w
		ep_time = f' {time_style}{ep_time:>{ep_time_w}}{_0}'
		#ep_time = '|' + 'T'*ep_time_w
	# ep_time = ''

	# print('width TIM:', width, ep_time_w)

	runtime = ep.get('runtime')
	if runtime and isinstance(runtime, int):
		runtime_str = ' %dmin' % runtime  # could use fmt_duration() but we only want minutes here
		#runtime_str = 'r'*10
		width -= len(runtime_str)
	else:
		runtime_str = ''

	# print('width RT: ', width)

	# print('width 3:', width)

	s = ''
	if prefix and prefix is not None:
		s += f'{prefix}'
		width -= len(prefix)

	# print('width 4:', width)

	#ep['title'] = 'N'*(width + 3)

	# not enough space: truncate & ellipt
	if len(ep['title']) > width:
		width -= 1
		ep['title'] = ep['title'][:width] + '…'
		# TODO: to fancy fade to black at the end ;)

	# print('width 5:', width)

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
	print(f'    {_o}Overview:{_0} ', end='')
	for idx, line in enumerate(overview):
		if idx == 0:
			line = line[15:]
		print(line)

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

	writers = Counter(all_writers)
	writers = [name for name, _ in writers.most_common(5)]
	directors = Counter(all_directors)
	directors = [name for name, _ in directors.most_common(5)]
	guests = Counter(all_guests)
	guests = [name for name, _ in guests.most_common(10)]

	if directors:
		print(f'    {_o}Directors:{_0}', f'{_o},{_0} '.join(directors))
	if writers:
		print(f'    {_o}Writers:{_0}  ', f'{_o},{_0} '.join(writers))
	if series.get('cast'):
		print(f'    {_o}Cast:{_0}     ', f'{_o},{_0} '.join(series['cast']))
	if guests:
		print(f'    {_o}Guests:   {_0}', f'{_o},{_0} '.join(guests))

	num_seasons = max(ep.get('season',0) for ep in episodes)
	print(f'    {_o}Seasons: {_0}', num_seasons, end='')
	print(f'  {_f}/{_0}  {_o}Episodes: {_0}', len(episodes))
	for season in range(1, num_seasons + 1):
		print(f'     {_c}{"s%d" % season:>3}{_0}', '%3d' % len(list(filter(lambda ep: ep.get('season') == season, episodes))), 'episodes')


def print_archive_status(series:dict) -> None:
	if has_meta(series, 'archived'):
		print(f'{_f}       Archived', end='')
		seen, unseen = seen_unseen_episodes(series)
		if seen and unseen:  # some has been seen, but not all
			print(' / Abandoned', end='')
		print('  ', get_meta(series, 'archived').split()[0], end='')
		print(f'{_0}')


def fmt_duration(seconds: int|float, roughly: bool=False):
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
		parts.append(templ % (months, unit['m'], _plural(months if roughly else 1)))
	elif weeks > 0:
		parts.append(templ % (weeks, unit['w'], _plural(weeks if roughly else 1)))

	if not roughly or (not months and not weeks):
		if days > 0:
			parts.append(templ % (days, unit['d'], _plural(days if roughly else 1)))

	if not roughly:
		if hours > 0:
			parts.append(templ % (hours, unit['h'], _plural(hours if roughly else 1)))
		if minutes or (hours > 0 or seconds > 0):
			parts.append(templ % (minutes, unit['min'], _plural(minutes if roughly else 1)))
		if seconds:
			parts.append(templ % (seconds, unit['s'], _plural(seconds if roughly else 1)))

	return ' '.join(parts)


def new_progress(total:int, width:int, color:int|str|None=None, bg_color:int|str=4, text_color:str|int|None=None, fmt_info:Callable|None=None):
	#print(f'new_progress: total:{total} width:{width} bg_color:{bg_color} text_color:{text_color} fmt_info:{fmt_info}')

	bar_ch = ('▏', '▎', '▍', '▌', '▋', '▊', '▉')

	info_width = len(str(total))
	if fmt_info is None:
		def fmt_info(c, t):
			return f'%{info_width}s/%-{info_width}s' % (c, t)

	CLR = '\x1b[K'  # clear to end-of-line
	INV = '\x1b[7m' # video inversion
	RST = '\x1b[m'  # reset all attributes
	DIM = '\x1b[2m' # faint/dim color
	SAV = '\x1b[s'  # save cursor position
	LOAD = '\x1b[u'  # restore saved cursor position


	b0 = ''
	b1 = RST
	bh = f'\x1b[4{bg_color}m'
	t0 = ''
	t1 = b0

	if color is not None:
		b0 = f'\x1b[3{color}m'  # w/ inversion
		bh = b0 + bh            # no inversion
		t0 = b0

	if text_color is not None:
		if color:
			t0 = f'\x1b[4{text_color};3{color}m'  # w/ inversion
		else:
			t0 = f'\x1b[4{text_color}m'           # w/ inversion


	def _replace_reps(s, find, repl):
		ptn = re.compile(r'(%s+)' % find)

		def replacer(m):
			count = len(m.group(1))/len(find)
			return repl % { 'n': count, 's': m.group(1) }

		return ptn.sub(replacer, s)

	left_margin = 1
	left_pad = ' '*left_margin
	right_margin = 1
	right_pad = ' '*right_margin

	def gen(curr, text=None):
		ltotal = total
		lwidth = width

		# if 'curr' is a string, show an "indeterminate" progress bar
		if isinstance(curr, str):
			text = curr
			curr = None
			ltotal = None

		#print(f'new_progress.gen: curr:{curr} text:{text}')

		if curr is None or ltotal is None:  # indeterminate progress bar
			percent = f'{DIM}{"?":4}{RST}'
			bar_w = lwidth
			info = '?'

		else:
			pct_w = 4 + left_margin  # ' 42% '
			progress = curr/ltotal
			percent = '%3.0f%%' % (100*progress)
			info = fmt_info(curr, ltotal)
			lwidth -= pct_w + right_margin + len(info)
			bar_w = progress*lwidth

		# widths of completed (head) and remaining (tail) segments
		int_w = int(bar_w)
		head = bar_ch[int((bar_w % 1)*len(bar_ch))]
		tail_w = lwidth - int_w - 1
		# print('int_w:', int_w)

		opt_text = ''
		if text:
			text_done = _replace_reps(text[:int(bar_w)], ' ', '\x1b[%(n)dC')
			text_todo = _replace_reps(text[int(bar_w):], ' ', '\x1b[%(n)dC')

			opt_text = ''
			if text_done:
				opt_text += f'{INV}{t0}{text_done}{t1}'
			if text_todo:
				opt_text += f'{RST}{bh}{text_todo}'
			if opt_text:
				opt_text += LOAD

		last_bar = ''.join([
				CLR,
				percent,
				left_pad,
				# completed bar segments
				(f'{INV}{SAV}{b0}%{int_w}s{b1}' % '') if int_w else '',
				# the "head" segment
				f'{bh}{head}',
				# remaining bar segments
				(f'%{tail_w}s' % '') if tail_w else '',
				LOAD,
				opt_text,          # ends with LOAD if non-empty
				f'\x1b[{lwidth}C',  # move to right edge
				RST,
				right_pad,
				# display "info"
				DIM, info, RST,
		])
		#print('BAR:', last_bar.replace('\x1b', 'Σ').replace('\r', 'ΣR').replace('Σ', '\x1b[35;1mΣ\x1b[m'))
		return last_bar

	gen.__name__ = 'progress_bar'
	gen.__doc__ = '''Return a rendered progress bar at 'curr' (of 'total') progress.'''
	gen.total = total
	gen.width = width

	return gen


def strip_ansi(s: str):
	return re.sub('\x1b\\[[0-9;]*[mJ]', '', s)


def _ep_key(episode:dict):
	return f'{episode["season"]}:{episode["episode"]}'


def print_seen_status(series:dict, gray: bool=False, summary=True, next=True, last=True, width:int=0):
	ind = '       '

	seen, unseen = seen_unseen_episodes(series)
	all_seen = seen and len(seen) == len(series.get('episodes', []))

	s = ''

	if summary and (seen or unseen):
		s += f'\x1b[38;5;256m{ind}'

		if seen:
			seen_duration = sum((ep.get('runtime') or 0) for ep in seen)*60
			s += f'Seen: {len(seen)} {_f}{fmt_duration(seen_duration)}{_0}'
			if all_seen:
				s += f'  {_g}ALL{_0}'

		if seen and unseen:
			s += f' {_o}-{_0} '

		if unseen:
			unseen_duration = sum((ep.get('runtime') or 0) for ep in unseen)*60
			s += f'Unseen: {len(unseen)} {_f}{fmt_duration(unseen_duration)}{_0}'

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
		print(format_episode_title('', seen[-1], gray=gray, include_season=True, width=width - len(header)))

	if next and unseen:
		header = f'{ind}Next: '
		s = format_episode_title('', unseen[0], gray=gray, include_season=True, width=width - len(header))
		if s:
			if gray:
				print(_f, end='')
			print(f'{header}{s}')


def series_num_archived(db:dict) -> int:
	return sum(1 if has_meta(series, 'archived') else 0 for series in db.values())


def get_series(db:dict, archived:bool|None=None, index=None, match=None) -> list[tuple[int, str]]:
	series_ids = sorted(db, key=lambda sid: (db[sid]['title'].casefold(), db[sid].get('year', '')))

	series_list:list[tuple[int, str, dict]] = []

	find_index = index
	index = 0

	for series_id in series_ids:
		index += 1
		series = db[series_id]

		is_archived = has_meta(series, 'archived')
		if archived is not None and is_archived != archived:
			continue

		if find_index is not None:
			if find_index != index:
				continue

		elif match and not match(series):
			continue

		series_list.append( (index, series_id) )

	return series_list


def seen_unseen_episodes(series:dict, before=None) -> tuple[list,list]:
	episodes = series.get('episodes', [])
	seen = get_meta(series, 'seen', {})

	seen_eps = []
	unseen_eps = []

	for ep in episodes:
		if _ep_key(ep) in seen:
			seen_eps.append(ep)
		else:
			# only include episodes that are already available in 'unseen'
			dt = ep.get('date')
			if not dt:
				continue
			dt = datetime.fromisoformat(ep.get('date'))
			if before and dt > before:
				continue

			unseen_eps.append(ep)

	return seen_eps, unseen_eps


def term_width() -> int:
	try:
		return int(os.popen('stty size', 'r').read().split()[1])
	except:
		return 100


def option_def(command:str, option:str|None=None):
	cmd_opts = command_options.get(command)

	if not isinstance(cmd_opts, dict) or not cmd_opts:
		return None

	if option is None:
		return cmd_opts

	for key, opt in cmd_opts.items():
		if option in opt['name']:
			return { 'key': key, **opt }

	return None


def print_cmd_usage(command:str, syntax:str) -> None:
	summary = known_commands[command].get('help')
	if summary:
		print(_b + summary + _00)
	print(f'Usage: %s {_c}%s{_00} %s' % (PRG, command, syntax))


def print_cmd_option_help(command:str) -> None:
	options = option_def(command)
	if options:
		print(f'{_b}Options:{_00}')
		for opt in options.values():
			option = opt.get('name')
			if type(option) is tuple:
				option = ', '.join(option)

			arg_type = opt.get('arg')
			if arg_type is not None:
				arg_string = arg_placeholder(arg_type)
				option = '%s %s' % (option, arg_string)

			text = opt.get('help', '')
			print('   %-20s %s' % (option, text))


def arg_placeholder(arg_type):
	if arg_type is int:
		return 'N'
	if arg_type is float:
		return 'F'
	if arg_type is datetime:
		return 'YYYY-MM-DD'
	if arg_type is not None:
		return 'string'

	raise RuntimeError('argument placeholder type can not be None')


def print_cmd_help_table():

	def hilite_alias(cmd, aliases) -> str:
		highlighted = ''
		for idx, ch in enumerate(cmd):
			matched = filter(lambda a: a.lower() == ch.lower(), aliases)
			try:
				highlighted += f'{_c}{next(matched)}{_00}' + cmd[idx + 1:]
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
	default_command = config_get('commands/default')

	print(f'{_b}%s{_00} / {_b}Ep{_00}isode {_b}M{_00}anager / (c)2022 André Jonsson' % PRG)
	print('Version %s (%s) ' % (VERSION, VERSION_DATE))
	print(f'{_b}Usage:{_00} %s [<{_b}command{_00}>] [{_o}<args ...>{_00}]' % PRG)
	print()
	print(f'Where {_b}<command>{_00} is:  {_f}(one-letter alias highlighted){_00}')
	print_cmd_help_table()
	print(f'  (none)  ▶  {_b}%s{_00}' % default_command)
	print()
	print(f'See: %s {_b}<command> --help{_00} for command-specific help.' % PRG)
	print()
	print('Remarks:')
	print(f'  # = Series listing number, e.g. as listed by the {_b}l{_00}ist command.')
	print(f'  If an argument does not match a command, it will be used as argument to the default command.')
	print(f'  Shortest unique prefix of a command is enough, e.g. "ar"  for "archive".')
	if orjson is not None:
		print(f'  {_f}Using {_b}orjson{_00}{_f} for faster load/save.')
	else:
		print(f'  {_f}Install \'orjson\' for faster load/save{_00}')
	if compressor:
		print(f'  {_f}Using {_b}{compressor["binary"]}{_00}{_f} to compress database backups.')
	if not tmdb.ok():
		print(f'   {_c}NOTE: Need to set TMDb API key (TMDB_API_KEY environment){_00}')
	sys.exit(exit_code)


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
			print(f'{_b}Aliases:{_00} %s' % ', '.join(cmd[1:]))
			return


def warning_prefix(context_name=''):
	if context_name:
		return f'{_c}[{_00}{_b}{PRG} {context_name}{_c}]{_00}'
	return f'{_c}[{_00}{_b}{PRG}{_c}]{_00}'


def bad_cmd(cmd:str) -> None:
	print(f'{warning_prefix()} Unknown command: {_E}%s{_00}' % cmd, file=sys.stderr)
	sys.exit(1)

def bad_opt(command:str, option:str) -> None:
	print(f'{warning_prefix(command)} Unknown option: {option}', file=sys.stderr)
	sys.exit(1)

def bad_opt_arg(command:str, option, arg, arg_type:Callable, explain:str|None=None) -> None:
	print(warning_prefix(command), end='', file=sys.stderr)

	expected = None
	if arg_type is not None:
		expected = arg_type.__name__

	if expected is None:
		print(f' Unexpected argument for {option}: {_b}{arg}{_00}', file=sys.stderr, end='')
	elif arg is None:
		print(f' Required argument missing for {option}', file=sys.stderr, end='')
	else:
		print(f' Bad option argument for {option}: {_b}{arg}{_00}  %s expected' % expected, file=sys.stderr, end='')

	if explain:
		print(',', explain, end='', file=sys.stderr)
	print(file=sys.stderr)

	sys.exit(1)


def ambiguous_cmd(name:str, matching:list[str]) -> None:
	print(f'{warning_prefix()} Ambiguous command: {_E}%s{_00}  matches: %s' % (name, f'{_o},{_00} '.join(sorted(matching))), file=sys.stderr)
	sys.exit(1)


def now() -> str:
	return now_datetime().isoformat(' ', timespec='seconds')


def now_datetime() -> datetime:
	return datetime.now()


app_config = {}

def read_json(filepath) -> dict:
	if pexists(filepath) and psize(filepath) > 1:
		if orjson is not None:
			with open(filepath, 'rb') as fp:
				return orjson.loads(fp.read())
		else:
			with open(filepath, 'r') as fp:
				return json.load(fp)

	return {}


def write_json(filepath, data) -> Exception|None:
	tmp_name = mkstemp(dir=dirname(filepath))[1]
	try:
		if orjson is not None:
			with open(tmp_name, 'wb') as fpo:
				fpo.write(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
		else:
			with open(tmp_name, 'w') as fps:
				json.dump(data, fps, indent=2, sort_keys=True)

		os.rename(tmp_name, filepath)

	except Exception as e:
		os.remove(tmp_name)
		return e

	return None


def load_config() -> bool:
	global app_config
	app_config = read_json(app_config_file)

	config = {**default_configuration}
	config.update(app_config)
	app_config = config

	db_file = config_get('paths/series-db')
	if not db_file or not isinstance(db_file, str):
		# TODO: $XDG_CONFIG_HOME
		config_set('paths/series-db', pexpand(f'$HOME/.config/{PRG}/series'))

	paths = app_config.get('paths', {})
	if not isinstance(paths, dict):
		raise RuntimeError(f'{warning_prefix()} Config key "paths" is not an object')

	for key in paths.keys():
		paths[key] = pexpand(paths[key])

	return len(app_config) > 0


def save_config():
	err = write_json(app_config_file)
	if err is not None:
		print(f'{_E}ERROR{_00} Failed saving configuration: %s' % str(err))



def load_series_db(ctx:context) -> bool:

	db_file = str(config_get('paths/series-db'))

	t0 = time.time()

	db = {}

	if pexists(db_file) and psize(db_file) > 1:
		if orjson is not None:
			with open(db_file, 'rb') as fp:
				db = orjson.loads(fp.read())
		else:
			with open(db_file, 'r') as fp:
				db = json.load(fp)

	t1 = time.time()
	if config_bool('debug'):
		print(f'{_f}[load: %.1fms]{_0}' % ((t1 - t0) * 1000))

	modified = migrate_db(db)

	ctx.db = db
	ctx.db_meta = db.pop(meta_key)

	if modified:
		save_series_db(ctx)

	return True


def migrate_db(db:dict) -> bool:

	modified = False

	# no db meta data, yikes!
	if meta_key not in db:
		db[meta_key] = {}
		modified = True

	db_version = db[meta_key].get('version')

	# 1. migrate legacy series meta data
	fixed_legacy_meta = 0
	# 2. fix incorrectly written value to 'archived'
	fixed_archived = 0

	# remove meta data while migrating
	meta_data = db.pop(meta_key, None)

	for series_id, series in db.items():
		if meta_key not in series:
			series[meta_key] = {
				key: series.pop(key)
				for key in legacy_meta_keys
				if key in series
			}
			fixed_legacy_meta += 1

		if get_meta(series, 'archived') == True:
			# fix all "archived" values to be dates (not booleans)
			seen = get_meta(series, 'seen')
			last_seen = '0000-00-00 00:00:00'
			# use datetime from last marked episode
			for dt in seen.values():
				if dt > last_seen:
					last_seen = dt

			set_meta(series, 'archived', last_seen)
			fixed_archived += 1

	# restore meta data
	db[meta_key] = meta_data

	# if no version exists, set to current version
	if db_version is None:
		db[meta_key]['version'] = DB_VERSION
		print(f'{_f}Set DB version: None -> %s{_0}' % DB_VERSION)
		modified = True

	if fixed_legacy_meta:
		print(f'{_f}Migrated legacy meta-data of %d series{_0}' % fixed_legacy_meta)
		modified = True
	if fixed_archived:
		print(f'{_f}Fixed bad "archived" value of %d series{_0}' % fixed_archived)
		modified = True

	return modified


compressor:dict|None = None
compressors = [
	{
		'binary': 'zstd',
		'args': ['-10', '-q', '-T0'],
		'extension': '.zst',
	},
	{
		'binary': 'lz4',
		'args': ['-9', '-q'],
	},
	{
		'binary': 'gzip',
		'args': ['-8', '-q'],
		'extension': '.gz',
	},
	{
		'binary': 'xz',
		'args': ['-2', '-q', '-T', '0'],
	}
]

import shutil
for method in compressors:
	if shutil.which(method['binary']):
		compressor = method
		break

# TODO: 'mk_backup' should return a waitable promise (so we can do it in parallel with the serialization)
if compressor:
	from subprocess import Popen

	def mk_backup(source:str, destination:str) -> bool:
		if not isinstance(compressor, dict): # redundant, basically to shut mypy up
			return False

		destination += compressor.get('extension', compressor['binary'])

		tmp_name = mkstemp(dir=dirname(source))[1]
		os.rename(source, tmp_name)
		try:
			command_line = [compressor['binary']] + compressor['args']
			# replace "OUTPUT" with destination
			infp = open(tmp_name, 'rb')
			outfp = open(destination, 'wb')
			cmd = Popen(command_line, stdin=infp, stdout=outfp, universal_newlines=False)
			exit_code = cmd.wait()
			# copy file times from source to destination
			file_info = os.stat(tmp_name)
			os.utime(destination, (file_info.st_atime, file_info.st_mtime))
			if exit_code != 0:
				os.rename(tmp_name, destination)
			else:
				os.remove(tmp_name)

		except Exception as e:
			print(f'{_E}ERROR{_00} Failed compressing database backup: %s' % str(e))
			os.rename(tmp_name, destination)
			exit_code = 1

		return exit_code == 0

else:
	def mk_backup(filename:str, destination:str) -> bool:
		os.rename(filename, destination)
		return True

def save_series_db(ctx:context) -> None:

	db_file = str(config_get('paths/series-db'))

	if not pexists(db_file):
		os.makedirs(dirname(db_file), exist_ok=True)

	def backup_name(idx) -> str:
		return '%s.%d' % (db_file, idx)


	# write to a temp file and then rename it afterwards
	tmp_name = mkstemp(dir=dirname(db_file))[1]
	try:
		db = ctx.db
		# put meta data "inline" for saving
		db[meta_key] = ctx.db_meta

		if orjson is not None:
			with open(tmp_name, 'wb') as fpo:
				fpo.write(orjson.dumps(db, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
		else:
			with open(tmp_name, 'w') as fps:
				json.dump(db, fps, indent=2, sort_keys=True)

		# remove the meta data afterwards
		db.pop(meta_key, None)

		# rotate backups
		for idx in range(num_config_backups - 1, 0, -1):
			if pexists(backup_name(idx)):
				os.rename(backup_name(idx), backup_name(idx + 1))

		# current file becomes first backup (<name>.1)
		# TODO: spawn background process to compress to make it appear faster?
		#   might run into (more) race-conditions of course

		# backup existing(old) db file to 'series.1'
		mk_backup(db_file, backup_name(1))

		os.rename(tmp_name, db_file)

	except Exception as e:
		print(f'{_E}ERROR{_00} Failed saving series database: %s' % str(e))
		os.remove(tmp_name)


def _plural(n: int | list | tuple | dict) -> str:
	if isinstance(n, (list, tuple, dict)):
		N = len(n)
	else:
		N = n
	return '' if N == 1 else 's'

def pexpand(p):
	return expanduser(expandvars(p))


_00 = '\x1b[m'      # normal (reset all)
_0 = '\x1b[22;23;24;39m' # normal FG style
_b = '\x1b[1m'     # bold
_f = '\x1b[2m'     # faint
_i = '\x1b[3m'     # italic
_fi = '\x1b[2;3m'  # faint & italic
_u = '\x1b[4m'     # underline
_g = '\x1b[32;1m'  # good/green
_c = '\x1b[33;1m'  # command
_o = '\x1b[34;1m'  # option
_K = '\x1b[K'      # clear end-of-line
_E = '\x1b[41;97;1m' # ERROR (white on red)
_EOL = '\x1b[666C' # move far enough to the right to hit the edge

imdb_url_tmpl = 'https://www.imdb.com/title/%s'

today_date = date.today()

updated_key = 'updated'
meta_key = 'epm:meta'
legacy_meta_keys = ('added', updated_key, 'seen', 'archived')
ignore_changes = (
	'images',
	'videos',
	'production_companies',
	'season_regular',
	'crew',
	'homepage',
	'user_review_count',
)

# TODO: $XDG_CONFIG_HOME
app_config_file = pexpand(f'$HOME/.config/{PRG}/config')
num_config_backups = 10

DB_VERSION = 1

from episode_manager import tmdb

def main():
	try:
		start()
	except tmdb.NoAPIKey:
		print('No TMDb API key.', file=sys.stderr)
		print(tmdb.api_key_help)
		sys.exit(0)
	except KeyboardInterrupt:
		print('** User beak', file=sys.stderr)
		sys.exit(1)

if __name__ == '__main__':
	main()
