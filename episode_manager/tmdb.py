import sys
import requests
from requests import ReadTimeout, ConnectTimeout
from urllib.parse import quote as url_escape
from http import HTTPStatus
import json
import concurrent.futures as futures
from datetime import datetime, timedelta
import time
import os
import builtins
from collections.abc import Iterable
from typing import Callable, Any

# TODO: API version 4 ?
_base_url_tmpl = 'https://api.themoviedb.org/3/%%(path)s?api_key=%s'
_base_url:str|None = None
_api_key = os.getenv('TMDB_API_KEY', '')

api_key_help = 'Set "TMDB_API_KEY" environment variable for your account.'

class NoAPIKey(RuntimeError):
	pass


__parallel_requests = 16

def set_parallel(num) -> None:
	global __parallel_requests
	__parallel_requests = max(1, int(num or 1))

def __get_executor(n=__parallel_requests):
	return futures.ThreadPoolExecutor(max_workers=n, thread_name_prefix='tmdb-request')


def _update_url_func() -> None:
	def mk_url(endpoint:str, query:dict|None=None) -> str:
		if _base_url is None:
			raise RuntimeError('_base_url is None, which should never happen!')

		url = _base_url % { 'path': endpoint }

		if query is not None:
			q = []
			for k, v in query.items():
				q.append('%s=%s' % (url_escape(k), url_escape(str(v))))
			url += '&%s' % '&'.join(q)

		return url

	global _qurl
	_qurl = mk_url


_qurl:Callable[[str, dict], str]|None = None

def set_api_key(key) -> None:
	global _api_key
	_api_key = key

	if _api_key:
		global _base_url
		_base_url = _base_url_tmpl % _api_key
		_update_url_func()

if _api_key:
	set_api_key(_api_key)

def ok() -> bool:
	return bool(_api_key)

def _query(url) -> dict[str, Any]|None:
	# print('\x1b[2mquery: %s\x1b[m' % url)
	try:
		resp = requests.get(url, timeout=10)
		# print('\x1b[2mquery: DONE %s\x1b[m' % url)
	except (ReadTimeout, ConnectTimeout) as to:
		# print('\x1b[41;97;1mquery: TIMEOUT %s\x1b[m' % url)
		return None

	if resp.status_code != HTTPStatus.OK:
		return None

	return resp.json()


__recent_searches:dict = {}

def search(search:str, type:str='series', year:int|None=None, page:int=1):

	# /search/tv

	if not _api_key:
		raise NoAPIKey()

	if _qurl is None:
		return []

	path = 'search'
	if type == 'series':
		path += '/tv'
	else:
		path += '/movie'

	query = {
		'query': search,
	}
	if year is not None:
		query['first_air_date_year'] = year

	if page >= 1:
		query['page'] = page

	url = _qurl(path, query)

	if url in __recent_searches:
		return __recent_searches.get(url)

	data = _query(url)
	if not data:
		return []

	total_results = data.get('total_results', 0)

	hits = data.get('results', [])

	_rename_keys(hits, {
		'name': 'title',
		'first_air_date': 'date',
		'original_name': 'original_title',
		'original_language': 'language',
		'origin_country': 'country',
	})
	_del_keys(hits, [
		'backdrop_path',
		'popularity',
		'poster_path',
		'vote_average',
		'vote_count',
		'genre_ids',   # for now (in this tool), we don't need these
	])
	_set_values(hits, {
		'year': lambda hit: [int(hit.get('date', [0]).split('-')[0])] if hit.get('date') else None,
		'id': lambda hit: str(hit['id']),
		'country': lambda hit: ', '.join(hit.get('country')),
	})
	_del_empty(hits)

	if builtins.type(hits) is dict:
		hits = [ hits ]

	__recent_searches[url] = hits

	return hits, total_results



__imdb_id_to_tmdb:dict = {}

def _get_tmdb_id(imdb_id):
	data = _query(_qurl('find/%s' % imdb_id, {'external_source':'imdb_id'}))
	if (data or {}).get('tv_results'):
		raise RuntimeError('Unknown IMDb ID: %s' % imdb_id)

	series = data.get('tv_results', [])
	# "there can be only one"
	title_id = series[0]['id']
	__imdb_id_to_tmdb[imdb_id] = str(title_id)

	return title_id


__details:dict = {}
_missing = object()

def details(title_id:str|list[str], type='series'):

	if not _api_key:
		raise NoAPIKey()

	if isinstance(title_id, Iterable) and not isinstance(title_id, str):
		wrapped_args = map(lambda I: ( (I,), {} ) , title_id)
		return _parallel_query(details, wrapped_args)

	if title_id.startswith('tt'):
		title_id = _get_tmdb_id(title_id)

	data = __details.get(title_id, _missing)
	if data is not _missing:
		return data

	detail_path = 'tv/%s' % title_id
	if type == 'film':
		detail_path = 'movie/%s' % title_id

	with __get_executor() as executor:
		promises = [
			executor.submit(_query, _qurl(detail_path)),
			executor.submit(_query, _qurl('tv/%s/external_ids' % title_id)),
			executor.submit(_query, _qurl('tv/%s/credits' % title_id)),
		]

	# details
	data = promises[0].result()
	if not data:
		#print('[tmdb] no details for %s' % title_id, file=sys.stderr)
		return None

	# external IDs
	ext_id = promises[1].result() or {}

	imdb_id = ext_id.get('imdb_id') or None
	if imdb_id:
		data['imdb_id'] = imdb_id

	_rename_keys(data, {
		'name': 'title',
		'first_air_date': 'date',
		'last_air_date': 'end_date',
		'original_name': 'original_title',
		'original_language': 'language',
		'origin_country': 'country',
		'number_of_seasons': 'total_seasons',
		'number_of_episodes': 'total_episodes',
	})
	_del_keys(data, [
		'backdrop_path',
		'popularity',
		'poster_path',
		'vote_average',
		'vote_count',
		'production_companies',
		'production_countries',
		'homepage',
		'in_production',
		'languages',
		'spoken_languages',
		'last_episode_to_air',
		'next_episode_to_air',
		'networks',
		'type',
		'tagline',
		'seasons',
		'created_by',
		'adult',
		'episode_run_time',
	])
	_set_values(data, {
		'year': lambda _: [int(data.get('date', [0]).split('-')[0])] if data.get('date') else None,
		'id': lambda _: str(data['id']),
		'country': lambda _: ', '.join(data.get('country')),
		'genre': lambda _: ', '.join(map(lambda g: g.get('name'), data.get('genres'))),
		'status': lambda _: _map_status(data.get('status')) if 'status' in data else None,
	})
	_del_keys(data, ['genres'])

	if data.get('status') in ('ended', 'canceled') and 'end_date' in data and 'year' in data:
		data['year'] = data['year'] + [ int(data.get('end_date').split('-')[0]) ]
	else:
		del data['end_date']

	credits = promises[2].result() or {}
	cast = credits.get('cast', [])
	crew = credits.get('crew', [])

	_set_values(data, {
		'director': lambda ep: _job_people(crew, 'Director'),
		'writer': lambda ep: _job_people(crew, 'Writer'),
		'cast': lambda ep: list(map(lambda p: p.get('name') or '', cast))
	})

	__details[title_id] = data

	return data


def episodes(series_id:str|list[str], with_details=False, progress:Callable|None=None):

	if not _api_key:
		raise NoAPIKey()

	if _qurl is None:
		return []

	if isinstance(series_id, Iterable) and not isinstance(series_id, str):
		wrapped_args = map(lambda sid: ( (sid,), {'with_details': with_details} ), series_id)
		return _parallel_query(episodes, wrapped_args, progress_callback=progress)

	if series_id.startswith('tt'):
		series_id = _get_tmdb_id(series_id)

	# unfortunately we must synchronously get the details first
	ser_details = details(series_id, type='series')

	num_seasons = ser_details.get('total_seasons', 1)
	ep_runtime = ser_details.get('episode_run_time')

	def fetch_season(season):
		data = _query(_qurl('tv/%s/season/%d' % (series_id, season))) or {}
		data = data.get('episodes', [])

		_rename_keys(data, {
			'name': 'title',
			'first_air_date': 'date',
			'original_name': 'original_title',
			'original_language': 'language',
			'origin_country': 'country',
		})
		_del_keys(data, ['production_code', 'vote_average', 'vote_count'])
		_rename_keys(data, {
			'air_date': 'date',
			'season_number': 'season',
			'episode_number': 'episode',
		})
		_set_values(data, {
			'director': lambda ep: _job_people(ep.get('crew', []), 'Director'),
			'writer': lambda ep: _job_people(ep.get('crew', []), 'Writer'),
			'guest_cast': lambda ep: list(map(lambda p: p.get('name') or '', ep.get('guest_stars', [])))
		})
		_del_keys(data, ['id', 'still_path', 'crew', 'guest_stars'])

		return data

	# then fetch all the seasons, in parallel
	with __get_executor() as executor:
		promises = [
			executor.submit(fetch_season, season)
			for season in range(1, num_seasons + 1)
		]

	all_episodes = [
		episode
		for promise in promises
		for episode in promise.result()
	]

	# if the series contains runtime info, populate each episode (unless already present)
	if ep_runtime:
		for ep in all_episodes:
			if not ep.get('runtime'):
				ep['runtime'] = ep_runtime

	if with_details:
		return ser_details, all_episodes

	return all_episodes


def changes(series_id:str|list[str], after:datetime, ignore:tuple=None, progress:Callable|None=None) -> list:

	if _qurl is None:
		return []

	if isinstance(series_id, Iterable) and not isinstance(series_id, str):
		wrapped_args = map(lambda sid: ( (sid, after), {'ignore': ignore} ), series_id)
		return _parallel_query(changes, wrapped_args, progress_callback=progress)

	now = datetime.now().date().isoformat()
	after_str = after.date().isoformat()

	data = _query(_qurl('tv/%s/changes' % series_id, {'start_date': after_str, 'end_date': now}))

	# remove change entries that was requested to ignore
	if data and data.get('changes') and isinstance(ignore, (tuple, list)):
		def non_ignored(entry):
			return entry.get('key') not in ignore
		data['changes'] = list(filter(non_ignored, data['changes']))

	return (data or {}).get('changes', [])


def _job_people(people, job):
	return list(
		person.get('name')
		for person in people
		if person.get('job') == job
	)

def _map_status(st):
	st = st.lower()
	if st in ('ended', 'canceled'):
		return st
	return 'active'  # TODO: a better term?

def _del_empty(data):
	if type(data) is list:
		for item in data:
			_del_empty(item)

	elif type(data) is dict:
		for key, value in list(data.items()):
			if not value:
				del data[key]

def _del_keys(data, keys):
	if type(data) is list:
		for item in data:
			_del_keys(item, keys)

	elif type(data) is dict:
		for key in keys:
			data.pop(key, 0)

def _lower_case_keys(data):
	if type(data) is list:
		for item in data:
			_lower_case_keys(item)

	elif type(data) is dict:
		for key, value in list(data.items()):
			if type(key) is str:
				keyL = key.lower()
				if keyL != key:
					del data[key]
					data[keyL] = value

_missing = object()

def _rename_keys(data, renames):
	if type(data) is list:
		for item in data:
			_rename_keys(item, renames)

	elif type(data) is dict:
		for old, new in renames.items():
			value = data.pop(old, _missing)
			if value is not _missing:
				data[new] = value

def _set_values(data, new_values):
	if type(data) is list:
		for item in data:
			_set_values(item, new_values)

	elif type(data) is dict:
		for key, setter in new_values.items():
			try:
				value = setter(data)
				if value not in (None, '', [], {}):
					data[key] = value
				else:
					data.pop(key, None)
			except Exception as e:
				print('_set_values: "%s":' % key, str(e), file=sys.stderr)


def _parallel_query(func:Callable, arg_list:list, progress_callback:Callable|None=None):
	def func_wrap(idx, *args, **kw):
		t0 = time.time()

		res = func(*args, **kw)

		duration = time.time() - t0
		if progress_callback:
			progress_callback(idx, duration, args)
		return res

	with __get_executor() as executor:
		promises = [
			executor.submit(func_wrap, idx, *args, **kw)
			for idx, (args, kw) in enumerate(arg_list)
		]

	return [
		p.result()
		for p in promises
	]


def _self_test(args):
	def next(required=True):
		if required:
			return args.pop(0)
		else:
			return args.pop(0, None)

	op = next()

	if op == 's':
		print('SEARCH', file=sys.stderr)
		info = search(next(), year=int(next()))

	elif op == 'e':
		print('EPISODE', file=sys.stderr)
		info = episodes(next())

	elif op == 'ed':
		print('EPISODE + DETAILS', file=sys.stderr)
		info = episodes(next(), with_details=True)

	elif op == 'edp':
		print('EPISODE + DETAILS   PARALLEL', file=sys.stderr)
		info = episodes(args, with_details=True)

	elif op == 'd':
		print('DETAILS', file=sys.stderr)
		info = details(next())

	elif op == 'dp':
		print('DETAILS   PARALLEL', file=sys.stderr)
		info = details(args)

	elif op == 'c':
		print('CHANGES', file=sys.stderr)
		dt = datetime.now() - timedelta(days=int(next()))
		info = changes(next(), after=dt, ignore=('images',))

	elif op == 'cp':
		print('CHANGES   PARALLEL', file=sys.stderr)
		dt = datetime.now() - timedelta(days=int(next()))
		info = changes(args, after=dt, ignore=('images',))

	else:
		print('_self_test: <op> [args...]', file=sys.stderr)
		print('   <op> one of s(earch) e(pisodes) d(etails) c(hanges)', file=sys.stderr)

	print(json.dumps(info, indent=2))
	print('ENTRIES: %d' % len(info), file=sys.stderr)


if __name__ == '__main__':
	_self_test(sys.argv[1:])