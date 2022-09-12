import time
import sys
import os
from datetime import datetime, timedelta
from os.path import dirname, exists as pexists
from subprocess import run
from tempfile import mkstemp
import enum

from . import config
from .utils import read_json, write_json, warning_prefix, cap, now_datetime
from .styles import _0, _00, _0B, _c, _i, _b, _f, _fi, _K, _E, _o, _g, _L, _S, _u, _EOL

from typing import Any, Callable, TypeVar, Generator

DB_VERSION = 3

def code_version() -> int:
	return DB_VERSION


def load(file_path:str|None=None) -> dict:

	db_file = file_path or str(config.get('paths/series-db'))

	if not db_file or not isinstance(db_file, str) or len(db_file) < 2:
		raise RuntimeError('Invalid series db file path: %r' % db_file)

	if not pexists(db_file):
		old_db_file = db_file.replace('/episode_manager/', '/epm/')
		if pexists(old_db_file):
			os.makedirs(dirname(db_file), exist_ok=True)
			shutil.copy(old_db_file, db_file)
			print(f'{_f}[db: imported from old location: {old_db_file}]')

	t0 = time.time()
	db = read_json(db_file)
	t1 = time.time()

	if config.get_bool('debug'):
		ms = (t1 - t0)*1000
		print(f'{_f}[db: read %d entries in %.1fms; v%d]{_0}' % (len(db) - 1, ms, meta_get(db, meta_version_key)), file=sys.stderr)

	modified = _migrate(db)

	if modified:
		save(db)

	return db


def _migrate(db:dict) -> bool:

	modified = False

	# no db meta data, yikes!
	if meta_key not in db:
		db[meta_key] = {}
		modified = True

	db_version = db[meta_key].get('version', 0)

	fixed_legacy_meta = 0
	fixed_archived = 0
	fixed_update_history = 0

	for series_id in all_ids(db):
		series = db[series_id]

		if db_version < 1:
			if meta_key not in series:
				series[meta_key] = {
						key: series.pop(key)
						for key in meta_legacy_keys
						if key in series
				}
				fixed_legacy_meta += 1

			if meta_get(series, meta_archived_key) == True:
				# fix all "archived" values to be dates (not booleans)
				seen = meta_get(series, meta_seen_key)
				last_seen = '0000-00-00 00:00:00'
				# use datetime from last marked episode
				for dt in seen.values():
					if dt > last_seen:
						last_seen = dt

				meta_set(series, meta_archived_key, last_seen)
				fixed_archived += 1

		if db_version < 3:
			last_update = meta_get(series, 'updated')
			if last_update:
				meta_set(series, meta_update_check_key, last_update)
				meta_del(series, 'updated')

			update_history = meta_get(series, meta_update_history_key)
			if not update_history and last_update:
				meta_set(series, meta_update_history_key, [last_update])
				fixed_update_history += 1

			series.pop('id', None)


	if db_version < 2:
		# assign 'list_index' ordered by "added" time
		list_index = 1
		for series in sorted(db.values(), key=lambda series: meta_get(series, meta_added_key)):
			meta_set(series, meta_list_index_key, list_index)
			list_index += 1
		modified = True

	# if no version exists, set to current version
	if db_version != DB_VERSION:
		print(f'{_f}Set DB version: %s -> %s{_0}' % (meta_get(db, meta_version_key), DB_VERSION))
		meta_set(db, meta_version_key, DB_VERSION)
		modified = True

	if db_version < 2:
		meta_set(db, meta_next_list_index_key, list_index)
		print(f'{_f}Built list indexes for all {len(db) - 1} series, next index: {list_index}{_0}')
		modified = True

	if fixed_legacy_meta:
		print(f'{_f}Migrated legacy meta-data of {fixed_legacy_meta} series{_0}')
		modified = True

	if fixed_archived:
		print(f'{_f}Fixed bad "{meta_archived_key}" value of {fixed_archived} series{_0}')
		modified = True

	if fixed_update_history:
		print(f'{_f}Fixed empty "{meta_update_history_key}" value of {fixed_update_history} series{_0}')
		modified = True

	return modified


_compressor: dict | None = None
_compressors:list[dict[str, str | list[str]]] = [
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
for method in _compressors:
	if shutil.which(method['binary']): # type: ignore
		_compressor = method
		break

def compressor():
	return _compressor['binary'] if _compressor else None

# TODO: 'mk_backup' should return a waitable promise (so we can do it in parallel with the serialization)

def mk_uncompressed_backup(source:str, destination:str) -> bool:
	os.rename(source, destination)
	return True

if _compressor:
	def mk_backup(source:str, destination:str) -> bool:

		# copy file access & mod timestamps from source
		file_info = os.stat(source)

		destination += _compressor.get('extension', _compressor['binary']) # type: ignore

		try:
			command_line = [_compressor['binary']] + _compressor['args'] # type: ignore

			infp = open(source, 'rb')
			outfp = open(destination, 'wb')

			comp = run(command_line, stdin=infp, stdout=outfp, universal_newlines=False)
			success = comp.returncode == 0

			if success:
				# file compressed into destination, we can safely remove the source(s)
				os.remove(source)
			else:
				# compression failed, just fall back to uncomrpessed
				print(f'[{warning_prefix()}] Compression failed: {source} -> {destination}: {comp.returncode}', file=sys.stderr)
				mk_uncompressed_backup(source, destination)

			# copy timestamps from source file
			os.utime(destination, (file_info.st_atime, file_info.st_mtime))

		except Exception as e:
			print(f'{_E}ERROR{_00} Failed compressing database backup: %s' % str(e))
			os.rename(source, destination)
			success = False

		return success

else:
	mk_backup = mk_uncompressed_backup

def save(db:dict) -> None:

	# print('SAVE DISABLED')
	# import inspect
	# frames = inspect.stack()[1:3]
	# for fr in frames:
	# 	fname = basename(fr.filename)
	# 	print(f' from {_b}{fr.function}{_o}(){_0}  {_f}{fname}{_c}:{_0}{_f}{fr.lineno}{_0}')
	# return

	db_file = str(config.get('paths/series-db'))

	if not pexists(db_file):
		os.makedirs(dirname(db_file), exist_ok=True)

	def backup_name(idx) -> str:
		return '%s.%d' % (db_file, idx)


	# write to a temp file and then rename it afterwards
	tmp_name = mkstemp(dir=dirname(db_file))[1]
	t0 = time.time()
	err = write_json(tmp_name, db)
	t1 = time.time()

	if err is None:
		# rotate backups
		for idx in range(config.get_int('num-backups')):
			if pexists(backup_name(idx)):
				os.rename(backup_name(idx), backup_name(idx + 1))

		# current file becomes first backup (<name>.1)
		# TODO: spawn background process to compress to make it appear faster?
		#   might run into (more) race-conditions of course

		# backup existing(old) db file to 'series.1'
		t2 = time.time()
		mk_backup(db_file, backup_name(1))
		t3 = time.time()

		os.rename(tmp_name, db_file)

		if config.get_bool('debug'):
			ms = (t1 - t0)*1000
			ms2 = (t3 - t2)*1000
			print(f'{_f}[db: wrote %d entries in %.1fms (%.1fms); v%d]{_0}' % (len(db) - 1, ms, ms2, meta_get(db, meta_version_key)), file=sys.stderr)

	else:
		print(f'{_E}ERROR{_00} Failed saving series database: %s' % str(err))
		os.remove(tmp_name)


def meta_get(obj:dict, key:str, def_value:Any=None) -> Any:
	return obj.get(meta_key, {}).get(key, def_value)


def meta_has(obj:dict, key:str) -> bool:
	return meta_get(obj, key, None) is not None


def meta_set(obj:dict, key: str, value) -> None:
	if meta_key not in obj:
		obj[meta_key] = {}
	obj[meta_key][key] = value


def meta_del(obj:dict, key: str) -> None:
	obj[meta_key].pop(key, None)


def meta_copy(source:dict, destination:dict) -> None:
	destination[meta_key] = source.get(meta_key, {})


class State(enum.IntFlag):
	PLANNED   = 0x01  # added but nothing seen (yet)
	STARTED   = 0x02  # some episodes seen
	COMPLETED = 0x04  # all episodes seen and manually restored
	ARCHIVED  = 0x08  # all episodes seen (automatically archived)
	ABANDONED = 0x10  # manually archived when not all episodes seen

	ACTIVE    = 0x01 | 0x02


T = TypeVar('T')
def filter_map(db:dict, sort_key:Callable[[str, dict],Any]|None=None, filter:Callable[[str,dict],bool]|None=None, map:Callable[[str,dict],T]|None=None) -> Generator[T,None,None]:

	if filter is None:
		def no_filter(series_id:str, series:dict):
			return True
		filter = no_filter

	if map is None:
		def identity(series_id:str, series:dict):
			return series_id, series
		map = identity

	db_iter:Generator|list = (
		(series_id, series)
		for series_id, series in db.items()
		if series_id != meta_key
	)
	if sort_key:
		db_iter = sorted(db_iter, key=sort_key)  # type: ignore # 'key' expects more generic type than we use

	return (
		map(series_id, series)
		for series_id, series in db_iter
		if filter(series_id, series)
	)


def _sortkey_title_and_year(sid_series:tuple[str,dict]) -> Any:
	series_id, series = sid_series
	return series['title'].casefold(), series.get('year', [])

def indexed_series(db:dict, index=None, match=None, state:State|None=None, sort_key:Callable|None=None) -> list[tuple[int, str]]:
	"""Return a list with a predictable sorting, optionally filtered."""

	def flt(series_id:str, series:dict) -> bool:
		passed:bool = True
		if passed and index is not None:
			passed = meta_get(series, meta_list_index_key) == index
		if passed and match is not None:
			passed = match(series)
		if passed and state is not None:
			passed = (series_state(series) & state) > 0
		return passed

	def index_and_series(series_id:str, series:dict) -> tuple[int, str]:
		return meta_get(series, meta_list_index_key), series_id

	sort_key = sort_key or _sortkey_title_and_year

	return list(filter_map(db, filter=flt, map=index_and_series, sort_key=sort_key))


def find_single_series(db:dict, idx_or_id:str) -> tuple[int|None, str|None, str|None]:
	nothing_found = None, None, f'Series not found: {idx_or_id}'

	if not idx_or_id:
		return nothing_found

	find_index:int|None = None
	imdb_id:str|None = None

	# int -> list index
	# "tt[0-9]+" -> IMDb ID
	try:
		find_index = int(idx_or_id)
	except:
		if idx_or_id[:2] == 'tt':
			imdb_id = idx_or_id
		else:
			return nothing_found

	def flt(series_id:str, series:dict) -> bool:
		passed = True

		if passed and find_index is not None:
			passed = meta_get(series, meta_list_index_key) == find_index

		if passed and imdb_id is not None:
			passed = series.get('imdb_id') == imdb_id

		return passed

	def index_sid(series_id:str, series:dict) -> tuple[int, str]:
		return meta_get(series, meta_list_index_key), series_id

	found = list(filter_map(db, filter=flt, map=index_sid))

	if found:
		return *found[0], None

	return nothing_found


def last_seen_episode(series:dict) -> tuple[dict|None, str|None]:
	episodes = series.get('episodes', [])
	if not episodes:
		return None, None

	seen = meta_get(series, meta_seen_key, {})
	last_seen = (0, 0)
	seen_time = None
	for seen_key in seen.keys():
		season, episode = [int(n) for n in seen_key.split(':')]
		if season > last_seen[0] or episode > last_seen[1]:
			last_seen = (season, episode)
			seen_time = seen[seen_key]

	if last_seen == (0, 0):
		return None, None

	for ep in episodes:
		season = ep['season']
		episode = ep['episode']
		# next episode in same season or first in next season
		if season == last_seen[0] and episode == last_seen[1]:
			return ep, seen_time

	return None, None


def next_unseen_episode(series:dict) -> dict|None:
	episodes = series.get('episodes', [])
	if not episodes:
		return None

	seen = meta_get(series, meta_seen_key, {})
	last_seen = (0, 0)
	for seen_key in seen.keys():
		season, episode = [int(n) for n in seen_key.split(':')]
		if season > last_seen[0] or episode > last_seen[1]:
			last_seen = (season, episode)

	if last_seen == (0, 0):
		return episodes[0]

	for ep in episodes:
		season = ep['season']
		episode = ep['episode']
		# next episode in same season or first in next season
		if season == last_seen[0] and episode == last_seen[1] + 1 \
			or\
			season == last_seen[0] + 1 and episode == 1:
			return ep

	return {}


def all_ids(db:dict) -> list[str]:
	return list(
		key
		for key in db.keys()
		if key != meta_key
	)


def series_state(series:dict) -> State:
	is_archived = meta_has(series, meta_archived_key)
	is_ended = series.get('status') in ('ended', 'canceled')

	num_episodes = len(series.get('episodes', []))
	num_seen = len(meta_get(series, meta_seen_key, {}))
	num_unseen = num_episodes - num_seen

	if is_archived:
		if num_seen and num_unseen:  # partially seen
			return State.ABANDONED

		return State.ARCHIVED

	elif num_seen:
		if not num_unseen and is_ended:
			return State.COMPLETED

		return State.STARTED

	return State.PLANNED


HOUR = 3600
DAY = 24*HOUR
WEEK = 7*DAY

def should_update(series:dict) -> bool:

	debug = config.get_bool('debug')

	# never updated -> True
	# archived -> False
	# ended -> False
	# if update history > 2, AGE = interval between last two updates, cap: 2 weeks
	# else: AGE = age of last update, cap: 2 days
	# ---
	# if last check is older than NOW - AGE: True
	# else: False

	# TODO: take seen episodes into account?

	if debug: print(f'\x1b[33;1m{series["title"]}\x1b[m', end='')

	last_check = meta_get(series, meta_update_check_key)
	if not last_check:  # no updates whatsoever
		if debug: print('  never updated -> \x1b[32;1mTrue\x1b[m')
		return True

	if series_state(series) & (State.ARCHIVED | State.COMPLETED) > 0:
		if debug: print('  archived -> \x1b[31;1mFalse\x1b[m')
		return False

	if series.get('status') in ('ended', 'canceled'):
		# it's assumed we already have all the necessary info (most importantly the episodes)
		if debug: print('  ended -> \x1b[31;1mFalse\x1b[m')
		return False

	last_check = datetime.fromisoformat(last_check)
	simple_age_cap = 4*DAY

	update_history = meta_get(series, meta_update_history_key)
	if update_history:
		# time between the last (actual) update and the last time it was checked
		last_update = datetime.fromisoformat(update_history[-1])
		age = int((last_check - last_update).total_seconds())
		age = cap(age, None, 2*WEEK)
		if debug: print(f'  \x1b[35;1mhistory\x1b[m:', end='')

	else:
		age = int((now_datetime() - last_check).total_seconds())
		if debug: print(f'  \x1b[36;1mlast\x1b[m:', end='')
		age = cap(age, None, simple_age_cap)

	if debug: print(f'{age/DAY:.1f} days', end='')

	if age < simple_age_cap:
		if debug: print(f' < {simple_age_cap//DAY} \x1b[31;1mFalse\x1b[m')
		return False


	check_expiry = last_check + timedelta(seconds=age)

	expired = now_datetime() > check_expiry

	if debug:
		print(f'  expiry:{str(check_expiry)[:19]}', end='')
		if expired:
			print(' \x1b[32;1mTrue\x1b[m')
		else:
			print(' \x1b[31;1mFalse\x1b[m')

	return expired

	# updated_stamp = meta_get(series, meta_updated_key)
	# if not updated_stamp:
	# 	return True, None
	#
	# updated = datetime.fromisoformat(updated_stamp)
	# age_seconds = int((now_datetime() - updated).total_seconds())
	# # print('%s updated:' % series['title'], updated, 'age:', age_seconds, max_age_seconds)
	# return age_seconds > max_age_seconds, updated



def series_seen_unseen_eps(series:dict, before: datetime | None=None) -> tuple[list, list]:
	episodes = series.get('episodes', [])
	seen = meta_get(series, meta_seen_key, {})

	seen_eps = []
	unseen_eps = []

	for ep in episodes:
		if episode_key(ep) in seen:
			seen_eps.append(ep)
		else:
			# only include episodes in 'unseen' that are already available
			dt = ep.get('date')
			if not dt:
				continue
			dt = datetime.fromisoformat(dt)
			if before and dt > before:
				continue

			unseen_eps.append(ep)

	return seen_eps, unseen_eps


def episode_key(episode:dict):
	return f'{episode["season"]}:{episode["episode"]}'


# def series_num_archived(db:dict) -> int:
# 	return sum(1 if meta_has(series, meta_archived_key) else 0 for series in db.values())


meta_key = 'epm:meta'
meta_added_key = 'added'
meta_seen_key = 'seen'
meta_archived_key = 'archived'
meta_list_index_key = 'list_index'
meta_next_list_index_key = 'next_list_index'
meta_update_check_key = 'update_check'
meta_update_history_key = 'update_history'
meta_version_key = 'version'


meta_legacy_keys = (
	meta_added_key,
	meta_update_check_key,
	meta_seen_key,
	meta_archived_key,
)
