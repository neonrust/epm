import enum
import os
import sys
from os.path import basename, dirname, join as pjoin, exists as pexists
import shutil
from typing import Any

from .utils import read_json, write_json, print_json, warning_prefix, pexpand
from .styles import _00, _f, _o, _0, _E


default_max_refresh_age = 2  # days
default_max_hits = 10

env_config_path = 'EPM_CONFIG'
env_series_db_path = 'EPM_SERIES_DB'
env_series_cache_path = 'EPM_SERIES_CACHE'
env_debug = 'EPM_DEBUG'

user_config_home = os.getenv('XDG_CONFIG_HOME') or pexpand(pjoin('$HOME', '.config'))
user_cache_home = os.getenv('XDG_CACHE_HOME') or pexpand(pjoin('$HOME', '.cache'))

app_config_file = ''  # set in _init()
PRG = ''              # set in _init()

ValueType = str|int|float|list[Any]|dict[str, Any]  # "Any" b/c mypy doesn't support recursive type hints

_configuration_defaults:dict[str, ValueType] = {
	'commands': {
		'default': 'unseen',
		'calendar': {
			'num_weeks': 1,
		},
	},
	'num-backups': 10,
	'num-update-history': 5,
	'lookup': {
		'max-hits': default_max_hits,
	},
}

if os.getenv(env_debug):
	_debug_log = pjoin(user_config_home, 'episode_manager', 'debug.log')
	_debug_fp = open(_debug_log, 'w')
	def debug(*args, **kw):
		print(*args, **kw, file=_debug_fp, flush=True)
else:
	def debug(*_, **__):
		pass


_app_config:dict[str, ValueType] = {}
_app_config_dirty = False  # if True, it needs to be saved to disk
_memory_config:dict[str, ValueType] = {}  # only used at runtime, not persisted

class Store(enum.IntEnum):
	Persistent = 1
	Memory = 2
	Defaults = 3

_config_stores = {
	None: _app_config,
	Store.Persistent: _app_config,
	Store.Memory:     _memory_config,
	Store.Defaults:   _configuration_defaults,
}


def load() -> bool:
	"""Load persistent confguration from 'app_config_file' (into Store.Persistent)."""

	_app_config.clear()

	if not pexists(app_config_file):
		old_config_file = app_config_file.replace('/episode_manager/', '/epm/')
		if old_config_file != app_config_file and pexists(old_config_file):
			os.makedirs(dirname(app_config_file), exist_ok=True)
			shutil.copy(old_config_file, app_config_file)
			print(f'{_f}[config: imported from old location: {old_config_file}]')


	config = read_json(app_config_file)
	if config:
		_app_config.update(config)

	db_file = get('paths/series-db')
	if not isinstance(db_file, str):
		db_file = os.getenv(env_series_db_path)
		if not db_file:
			db_file = pjoin(user_config_home, 'episode_manager', 'series')
		set('paths/series-db', db_file, store=Store.Memory)

	cache_path = get('paths/series-cache')
	if not isinstance(cache_path, str):
		cache_path = os.getenv(env_series_cache_path)
		if not cache_path:
			cache_path = pjoin(user_cache_home, 'episode_manager')
		set('paths/series-cache', cache_path, store=Store.Memory)

	paths = _app_config.get('paths', {})
	if not isinstance(paths, dict):
		raise RuntimeError(f'{warning_prefix()} Config key "paths" is not a dict')

	for key in paths.keys():
		paths[key] = pexpand(paths[key])

	global _app_config_dirty
	_app_config_dirty = False

	return len(_app_config) > 0


def save() -> bool:
	"""Save configuration (if dirty)."""

	global _app_config_dirty
	if not _app_config_dirty or not _app_config:
		return False

	err = write_json(app_config_file, _app_config)
	if err is not None:
		print(f'{_E}ERROR{_00} Failed saving configuration: %s' % str(err))

	_app_config_dirty = False
	return True


def forget_all(store:Store):
	"""Clear specified config store."""

	_config_stores[store].clear()
	if store == Store.Persistent:
		global _app_config_dirty
		_app_config_dirty = True

def print_current():
	"""Debug helper; print current persistent configuration, as JSON."""
	print_json(_app_config)


def remove(path:str) -> bool:
	# from high to low priority
	configs:list[ValueType] = [_memory_config, _app_config]
	scope:list[ValueType|None] = configs

	keys = path.split('/')

	del_key = keys.pop()

	current:list[str] = []
	for key in keys:
		# print(f'cfg: %s {_o}/{_0} %s' % ('/'.join(current), key))

		for n in range(len(scope)):
			scope[n] = scope[n].get(key)  # type: ignore  # non-dicts already discarded above
			if not isinstance(scope[n], dict):
				scope[n] = None

		if not any(scope):
			# all leads have dried up
			return False

		current.append(key)

	# print('remove: scopes: %s' % scope)

	deleted = [False]*len(scope)
	missing = object()
	for idx, sc in enumerate(scope):
		if sc and sc.pop(del_key, missing) is not missing:
			# TODO: ideally, if the dict now became empty,
			#  it should be removed from its parent as well
			deleted[idx] = True

	if deleted[1]:  # i.e. _app_config
		global _app_config_dirty
		_app_config_dirty = True

	return any(deleted)

def get(path:str, default_value:ValueType|None=None, convert=None) -> ValueType|None:
	# path: key/key/...
	keys = path.split('/')
	if not keys:
		raise RuntimeError('Empty key path')

	# from high to low priority
	configs:list[ValueType] = [_memory_config, _app_config, _configuration_defaults]
	scope:list[ValueType] = configs

	current:list[str] = []
	for key in keys:
		# print('cfg: %s + %s' % ('/'.join(current), key))
		# remove non-dict entries
		scope = [sc for sc in scope if isinstance(sc, dict)]
		if not scope:
			raise RuntimeError('Invalid path "%s"; not object at "%s", got %s (%s)' % (path, '/'.join(current), scope, type(scope).__name__))

		# print('scope:', scope)
		for n in range(len(scope)):
			scope[n] = scope[n].get(key)  # type: ignore  # non-dicts already discarded above
		# remove scopes where the branch doesn't exist
		scope = [sc for sc in scope if sc is not None]
		if not scope:
			break  # not found anywhere!

		current.append(key)

	if not scope:
		value = default_value
	else:
		# use first value (higher prio)
		value = scope[0]

	if convert is not None:
		value = convert(value)

	return value


def get_int(path:str, default_value:int=0) -> int:
	v = get(path, default_value)
	if isinstance(v, (str, int)):
		return int(v)
	return default_value


def get_bool(path:str, default_value:bool=False) -> bool:
	v = get(path, default_value)
	if isinstance(v, (str, int, bool)):
		return bool(v)
	return default_value


def get_list(path:str, default_value:list|None=None) -> list|None:
	v = get(path, default_value)
	if isinstance(v, list):
		return v
	return default_value


def set(path:str, value:Any, store:Store|None=Store.Persistent) -> None:
	# path: key/key/key
	keys = path.split('/')
	if not keys or any(len(key) == 0 for key in keys):
		raise RuntimeError('Empty key path')

	store = store or Store.Memory
	maybe_store = _config_stores.get(store)
	if store not in _config_stores or maybe_store is None:
		raise RuntimeError('invalid config store "%s"' % store)

	config:dict[str, ValueType] = maybe_store
	if not isinstance(config, dict): # to shut mypy up
		return None

	scope = config

	current:list[str] = []
	while keys:
		key = keys.pop(0)

		if not keys:  # leaf key
			scope[key] = value
			break

		sub_scope = scope.get(key)
		if sub_scope is None:  # missing key (object container)
			sub_scope = {}
			scope[key] = sub_scope

		if not isinstance(sub_scope, dict): # exists, but is not an object
			raise RuntimeError('Invalid path "%s"; not object at "%s", got %s (%s)' % (
				path,
				'/'.join(current),
				scope,
				type(sub_scope).__name__,
			))

		scope = sub_scope
		current.append(key)


	if store == Store.Persistent:
		global _app_config_dirty
		_app_config_dirty = True


def tag(tag_name:str) -> dict[str, Any]|None:
	all_tags = _app_config.get('tags', {})
	assert(isinstance(all_tags, dict))

	# try direct hit first
	config = all_tags.get(tag_name)
	if config:
		return { 'name': tag_name, **config }

	# then case-insensitive search
	for name, config in all_tags.items():
		if name.lower() == tag_name:
			return { 'name': name, **config }

	return None


def _init():
	global PRG
	PRG = basename(sys.argv[0])

	global app_config_file
	app_config_file = os.getenv(env_config_path) \
	                  or \
	                  pjoin(user_config_home, 'episode_manager', 'config')

_init()


if __name__ == '__main__':
	load()

	def dump_stores():
		print('\x1b[33;1mMEMORY %s\x1b[m' % ('-'*30))
		print_json(_memory_config)
		print('\x1b[33;1mAPP %s\x1b[m' % ('-'*30))
		print_json(_app_config)
		print('\x1b[33;1mDEFAULTS %s\x1b[m' % ('-'*30))
		print_json(_configuration_defaults)

	dump_stores()

	paths = [
		'lookup/max-hits',
		'commands/default',
		'paths/series-db',
		'paths/series-cache',
	]
	print('='*40)
	for path in paths:
		value = get(path)
		print(f'\x1b[34;1m{path:<20}\x1b[m = \x1b[97;1m{value}\x1b[m')

	set('commands/default', 'unseen2', store=Store.Persistent)

	dump_stores()

	print('='*40)
	for path in paths:
		value = get(path)
		print(f'\x1b[34;1m{path:<20}\x1b[m = \x1b[97;1m{value}\x1b[m')
