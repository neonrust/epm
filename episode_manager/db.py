import time
import sys
import os
from os.path import dirname, exists as pexists
from subprocess import run
from tempfile import mkstemp

from . import config
from .utils import read_json, write_json, warning_prefix, json_serializer
from .styles import _0, _00, _0B, _c, _i, _b, _f, _fi, _K, _E, _o, _g, _L, _S, _u, _EOL

from typing import Any

DB_VERSION = 2

def code_version() -> int:
	return DB_VERSION

def load() -> dict:

	db_file = str(config.get('paths/series-db'))

	t0 = time.time()

	if not db_file or not pexists(dirname(db_file)):
		raise RuntimeError('Invalid series db file path: %r' % db_file)

	db = read_json(db_file)

	t1 = time.time()
	if config.get_bool('debug'):
		ms = (t1 - t0)*1000
		print(f'{_f}[db: %d entries in %.1fms; v%d]{_0}' % (len(db) - 1, ms, meta_get(db, meta_version_key)))

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

	# 1. migrate legacy series meta data
	fixed_legacy_meta = 0
	# 2. fix incorrectly written value to 'archived'
	fixed_archived = 0

	for series_id, series in db.items():
		if series_id == meta_key:
			continue

		if db_version == 0:
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
		meta_set(db, 'next_list_index', list_index)
		print(f'{_f}Built list indexes for all %d series, next index: %d{_0}' % (len(db) - 1, list_index))
		modified = True

	if fixed_legacy_meta:
		print(f'{_f}Migrated legacy meta-data of %d series{_0}' % fixed_legacy_meta)
		modified = True

	if fixed_archived:
		print(f'{_f}Fixed bad "archived" value of %d series{_0}' % fixed_archived)
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
	err = write_json(tmp_name, db)
	if err is None:
		# rotate backups
		for idx in range(config.get_int('num-backups')):
			if pexists(backup_name(idx)):
				os.rename(backup_name(idx), backup_name(idx + 1))

		# current file becomes first backup (<name>.1)
		# TODO: spawn background process to compress to make it appear faster?
		#   might run into (more) race-conditions of course

		# backup existing(old) db file to 'series.1'
		mk_backup(db_file, backup_name(1))

		os.rename(tmp_name, db_file)

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


meta_key = 'epm:meta'
meta_added_key = 'added'
meta_seen_key = 'seen'
meta_archived_key = 'archived'
meta_list_index_key = 'list_index'
meta_next_list_index_key = 'next_list_index'
meta_updated_key = 'updated'
meta_version_key = 'version'


meta_legacy_keys = (
	meta_added_key,
	meta_updated_key,
	meta_seen_key,
	meta_archived_key,
)
