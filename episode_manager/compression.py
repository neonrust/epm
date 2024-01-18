import os
import io
import shutil
import importlib
from subprocess import run, Popen, PIPE
from typing import BinaryIO, IO

from .config import debug

#CompressorType = TypeVar('CompressorType', bound=dict[str, str|list[str]|int|Callable[[Any, str, str]. bool]])

# detected (preferred) compression method
_compressor:dict|None = None



def compress_file(source:str, destination:str) -> bool:
	if not _compressor:
		os.rename(source, destination)
		return True

	return _compressor['compress'](_compressor, source, destination)


def open(source:str) -> BinaryIO:
	if not _compressor:
		return io.open(source, 'rb')

	return _compressor['open'](_compressor, source)


def from_file(filename:str) -> dict|None:
	parts = filename.rsplit('.', 1)
	if len(parts) < 2:
		return None
	extension = f'.{parts[1]}'

	for method in _compressors:
		if method['extension'] == extension:
			return method

	return None



def _zstandard_compress(method:dict, source:str, destination:str) -> bool:
	import zstandard
	compressor = zstandard.ZstdCompressor(level=method['level'])
	with io.open(source, 'rb') as sfp, io.open(destination, 'wb') as dfp:
		compressor.copy_stream(sfp, dfp)

	_copy_times(source, destination)
	os.remove(source)
	return True

def _zstandard_open(method:dict, source:str) -> BinaryIO:
	import zstandard
	fp = io.open(source, 'rb')
	dctx = zstandard.ZstdDecompressor()
	return dctx.stream_reader(fp)

def _gzip_compress(method:dict, source:str, destination:str) -> bool:
	import gzip
	with io.open(source, 'rb') as sfp, io.open(destination, 'wb') as dfp:
		compressed = gzip.compress(sfp.read(), compresslevel=method['level'])
		if not compressed:
			return False
		dfp.write(compressed)

	_copy_times(source, destination)
	os.remove(source)
	return True

def _gzip_open(method:dict, source:str) -> IO[bytes]|None:
	import gzip
	fp = gzip.open(source)
	return fp # type: ignore

def _xz_compress(method:dict, source:str, destination:str) -> bool:
	import lzma
	with io.open(source, 'rb') as sfp, io.open(destination, 'wb') as dfp:
		compressor = lzma.LZMACompressor(preset=method['level'])
		compressed = compressor.compress(sfp.read())
		if not compressed:
			return False
		dfp.write(compressed)

	_copy_times(source, destination)
	os.remove(source)
	return True

def _xz_open(method:dict, source:str) -> IO[bytes]|None:
	import lzma
	return lzma.open(source)


def _compress_external(method:dict, source:str, destination:str) -> bool:

	command_line = [ method['binary'] ] # type: ignore
	command_line += method.get('args', [])

	success = False  # always assume failure  ;)

	try:
		with io.open(source, 'rb') as sfp, io.open(destination, 'wb') as dfp:
			comp = run(command_line, stdin=sfp, stdout=dfp)
			success = comp.returncode == 0
			if not success:
				try:
					os.remove(destination)
				except FileNotFoundError:
					pass
				raise RuntimeError('exit code: %d' % comp.returncode)

		_copy_times(source, destination)
		os.remove(source)

	except Exception as e:
		# (de)compression failed, just fall back to uncomrpessed
		print(f'\x1b[41;97;1mERROR\x1b[m Compressing file failed: {e}')

	return success


def _open_external(method:dict, source:str) -> IO[bytes]|None:
	command_line = [method['binary']] + method['unargs'] + method['pipe'] # type: ignore
	sfp = io.open(source, 'rb')
	return Popen(command_line, stdin=sfp, stdout=PIPE, close_fds=True).stdout


def _copy_times(source:str, destination:str):
	# copy timestamps from the source
	source_stat = os.stat(source)
	os.utime(destination, (source_stat.st_atime, source_stat.st_mtime))



def _detect_package(name):
	def detect(method:dict) -> bool:
		try:
			importlib.import_module(name)
			return True
		except ImportError:
			return False

	detect.__name__ = f'detect_{name}'
	return detect

def _detect_external(name):
	def detect(method:dict) -> bool:
		which = shutil.which(name)
		if not which:
			return False

		method['binary'] = which
		return True

	detect.__name__ = f'detect_{name}'
	return detect


ZSTD_LEVEL = 15
LZ4_LEVEL = 9
XZ_LEVEL = 6
GZIP_LEVEL = 9

_compressors:list[dict] = [
    {
	    'name': 'python-zstandard',
		'detect': _detect_package('zstandard'),
		'level': ZSTD_LEVEL,
		'compress': _zstandard_compress,
		'open': _zstandard_open,
		'extension': '.zst',
	},
	{
	    'detect': _detect_external('zstd'),
		'compress': _compress_external,
		'': _open_external,
		'args': [ f'-{ZSTD_LEVEL}', '--quiet', '--threads=0' ],
		'unargs': [ '--decompress', '--quiet', '--threads=0' ],
		'pipe': [ '--stdout' ],
		'extension': '.zst',
	},
	{
	    'detect': _detect_external('lz4'),
		'compress': _compress_external,
		'open': _open_external,
		'args': [ f'-{LZ4_LEVEL}', '--quiet' ],
		'unargs': [ '--decompress', '--quiet' ],
		'pipe': [ '--stdout' ],
		'extension': '.lz4',
	},
	{
	    'name': 'python-xz',
		'detect': _detect_package('lzma'),
		'level': XZ_LEVEL,
		'compress': _xz_compress,
		'open': _xz_open,
		'extension': '.xz',
	},
	{
	    'detect': _detect_external('xz'),
		'compress': _compress_external,
		'open': _open_external,
		'args': [ f'-{XZ_LEVEL}', '--quiet' ],
		'unargs': [ '--decompress', '--quiet' ],
		'pipe': [ '--stdout' ],
		'extension': '.xz',
	},
	{
	    'name': 'python-gzip',
		'detect': _detect_package('gzip'),
		'level': GZIP_LEVEL,
		'compress': _gzip_compress,
		'open': _gzip_open,
		'extension': '.gz',
	},
	{
	    'detect': _detect_external('gzip'),
		'compress': _compress_external,
		'open': _open_external,
		'args': [ f'-{GZIP_LEVEL}', '--quiet' ],
		'unargs': [ '--decompress', '--quiet' ],
		'pipe': [ '--stdout' ],
		'extension': '.gz',
	},
]

# detect which of the above compressor are available (in order of desirability)
def _init():
	global _compressor
	for method in _compressors:
		if method['detect'](method):
			_compressor = method
			debug('cmpr: detected compressor:', method.get('name') or method.get('binary'))
			break

	if not _compressor:
		raise RuntimeError('no compressor available (tried: %s)' % (', '.join(c['binary'] for c in _compressors)))

def compressor() -> str|None:
	if not _compressor:
		return None
	return _compressor.get('name') or _compressor.get('binary')

def method() -> dict|None:
	return _compressor


_init()
