from datetime import datetime
from os.path import basename, dirname, expandvars, expanduser, exists as pexists, getsize as psize, join as pjoin

import os
from subprocess import run
from tempfile import mkstemp
import sys

from typing import Any, TypeVar
from types import ModuleType as Module

from .styles import _0, _00, _0B, _c, _i, _b, _f, _fi, _K, _E, _o, _g, _L, _S, _u, _EOL

# use orjson if available
orjson:Module|None = None
try:
	import orjson as _orjson
	orjson = _orjson
except ImportError:
	orjson = None

import json

PRG = ''

class FatalJSONError(ValueError):
	pass

def json_serializer() -> str:
	if orjson is not None:
		return 'orjson'
	return 'json'


def warning_prefix(context_name:str|None=None) -> str:
	if context_name is not None:
		return f'{_c}[{_00}{_b}{PRG} {context_name}{_c}]{_00}'
	return f'{_c}[{_00}{_b}{PRG}{_c}]{_00}'


def read_json(filepath:str) -> dict:
	if pexists(filepath) and psize(filepath) > 1:
		try:
			if orjson is not None:
				with open(filepath, 'rb') as fp:
					return orjson.loads(fp.read())
			else:
				with open(filepath, 'r') as fp:
					return json.load(fp)

		except json.JSONDecodeError as jde:
			_dump_decode_error(jde, filepath)
			raise FatalJSONError(jde)

	return {}


def _dump_decode_error(err, filepath:str) -> None:
	if hasattr(err, 'lineno') and hasattr(err, 'colno'):
		line_num = 0
		print(f'{_E}ERROR{_00} Failed to read JSON ({filepath}:{err.lineno}:{err.colno}): {err.msg}', file=sys.stderr)
		with open(filepath) as fp:
			for line in fp:
				line_num += 1
				if line_num in (err.lineno - 1, err.lineno + 1):
					print(f'   {line}', end='')
				elif line_num == err.lineno:
					N = err.colno - 1
					line = line.rstrip()
					# print('N:', N, 'len:', len(line))
					left = line[:N - 1]
					# print(f'left>{left}<')
					bad_part = line[N - 1]
					rest = line[N - 1:]
					right = rest[1:] if rest else ''
					print(f'{_f}>>{_0} {left}{_E}{bad_part}{_00}{right} {_f}<<{_0}', file=sys.stderr)
					#print(f'{_b}{"^":>{err.colno + 3}}{_0}', file=sys.stderr)

				if line_num == err.lineno + 1:
					break


def write_json(filepath:str, data:Any) -> Exception|None:
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


def print_json(o:dict) -> None:
	if orjson is not None:
		s = orjson.dumps(o, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
	else:
		s = json.dumps(o,indent=2, sort_keys=True)
	print(s.decode('utf-8'))


_term_size = (0, 0)

def term_size() -> tuple[int, int]:
	global _term_size
	if _term_size != (0, 0):
		return _term_size

	try:
		stty = run(['stty', 'size'], capture_output=True)
		stty_size = stty.stdout.decode('utf-8').split()
		_term_size = (int(stty_size[1]), int(stty_size[0]))
	except:
		_term_size = (100, 60)

	return _term_size


def pexpand(p):
	return expanduser(expandvars(p))


def plural(n: int | list | tuple | dict) -> str:
	if isinstance(n, (list, tuple, dict)):
		N = len(n)
	else:
		N = n
	return '' if N == 1 else 's'


class BadIndexSpecifier(ValueError):
	pass

class ListIndex:
	"""
	Examples:
	   'a55' ->  1*100 + 55         =   155
	   'z12' -> 26*100 + 12         =  2612
	  'db34' -> (4*26 + 2)*100 + 34 = 10634
	"""
	def __init__(self, n:int):
		self._n = n
		self._l = n % 100
		n //= 100
		high_int = n
		high_digits = []
		for digit in str(high_int):
			c = chr(int(digit) - ord('0') + ord('a'))
			high_digits.append(c)

		self._h = ''.join(high_digits)

	def __eq__(self, n: int|Any):  # mypy doesn't support recursion
		if isinstance(n, int):
			return n == self._n
		return n.high == self._h and n.low == self._l

	def toint(self) -> int:
		return self._n

	@property
	def high(self) -> str:
		return self._h

	@property
	def low(self) -> str:
		return str(self._l)

	@property
	def components(self) -> tuple[str, int]:
		return self._h, self._l

	def __str__(self) -> str:
		return f'{self._h}{self._l}'


def clrline():
	print(f'{_00}\r{_K}', end='')

T = TypeVar('T')
def cap(v:T, lower:T|None, upper:T|None) -> T:
	if lower is not None and v < lower:  # type: ignore
		return lower
	elif upper is not None and v > upper:  # type: ignore
		return upper
	return v

def now_stamp() -> str:
	"""Only evaluates once; the same value will always be returned."""
	return now_datetime().isoformat(' ', timespec='seconds')


_now_datetime = None
def now_datetime() -> datetime:
	"""Only evaluates once; the same value will always be returned."""
	global _now_datetime
	if _now_datetime is None:
		_now_datetime = datetime.now()
	return _now_datetime



def _init():
	global PRG
	PRG = basename(sys.argv[0])

_init()
