import os
from os.path import basename, dirname, expandvars, expanduser, exists as pexists, getsize as psize, join as pjoin

from .utils import read_json, write_json, warning_prefix, pexpand

from typing import Any

default_max_refresh_age = 2  # days
default_max_hits = 10

user_config_home = os.getenv('XDG_CONFIG_HOME') or pexpand(pjoin('$HOME', '.config'))
app_config_file = ''

PRG = ''

def init(prg):
	global PRG
	PRG = prg
	global app_config_file
	app_config_file = pjoin(user_config_home, PRG, 'config')


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
	'num-backups': 10,
	'lookup': {
		'api-key': None,
		'max-hits': default_max_hits,
	},
	'debug': 0,
}

app_config = {}
app_config_dirty = False


def load() -> bool:
	global app_config
	global app_config_dirty

	app_config = read_json(app_config_file)
	app_config_dirty = False

	config = {**default_configuration}
	config.update(app_config)
	app_config = config

	db_file = get('paths/series-db')
	if not db_file or not isinstance(db_file, str):
		set('paths/series-db', pjoin(user_config_home, PRG, 'series'), dirty=False)

	paths = app_config.get('paths', {})
	if not isinstance(paths, dict):
		raise RuntimeError(f'{warning_prefix()} Config key "paths" is not an object')

	for key in paths.keys():
		paths[key] = pexpand(paths[key])

	app_config_dirty = False

	return len(app_config) > 0


def save():
	global app_config_dirty
	if not app_config_dirty:
		return

	err = write_json(app_config_file, app_config)
	if err is not None:
		print(f'{_E}ERROR{_00} Failed saving configuration: %s' % str(err))

	app_config_dirty = False

# type alias for type hints (should be recursive, but mypy doesn't support it)
ConfigValue = str|int|float|dict|list

def get(path:str, default_value:ConfigValue|None=None, convert=None) -> ConfigValue|None:
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


def get_int(path:str, default_value:int=0) -> int:
	v = get(path, default_value)
	if isinstance(v, (str, int)):
		return int(v)
	return default_value


def get_bool(path:str, default_value:bool=False) -> bool:
	v = get(path, default_value)
	if isinstance(v, (str, bool)):
		return bool(v)
	return default_value


def set(path:str, value:Any, dirty:bool=True) -> None:
	# path: key/key/key
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

	if dirty:
		global app_config_dirty
		app_config_dirty = True
