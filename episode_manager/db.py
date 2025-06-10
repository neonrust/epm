import sys
import time
import os
from datetime import datetime, timedelta
from os.path import dirname, exists as pexists, join as pjoin
from collections import UserDict
import shutil
from tempfile import mkstemp
import enum
import multiprocessing as mp
from multiprocessing.pool import ApplyResult

from . import config, compression, tmdb
from .config import debug
from .utils import read_json_obj, write_json, now_datetime, now_stamp
from .styles import _0, _b, _f, _E, _00

from typing import Any, Callable, TypeVar, Generator

DB_VERSION = 5

_SAVE_DISABLED = False #True

_REMOVE_DATA_AFTER = timedelta(days=30)

_dirty = True

def is_dirty() -> bool:
	return _dirty

def set_dirty(dirty:bool=True):
	global _dirty
	_dirty = dirty


def code_version() -> int:
	return DB_VERSION

def base_filename():
	path = config.get('paths/series-db')
	assert path, 'series-db is falsy: %r' % path
	return str(path)

def cache_path():
	path = config.get('paths/series-cache')
	assert path, 'series-cache is falsy: %r' % path
	return str(path)

def active_file(uncompressed:bool=False) -> str:
	return _filename_slot(base_filename(), 0)


s_mp_writer_pool = None
s_mp_writer_pool_results:list[ApplyResult] = []

def _write_series_file(title_id:str, data:dict, series_file:str):
	tmp_name = write_json_tmp(data, dirname(series_file))
	err = None
	if tmp_name:
		os.rename(tmp_name, series_file)
		debug(f'db: wrote series file {title_id} -> {series_file}')
	else:
		err = f'{_E}Failed{_00} writing series file for {title_id}'

	return err or True

_not_in_cache = object()

class SeriesCache:

	def __init__(self, path:str):
		self._cache:dict = {}
		self._path = path
		os.makedirs(path, exist_ok=True)

	def exists(self, title_id:str) -> bool:
		try:
			os.stat(self._series_file(title_id))
			return True

		except FileNotFoundError:
			return False


	def get(self, title_id:str) -> dict|None:
		data = self._cache.get(title_id, _not_in_cache)
		if data is _not_in_cache:
			t0 = time.time()
			data = self._load_series(title_id)
			t1 = time.time()
			ms = (t1 - t0)*1000
			debug(f'{_f}db: read series %s in %.1fms{_0}' % (title_id, ms))

			self._cache[title_id] = data

		return data


	def download(self, title_id:str) -> dict|None:
		data = tmdb.episodes(title_id, with_details=True)
		if data:
			series, episodes = data
			series['episodes'] = episodes
			data = series
			self.set(title_id, data)

		return data


	def set(self, title_id:str, data:dict):
		self._cache[title_id] = data

		if _SAVE_DISABLED:
			print(f'db: {_E}SAVE DISABLED{_00} (series)')
			return
		if not self._save_series(title_id, data):
			raise RuntimeError(f'failed serialization of {title_id}')


	def remove(self, title_id:str) -> bool:
		self._cache.pop(title_id, _not_in_cache)

		try:
			os.remove(self._series_file(title_id))
		except FileNotFoundError:
			pass

		return True


	def mtime(self, title_id:str) -> datetime|None:
		filename = self._series_file(title_id)

		try:
			info = os.stat(filename)
			return datetime.fromtimestamp(info.st_mtime)

		except FileNotFoundError:
			return None


	def _series_file(self, title_id:str) -> str:
		return pjoin(self._path, title_id)


	def _load_series(self, title_id:str) -> dict|None:
		try:
			filepath = self._series_file(title_id)
			fp = compression.open(filepath)
			return read_json_obj(fp)
		except:
			return None

	def _save_series(self, title_id:str, data:dict) -> bool:
		if s_mp_writer_pool:
			promise = s_mp_writer_pool.apply_async(_write_series_file, (title_id, data, self._series_file(title_id)))
			s_mp_writer_pool_results.append(promise)
			return True

		return _write_series_file(title_id, data, self._series_file(title_id))


class Database(UserDict):

	def __init__(self, initialdata=None):
		super().__init__(initialdata)
		# TODO: remove unreferencds entries in s_series_cache

	def __len__(self):
		if meta_key in self:
			return super().__len__() - 1  # exclude epm:meta
		return 0

	def __nonzero__(self):
		return len(self) > 0

	@property
	def version(self) -> int:
		version = self.meta.get(meta_version_key)
		if not isinstance(version, int):
			return 0
		return version

	@property
	def next_list_index(self):
		next_index = self.meta.get(meta_next_list_index_key)
		if not isinstance(next_index, int):
			return 1
		return next_index

	@next_list_index.setter
	def next_list_index(self, next_index):
		self.meta[meta_next_list_index_key] = next_index

	def items(self):
		return (
	        (series_id, meta)
			for series_id, meta in super().items()
			if series_id != meta_key
		)

	@property
	def meta(self) -> dict[str, str|int|float|dict|list]:
		if meta_key not in self:
			self[meta_key] = {}
		return self[meta_key]


	def remove(self, title_id:str) -> bool:
		if title_id not in self:
			return False

		del self[title_id]
		self.remove_series(title_id)

		return True


	def has_data(self, title_id:str) -> bool:
		assert s_series_cache is not None, 'no series cache instance!?!'

		return s_series_cache.exists(title_id)


	def series(self, title_id:str) -> dict:
		assert s_series_cache is not None, 'no series cache instance!?!'

		data = s_series_cache.get(title_id)
		if not data:
			debug(f'[{title_id}] no cached data, downloading...')
			data = s_series_cache.download(title_id)
			if data:
				debug(f'[{title_id}] downloaded')
				# the entry was just (down)loaded; do the necessary post-processing
				self[title_id][meta_update_check_key] = now_stamp()
				self.add_updated_log(title_id, now_stamp())
				self._update_meta(title_id, data)

		if not data:
			raise KeyError(title_id);

		self[title_id][meta_last_used_key] = now_stamp()
		set_dirty()

		return data


	def set_series(self, title_id:str, data:dict):
		assert s_series_cache is not None, 'no series cache instance!?!'

		s_series_cache.set(title_id, data)

		self._update_meta(title_id, data)


	def remove_series(self, title_id:str) -> bool:
		assert s_series_cache is not None, 'no series cache instance!?!'

		return s_series_cache.remove(title_id)


	def add_updated_log(self, title_id:str, latest_update_stamp:str):
		meta = self[title_id]
		update_history = meta.get(meta_update_history_key, [])
		update_history.append(latest_update_stamp)

		max_history = config.get_int('num-update-history')
		if len(update_history) > max_history:
			update_history.pop(0)

		meta[meta_update_history_key] = update_history


	def recalc_meta(self, title_id:str):
		series = self.series(title_id)
		self._update_meta(title_id, series)


	def _update_meta(self, title_id:str, data:dict):
		meta = self.get(title_id, {})
		#debug('meta update %s ---------------------' % title_id)

		meta['title'] = data['title']
		if 'year' in data:
			meta['year'] = data['year']
		if 'imdb_id' in data:
			meta['imdb_id'] = data['imdb_id']

		if data.get('active_status'):
			meta[meta_active_status_key] = data.get('active_status')
			#debug('  active-status:', meta[meta_active_status_key])

		# check if there are episodes marked that doesn't exist (any more)
		all_ep_keys = set(
		    episode_key(ep)
			for ep in data.get('episodes', [])
		)
		seen_set = meta.get(meta_seen_key, {})
		for seen_key, _ in sorted(seen_set.items()):
			if seen_key not in all_ep_keys:
				#debug('seen non-ep:', seen_key, '(removing from seen list)')
				del seen_set[seen_key]

		if not data.get('episodes'):
			debug('no episodes:', title_id)
		meta[meta_total_episodes_key] = len(data.get('episodes', []))
		meta[meta_total_seasons_key] = len(set(ep['season'] for ep in data.get('episodes', [])))
		_, unseen = series_seen_unseen(data, meta)
		meta[meta_unseen_episodes_key] = len(unseen)

		#debug('  total sns:', meta[meta_total_seasons_key])
		#debug('  total eps:', meta[meta_total_episodes_key])
		#debug('  unseen:   ', meta[meta_unseen_episodes_key])

		last_ep, seen_time = last_seen_episode(data, meta)

		if last_ep and seen_time:
			meta_last = {
			    'episode': episode_key(last_ep),
				'title': last_ep.get('title', ''),
				'date': last_ep['date'],
				'seen': seen_time,
			}
			meta_last['date'] = last_ep['date']
			meta[meta_last_episode_key] = meta_last
			#debug('  last:', meta_last['episode'])

		next_ep = next_unseen_episode(data, meta)
		if next_ep:
			meta_next = {
			    'episode': episode_key(next_ep),
				'title': next_ep.get('title', ''),
			}
			if 'date' in next_ep:
				meta_next['date'] = next_ep['date']
			meta[meta_next_episode_key] = meta_next
			#debug('  next:', meta_next['episode'])

		ep_dates_by_season = {}
		last_season = -1
		for ep in unseen:
			date = ep.get('date')
			if not date:
				continue
			season = ep.get('season')
			episode = ep.get('episode')
			ep_dates = ep_dates_by_season.get(season)
			if ep_dates == None:
				ep_dates = {}
			ep_dates[str(episode)] = date
			ep_dates_by_season[str(season)] = ep_dates

		if ep_dates_by_season:
			meta[meta_episode_dates_key] = ep_dates_by_season
		else:
			try:
				del meta[meta_episode_dates_key]
			except KeyError:
				pass

		meta[meta_last_used_key] = now_stamp()
		#debug('  used:', now_stamp())

		#debug('meta update END -----------------')


	def clean_unused(self):
		"""Remove series data of rarely used (archived) series"""

		assert s_series_cache is not None, 'no series cache instance!?!'

		removed = 0
		for title_id, meta in self.items():
			if series_state(meta) & State.ARCHIVED and self.has_data(title_id):
				last_used = meta.get(meta_last_used_key)

				if not last_used:
					# get the file's modification time stamp (access time might not be available/reliable)
					mtime = s_series_cache.mtime(title_id)
					if mtime is None:
						# file diesn't exist, set "last used" to an already-expired time stamp
						meta[meta_last_used_key] = (now_datetime() - _REMOVE_DATA_AFTER).isoformat(' ', timespec='seconds')
						set_dirty()
						continue

					last_used = mtime.isoformat(' ', timespec='seconds')
					meta[meta_last_used_key] = last_used
					set_dirty()

				age = now_datetime() - datetime.fromisoformat(last_used)
				if age > _REMOVE_DATA_AFTER:
					self.remove_series(title_id)
					removed += 1
					debug(f'''{title_id:>8} "{meta['title']}" {age.days} days -> {_b}removed{_0}''')

		if removed:
			debug(f'Series data removed for {removed} series (older than {_REMOVE_DATA_AFTER.days})')



s_series_cache:SeriesCache|None = None

def load(db_file:str|None=None) -> Database:

	global s_series_cache
	s_series_cache = SeriesCache(pjoin(cache_path(), 'series'))

	if not db_file:
		db_file = active_file()

	if not db_file or not isinstance(db_file, str) or len(db_file) < 2:
		raise RuntimeError('Invalid series db file path: %r' % db_file)


	if not pexists(db_file):
		debug('db: standard file doesn\'t exist: %s' % db_file)

		if compression.method():
			# also try the uncompressed filename
			# TODO: in fact, we need the uncompressed variant of 'db_file' (if given as argument)
			uncompressed_file = str(config.get('paths/series-db'))

		debug('db: trying uncompressed file: %s' % uncompressed_file)
		if pexists(uncompressed_file):
			t0 = time.time()
			make_backup(uncompressed_file, db_file)
			t1 = time.time()
			ms = (t1 - t0)*1000
			debug(f'db: compressed uncompressed file: {uncompressed_file} in %.1fms' % ms)

		if not pexists(db_file):
			# try old location
			old_db_file = uncompressed_file.replace('/episode_manager/', '/epm/')
			debug('db: trying old location: %s' % old_db_file)
			if pexists(old_db_file):
				os.makedirs(dirname(uncompressed_file), exist_ok=True)
				shutil.copy(old_db_file, uncompressed_file)
				print(f'{_f}[{_b}db{_0}{_f}: copied from old location: {old_db_file} -> {uncompressed_file}]{_0}')


	if not pexists(db_file):
		# brand new database
		print(f'{_f}[{_b}db{_0}{_f}: new database]{_0}')
		return Database()


	t0 = time.time()
	db = read_json_obj(compression.open(db_file))
	t1 = time.time()

	set_dirty(False)

	mig_db = _migrate(db)

	ms = (t1 - t0)*1000
	debug(f'{_f}db: read %d entries in %.1fms; v%d{_0}' % (len(mig_db), ms, mig_db.version))

	mig_db.clean_unused()

	if is_dirty():
		save(mig_db)

	return mig_db


def _migrate(db:dict) -> Database:
	# no db meta data, yikes!
	if meta_key not in db:
		db[meta_key] = {}
		set_dirty()

	db_version = db[meta_key].get('version', 0)

	fixed_external_data = 0
	fixed_legacy_meta = 0
	fixed_archived = 0
	fixed_update_history = 0
	fixed_nulls = 0
	fixed_update_history_dups = 0

	def legacy_meta_get(series:dict, key:str):
		return series.get(meta_key, {}).get(key)
	def legacy_meta_set(series:dict, key:str, value):
		meta = series.get(meta_key, {})
		meta[key] = value
		series[meta_key] = meta
	def legacy_meta_del(series:dict, key:str):
		meta = series.get(meta_key, {})
		meta.pop(key, None)
		series[meta_key] = meta

	for series_id in db.keys():
		if series_id == meta_key:
			continue

		meta = db[series_id]

		if db_version < 1:
			series = meta
			if meta_key not in series:
				series[meta_key] = {
				        key: series.pop(key)
						for key in meta_legacy_keys
						if key in series
				}
				fixed_legacy_meta += 1

			if legacy_meta_get(series, meta_archived_key) == True:
				# fix all "archived" values to be dates (not booleans)
				seen = legacy_meta_get(series, meta_seen_key)
				last_seen = '0000-00-00 00:00:00'
				# use datetime from last marked episode
				for dt in seen.values():
					if dt > last_seen:
						last_seen = dt

				legacy_meta_set(series, meta_archived_key, last_seen)
				fixed_archived += 1

		if db_version < 3:
			series = meta
			last_update = legacy_meta_get(series, 'updated')
			if last_update:
				legacy_meta_set(series, meta_update_check_key, last_update)
				legacy_meta_del(series, 'updated')

			update_history = legacy_meta_get(series, meta_update_history_key)
			if not update_history and last_update:
				legacy_meta_set(series, meta_update_history_key, [last_update])
				fixed_update_history += 1

			series.pop('id', None)

		if db_version < 4:
			series = meta
			def _del_empty(data):
				nonlocal fixed_nulls
				if isinstance(data, list):
					for item in data:
						_del_empty(item)

				elif isinstance(data, dict):
					for key, value in list(data.items()):
						if value is None:
							del data[key]
							fixed_nulls += 1
						elif isinstance(value, (dict, list)):
							_del_empty(value)

			_del_empty(series)

		# remove duplicate history entries
		if db_version < 5:
			history = legacy_meta_get(meta, meta_update_history_key)
		else:
			history = meta.get(meta_update_history_key, [])

		if len(history) >=2:
			history.sort()
			idx = 0
			mods = 0
			while len(history) >= 2 and idx < len(history):
				if idx > 0 and history[idx - 1] == history[idx]:
					del history[idx - 1]
					mods += 1
				else:
					idx += 1

			if mods > 0:
				debug(f'Removed {mods} dup history items from %s' % (meta['title']))
				if db_version < 5:
					series = meta
					legacy_meta_set(series, meta_update_history_key, history)
				else:
					meta[meta_update_history_key] = history
				fixed_update_history_dups += mods

		if db_version < 5:
			last_used = meta.get('last-used')
			if last_used:
				meta[meta_last_used_key] = last_used


	# ---------------------------------------------------------------

	if db_version < 2:
		# assign list index in added time order
		list_index = 1
		for series in sorted(db.values(), key=lambda series: legacy_meta_get(series, meta_added_key)):
			legacy_meta_set(series, meta_list_index_key, list_index)
			list_index += 1
		set_dirty()

	# if no version exists, set to current version
	if db_version != DB_VERSION:
		print(f'{_f}Set DB version: %s -> %s{_0}' % (legacy_meta_get(db, meta_version_key), DB_VERSION))
		if db_version < 5:
			legacy_meta_set(db, meta_version_key, DB_VERSION)
		else:
			meta_set(db, meta_version_key, DB_VERSION)

	if db_version < 2:
		legacy_meta_set(db, meta_next_list_index_key, list_index)
		print(f'{_f}Built list indexes for all {len(db) - 1} series, next index: {list_index}{_0}')

	if db_version < 5:
		old_db = db
		mig_db = Database(db)
		id_list = list(series_id for series_id, _  in old_db.items() if series_id != meta_key)

		print(f'{_f}Migrating database to v{DB_VERSION} ({len(id_list)} series)...{_0}')

		# save series data into external files; see SeriesCache
		# promote [series_id][emp:meta] -> [series_id]
		# the global [epm:meta], is unchanged

		# db.set_series will use the MP pool, if  it exists
		global s_mp_writer_pool
		s_mp_writer_pool = mp.Pool()

		for count, series_id in enumerate(id_list):
			# TODO: show progress bar: (count + 1) / len(idList)
			entry = old_db[series_id]   # series data & meta
			meta = entry.pop(meta_key, {})
			mig_db[series_id] = meta
			# write external series data file only for non-archived series
			series_data = entry
			if meta_archived_key not in meta:
				mig_db.set_series(series_id, series_data)  # updates meta
			else:
				mig_db._update_meta(series_id, series_data)

		# wait for the pool jobs to complete
		for p in s_mp_writer_pool_results:
			err = p.get()
			if err != True:
				print(err, file=sys.stderr)
			else:
				fixed_external_data += 1
	else:
		mig_db = Database(db)

	# ----------------------------------------------------

	def did_migration(msg):
		set_dirty()
		print(f'{_f}[\x1b[1mdb{_0}{_f}: {msg}]{_0}')

	if fixed_legacy_meta:
		did_migration(f'Migrated legacy meta-data; {fixed_legacy_meta} series')

	if fixed_external_data:
		did_migration(f'Migrated to external data; {fixed_external_data} series')

	if fixed_archived:
		did_migration(f'Fixed bad "{meta_archived_key}" value; {fixed_archived} series')

	if fixed_update_history:
		did_migration(f'Fixed empty "{meta_update_history_key}" values; {fixed_update_history} series')

	if fixed_nulls:
		did_migration(f'Removed null values; {fixed_nulls} series')

	if fixed_update_history_dups:
		did_migration(f'Removed duplicate entires of update history; {fixed_update_history_dups} series')

	return mig_db




def make_backup(source:str, destination:str) -> bool:
	if not compression.method() or not compression.compress_file(source, destination):
		os.rename(source, destination)
		return False

	return True


def _filename_slot(base_name:str, idx:int) -> str:
	method = compression.method()
	if method:
		return '%s.%d%s' % (base_name, idx, method['extension'])

	return '%s.%d' % (base_name, idx)


def _rotate_backups(base_name:str):
	num_backups = 0

	debug('db: rotating backups')

	# loop through all file slots, including 0
	for idx in range(config.get_int('num-backups'), 0, -1):
		org_file = _filename_slot(base_name, idx - 1)
		if pexists(org_file):
			num_backups += 1
			shifted_file = _filename_slot(base_name, idx)
			# debug(f'db: [rotate] rename {org_file} -> {shifted_file}')
			os.rename(org_file, shifted_file)

	return num_backups


def _unrotate_backups(base_name:str):
	num_backups = 0

	debug('db: unrotating backups')

	for idx in range(0, config.get_int('num-backups')):
		org_file = _filename_slot(base_name, idx + 1)
		if pexists(org_file):
			num_backups += 1
			unshifted_file = _filename_slot(base_name, idx)
			# debug(f'db: [unrotate] {org_file} -> {unshifted_file}')
			os.rename(org_file, unshifted_file)

	num_backups -= 1  # one backup was removed/restored

	return num_backups


def save(db:Database) -> bool:

	if _SAVE_DISABLED:
		print(f'db: {_E}SAVE DISABLED{_00}')
		set_dirty(False)
		return True

	if not is_dirty():
		debug(f'{_f}db: save ignored; not dirty{_0}')
		return True

	set_dirty(False)

	base_name = base_filename()
	db_path = dirname(base_name)

	os.makedirs(db_path, exist_ok=True)

	t0 = time.time()

	tmp_name = write_json_tmp(db.data, db_path)
	if not tmp_name:
		print(f'{_E}Failed{_00} writing database file', file=sys.stderr)
		return False

	_rotate_backups(base_name)

	os.rename(tmp_name, active_file())
	#debug(f'db: renamed new compressed {tmp_name} {active_file()}')

	t1 = time.time()
	ms = (t1 - t0)*1000
	debug('db: wrote %d entries in %.1fms; v%d' % (len(db), ms, db.version))

	return True


def write_json_tmp(data:dict, dir:str) -> str|None:
	# write to a temp file and then rename it afterwards
	tmp_name = mkstemp(dir=dir)[1]

	err = write_json(tmp_name, data)

	if err is not None:
		print(f'{_E}ERROR{_00} Failed writing JSON: %s' % str(err), file=sys.stderr)
		os.remove(tmp_name)
		return None

	tmp_name2 = mkstemp(dir=dir)[1]
	#debug(f'db: compressing {tmp_name} -> {tmp_name2}')

	if not compression.compress_file(tmp_name, tmp_name2):
		os.remove(tmp_name)
		os.remove(tmp_name2)
		return None

	return tmp_name2


def list_backups() -> list[str]:
	"""Returns a list of existing backups, most recent first."""

	base_name = base_filename()

	bups = []

	for idx in range(1, config.get_int('num-backups') + 1):
		bup_name = _filename_slot(base_name, idx)
		if pexists(bup_name):
			bups.append(bup_name)

	return bups


def rollback():
	"""Restore the most recent backup and shift all backups indices"""

	base_name= base_filename()

	first_backup = _filename_slot(base_name, 1)
	if not pexists(first_backup):
		return None, f'No backup to restore ({first_backup})', None

	change_log = load().meta.get(meta_changes_log_key, [])

	# decreease the index of all backups
	num_remaining = _unrotate_backups(base_name)

	return num_remaining, first_backup, change_log


def meta_set(meta:dict, key: str, value) -> None:
	# a bit complex to check whether 'value' differs from existing value
	set_dirty()
	meta[key] = value

	if value == [] or value == {}:
		del meta[key]


def meta_del(meta:dict, key: str) -> None:
	if key in meta:
		set_dirty()
	meta.pop(key, None)


def changelog_add(db:Database, message:str, series_id:str|None=None):
	log = db.meta.get(meta_changes_log_key)

	if not isinstance(log, list):
		log = []

	log.append((message, series_id))

	db.meta[meta_changes_log_key] = log
	set_dirty()

	debug('Logged change:', message, series_id if series_id else '')


def changelog_clear(db:Database):
	db.meta.pop(meta_changes_log_key, None)

class State(enum.IntFlag):
	PLANNED   = 0x01  # added but nothing seen (yet)
	STARTED   = 0x02  # some episodes seen
	COMPLETED = 0x04  # all episodes seen (and manually restored)
	ARCHIVED  = 0x08  # all episodes seen (automatically archived)
	ABANDONED = 0x10 | ARCHIVED  # manually archived when not all episodes seen

	ACTIVE    = PLANNED | STARTED
	ALL       = ACTIVE | COMPLETED | ARCHIVED


T = TypeVar('T')
def filter_map(db:Database, filter:Callable[[str,dict],bool]|None=None, map:Callable[[str,dict],T]|None=None, sort_key:Callable[[str, dict],Any]|None=None) -> Generator[T,None,None]:

	filter = filter or (lambda i, m: True)
	if not map:
		def map(series_id:str, meta:dict):
			return series_id, meta

	db_iter:Generator|list = db.items()
	if sort_key:
		db_iter = sorted(db_iter, key=sort_key)  # type: ignore # 'key' expects more generic type than we use

	return (
        map(series_id, meta)
		for series_id, meta in db_iter
		if filter(series_id, meta)
	)


def _sortkey_title_and_year(sid_meta:tuple[str,dict]) -> Any:
	series_id, meta = sid_meta
	return meta['title'].casefold(), meta.get('year', [])

def indexed_series(db:Database, index=None, match=None, state:State|None=None, tags:list[str]|None=None, sort_key:Callable|None=None) -> list[tuple[int, str]]:
	"""Return a list with a predictable sorting, optionally filtered."""

	def flt(series_id:str, meta:dict) -> bool:
		passed:bool = True

		if passed and index is not None:
			passed = meta.get(meta_list_index_key) == index

		if passed and state is not None:
			passed = (series_state(meta) & state) > 0

		if passed and tags is not None:
			passed = any(tag in tags for tag in meta.get(meta_tags_key, []))

		if passed and match is not None:
			passed = match(db, series_id, meta)

		return passed

	def index_and_id(series_id:str, meta:dict) -> tuple[int, str]:
		return meta[meta_list_index_key], series_id

	sort_key = sort_key or _sortkey_title_and_year

	return list(filter_map(db, filter=flt, map=index_and_id, sort_key=sort_key))


def title_match(title:str, find_title:str) -> bool:
	# TODO: impelement something more "fuzzy"
	return find_title in title.casefold()


def find_single_series(db:Database, needle:str, filter_callback:Callable[[str,dict],bool]|None=None) -> tuple[int|None, str|None, str|list|None]:
	nothing_found = None, None, f'Series not found: {needle}'

	if not needle:
		return nothing_found

	find_index:int|None = None
	imdb_id:str|None = None
	find_title:str|None = None

	# int -> list index
	# "tt[0-9]+" -> IMDb ID
	# anything else -> title
	try:
		find_index = int(needle)
	except ValueError:
		if needle[:2] == 'tt':
			imdb_id = needle
		else:
			find_title = needle.casefold()

	if find_title:
		debug('find_title:', find_title)
	elif find_index:
		debug('find_index:', find_index)

	def flt(series_id:str, meta:dict) -> bool:
		passed = True

		if passed and find_index is not None:
			passed = meta.get(meta_list_index_key) == find_index

		if passed and find_title is not None:
			passed = title_match(meta.get('title', ''), find_title)

		if passed and imdb_id is not None:
			series = db.series(series_id)
			if series:
				passed = meta.get('imdb_id') == imdb_id

		if passed and filter_callback is not None:
			passed = filter_callback(series_id, meta)

		return passed

	def index_sid(series_id:str, meta:dict) -> tuple[int, str]:
		return meta[meta_list_index_key], series_id

	found = list(filter_map(db, filter=flt, map=index_sid))

	if len(found) == 1:
		return *found[0], None

	if len(found) > 1:
		return None, None, found

	return nothing_found


def last_seen_episode(series:dict, meta:dict) -> tuple[dict|None, str|None]:
	episodes = series.get('episodes', [])
	if not episodes:
		return None, None

	seen = meta.get(meta_seen_key, {})
	last_seen = (0, 0)
	seen_time = None
	for seen_key in seen.keys():
		season, episode = seen_key.split(':')
		if season == 'S':
			continue
		season = int(season)
		episode = int(episode)
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


def next_unseen_episode(series:dict, meta:dict) -> dict|None:

	episodes = series.get('episodes', [])
	if not episodes:
		return None

	seen = meta.get(meta_seen_key, {})
	last_seen = (0, 0)
	for seen_key in seen.keys():
		season, episode = [
		    n if n == 'S' else int(n)
			for n in seen_key.split(':')
		]
		if season == 'S':
			continue  # only count "regular" epixodes
		if season > last_seen[0] or (season == last_seen[0] and episode > last_seen[1]):
			last_seen = (season, episode)

	if last_seen == (0, 0):
		return episodes[0]

	for ep in episodes:
		season = ep['season']
		episode = ep['episode']
		# next episode in same season (checked first) or first in next season
		if season == last_seen[0] and episode == last_seen[1] + 1 \
		    or\
			season == last_seen[0] + 1 and episode == 1:
			return ep

	return None


def series_state(meta:dict) -> State:
	is_archived = meta_archived_key in meta
	is_ended = meta.get(meta_active_status_key) in ('ended', 'canceled')

	num_seen, num_unseen = series_num_seen_unseen(meta, before=now_datetime())

	if is_archived:
		if num_unseen > 0:  # partially seen
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

def should_update(meta:dict) -> bool:

	# never updated -> True
	# archived -> False
	# ended -> False   (assumes, as we got the "ended" status, we also got all the episodes)
	# if update history > 2, AGE = interval between last two updates, cap: 2 weeks
	# else: AGE = age of last update, cap: 2 days
	# ---
	# if last check is older than NOW - AGE: True
	# else: False

	# TODO: take seen episodes into account?

	last_check = meta.get(meta_update_check_key)
	if not last_check:  # no updates whatsoever
	    return True

	if series_state(meta) & (State.ARCHIVED | State.COMPLETED) > 0:
		return False

	debug(f'\x1b[33;1m{meta["title"]}\x1b[m', end='')

	if meta.get(meta_active_status_key) in ('ended', 'canceled'):
		# it's assumed we already have all the necessary info (most importantly the episodes)
		#debug(f'  \x1b[3m{series["status"]}\x1b[m -> \x1b[31;1mFalse\x1b[m')
		debug('\r\x1b[K', end='')
		return False

	last_check = datetime.fromisoformat(last_check)
	simple_age_cap = WEEK

	update_history = meta.get(meta_update_history_key)
	if not update_history:
		debug(' \x1b[35;1mno updates\x1b[m \x1b[32;1mTrue\x1b[m')
		return True

	# time between the last (actual) update and the last time it was checked
	last_update = datetime.fromisoformat(update_history[-1])
	capped = ''

	if len(update_history) >= 2:
		# interval between two last updates
		# TODO: average interval between all updates, or longest/shortest?
		update_interval_sum = timedelta(0)
		for idx in range(1, len(update_history)):
			update_interval_sum += datetime.fromisoformat(update_history[idx]) - datetime.fromisoformat(update_history[idx - 1])
		update_interval = update_interval_sum/(len(update_history) - 1)
		if update_interval.total_seconds() >= simple_age_cap:
			update_interval = timedelta(seconds=simple_age_cap)
			capped = 'cap'
		debug(f' history interval:{update_interval.total_seconds()/DAY:.1f}d \x1b[33;1m{capped}\x1b[m', end='')
	else:
		update_interval = now_datetime() - last_update
		if update_interval.total_seconds() >= simple_age_cap:
			update_interval = timedelta(seconds=simple_age_cap)
			capped = 'cap'
		debug(f' last interval:{update_interval.total_seconds()/DAY:.1f}d \x1b[33;1m{capped}\x1b[m', end='')

	next_update = last_check + update_interval
	debug(f'  next:{str(next_update)[:19]}', end='')

	expired = now_datetime() > next_update
	if expired:
		debug(' \x1b[32;1mTrue\x1b[m')
	else:
		debug(' \x1b[31;1mFalse\x1b[m')

	return expired


def series_num_seen_unseen(meta:dict, before:datetime|None=None) -> tuple[int, int]:
	num_seen = len(meta.get(meta_seen_key, []))
	num_unseen = meta.get(meta_unseen_episodes_key, 0)

	# TODO: take 'before' into account

	return num_seen, num_unseen


def series_seen_unseen(series:dict, meta:dict, before:datetime|None=None) -> tuple[list, list]:
	episodes = series.get('episodes', [])
	seen = meta.get(meta_seen_key, {})

	seen_eps = []
	unseen_eps = []

	for ep in episodes:
		if episode_key(ep) in seen:
			seen_eps.append(ep)
		else:
			# only include episodes in 'unseen' that are already available
			dt = ep.get('date')
			if dt:
				dt = datetime.fromisoformat(dt)
				if before and dt > before:
					continue

			elif before is not None:  # we're filtering by date but episode has no date
			    continue

			unseen_eps.append(ep)

	return seen_eps, unseen_eps


def episode_key(episode:dict):
	return f'{episode["season"]}:{episode["episode"]}'


def series_index(index_number:int):
	if index_number < 100:
		return (None, str(index_number))

	low = index_number % 100
	high = index_number // 100

	high_digits:list[str] = []
	while True:
		digit = high % 26
		high -= digit
		if not digit:
			break
		high_digits.insert(0, chr(digit - 1 + ord('a')))

	high_digits_str = ''.join(high_digits)
	low_digits = '%02d' % low

	return (high_digits_str, low_digits)


# def series_num_archived(db:Database) -> int:
# 	return sum(1 if meta_has(series, meta_archived_key) else 0 for series in db.values())


meta_key = 'epm:meta'
meta_active_status_key = 'active_status'
meta_added_key = 'added'
meta_seen_key = 'seen'
meta_tags_key = 'tags'
meta_last_episode_key = 'last_episode'
meta_next_episode_key = 'next_episode'
meta_total_episodes_key = 'total_episodes'
meta_total_seasons_key = 'total_seasons'
meta_unseen_episodes_key = 'unseen_episodes'
meta_episode_dates_key = 'episode_dates'
meta_archived_key = 'archived'
meta_list_index_key = 'list_index'
meta_next_list_index_key = 'next_list_index'
meta_update_check_key = 'update_check'
meta_update_history_key = 'update_history'
meta_last_used_key = 'last_used'
meta_rating_key = 'rating'
meta_rating_comment_key = 'rating_comment'
meta_version_key = 'version'
meta_changes_log_key = 'changes_log'
meta_add_comment_key = 'add_comment'


meta_legacy_keys = (
    meta_added_key,
	meta_update_check_key,
	meta_seen_key,
	meta_archived_key,
)

if __name__ == '__main__':
	config.load()
	load()
