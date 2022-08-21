import os
from os.path import basename, dirname, expandvars, expanduser, exists as pexists, getsize as psize, join as pjoin
from typing import Any

from .utils import read_json, write_json, print_json, warning_prefix, pexpand


default_max_refresh_age = 2  # days
default_max_hits = 10

user_config_home = os.getenv('XDG_CONFIG_HOME') or pexpand(pjoin('$HOME', '.config'))

app_config_file = ''  # set in init()
PRG = '' # set in init()

def init(prg):
	global PRG
	PRG = prg
	global app_config_file
	app_config_file = pjoin(user_config_home, PRG, 'config')


ValueType = str|int|float|list[Any]|dict[str, Any]  # "Any" b/c mypy doesn't support recursive type hints

_configuration_defaults:dict[str, ValueType] = {
	'commands': {
		'default': 'unseen',
		'calendar': {
			'num_weeks': 1,
		},
	},
	'max-age': default_max_refresh_age,
	'num-backups': 10,
	'lookup': {
		'max-hits': default_max_hits,
	},
	'debug': 0,
}

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
	_app_config.clear()

	config = read_json(app_config_file)
	if config:
		_app_config.update(config)

	db_file = get('paths/series-db')
	if not db_file or not isinstance(db_file, str):
		db_file = pjoin(user_config_home, PRG, 'series')
		set('paths/series-db', db_file, store=Store.Memory)

	paths = _app_config.get('paths', {})
	if not isinstance(paths, dict):
		raise RuntimeError(f'{warning_prefix()} Config key "paths" is not an object')

	for key in paths.keys():
		paths[key] = pexpand(paths[key])

	global _app_config_dirty
	_app_config_dirty = False

	return len(_app_config) > 0


def save():
	global _app_config_dirty
	if not _app_config_dirty or not _app_config:
		return

	err = write_json(app_config_file, _app_config)
	if err is not None:
		print(f'{_E}ERROR{_00} Failed saving configuration: %s' % str(err))

	_app_config_dirty = False


def print_current():
	print_json(_app_config)


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
			scope[n] = scope[n].get(key)
		# remove scopes where the branch doesn't exist
		scope = [sc for sc in scope if sc is not None]
		if not scope:
			break  # not found anywhere!

		current.append(key)

	if not scope:
		scope = default_value
	else:
		# use first value (higher prio)
		scope = scope[0]

	if convert is not None:
		scope = convert(scope)

	return scope


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


def set(path:str, value:Any, store:Store|None=Store.Persistent) -> None:
	# path: key/key/key
	keys = path.split('/')
	if not keys:
		raise RuntimeError('Empty key path')

	store = store or Store.Memory
	config:ValueType = _config_stores.get(store)
	if store and config is None:
		raise RuntimeError('invalid config store "%s" (one of %s)' % (store, ', '.join(_config_stores.keys())))
	if not isinstance(config, dict): # to shut mypy up
		return None

	scope = config

	current:list[str] = []
	while keys:
		key = keys.pop(0)

		if not keys:  # leaf key
			scope[key] = value
			break

		new_scope:dict = scope.get(key)
		if new_scope is None:  # missing key (object container)
			new_scope = {}
			scope[key] = new_scope

		if not isinstance(new_scope, dict): # exists, but is not an object
			raise RuntimeError('Invalid path "%s"; not object at "%s", got %s (%s)' % (
				path,
				'/'.join(current),
				scope,
				type(new_scope).__name__,
			))

		scope = new_scope
		current.append(key)


	if store == Store.Persistent:
		global _app_config_dirty
		_app_config_dirty = True
