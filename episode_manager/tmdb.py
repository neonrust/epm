import sys
import requests
import json
import time
import os
import builtins
from requests import ReadTimeout, ConnectTimeout
from urllib.parse import quote as url_escape
from http import HTTPStatus
import concurrent.futures as futures
from datetime import datetime, timedelta
from collections.abc import Iterable
from typing import Callable, Any

_base_url_tmpl = 'https://api.themoviedb.org/3/%%(path)s?api_key=%s'
_base_url:str|None = None
_api_key:str|None = None

global_headers = {
	'User-Agent': 'EpisodeManager/0',
}

env_key_name = 'TMDB_API_KEY'

api_key_help = 'Set "%s" environment variable for your account.' % env_key_name

_raw_output = bool(os.getenv('TMDB_RAW'))

_image_url_prefix = 'https://image.tmdb.org/t/p/w500/'

class NoAPIKey(RuntimeError):
	pass

class APIAuthError(RuntimeError):
	pass

class NetworkError(RuntimeError):
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


def _qurl(endpoint:str, query:dict|None=None) -> str:
	raise NotImplementedError('_qurl')

def key_from_env() -> str|None:
	return os.getenv(env_key_name)

def set_api_key(key:str) -> None:
	global _api_key
	_api_key = key

	if _api_key:
		global _base_url
		_base_url = _base_url_tmpl % _api_key
		_update_url_func()

def ok() -> bool:
	return bool(_api_key)

def _query(url:str) -> dict[str, Any]|None:
	# print('\x1b[2mquery: %s\x1b[m' % url)
	try:
		resp = requests.get(url, headers=global_headers, timeout=10)
		# print('\x1b[2mquery: DONE %s\x1b[m' % url)
	except (ReadTimeout, ConnectTimeout):
		# print('\x1b[41;97;1mquery: TIMEOUT %s\x1b[m' % url)
		return None

	if resp.status_code == HTTPStatus.UNAUTHORIZED:
		raise APIAuthError()

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

	query:dict[str,str] = {
		'query': search,
	}
	if year is not None:
		query['first_air_date_year'] = str(year)

	if page >= 1:
		query['page'] = str(page)

	url = _qurl(path, query)

	if url in __recent_searches:
		return __recent_searches.get(url)

	data = _query(url)
	if not data:
		return []

	total_results = data.get('total_results', 0)

	hits = data.get('results', [])

	if not _raw_output:
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


__details:dict = {}
_missing = object()

def details(title_id:str|list[str]|Iterable, type='series') -> dict:

	if not _api_key:
		raise NoAPIKey()

	if isinstance(title_id, Iterable) and not isinstance(title_id, str):
		wrapped_args:list = list(map(lambda I: ( (I,), {} ) , title_id))
		return _parallel_query(details, wrapped_args)

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

	if not _raw_output:
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
			'id',
			'tagline',
			'created_by',
			'adult',
			'episode_run_time',
		])
		_set_values(data, {
			'year': lambda _: [int(data.get('date', [0]).split('-')[0])] if data.get('date') else None,
			'country': lambda _: ', '.join(data.get('country')),
			'genre': lambda _: ', '.join(map(lambda g: g.get('name'), data.get('genres'))),
			'status': lambda _: _map_status(data.get('status')) if 'status' in data else None,
		})
		_del_keys(data, ['genres'])

		if data.get('status') in ('ended', 'canceled') and 'end_date' in data and 'year' in data:
			data['year'] = data['year'] + [ int(data.get('end_date').split('-')[0]) ]
		else:
			del data['end_date']

		_del_empty(data)

		credits = promises[2].result() or {}
		cast = credits.get('cast', [])
		crew = credits.get('crew', [])

		seasons = data.pop('seasons', [])
		specials_info = list(filter(lambda season: season.get('season_number') == 0, seasons))
		if specials_info:
			specials_info = specials_info[0]
			data['specials'] = specials_info.get('episode_count', 1)

		_set_values(data, {
			'director': lambda ep: _job_people(crew, 'Director'),
			'writer': lambda ep: _job_people(crew, 'Writer'),
			'cast': lambda ep: list(map(lambda p: p.get('name') or '', cast))
		})

	__details[title_id] = data

	return data


def episodes(series_id:str|list[str]|Iterable, with_details=False, progress:Callable|None=None) -> list:

	if not _api_key:
		raise NoAPIKey()

	if _qurl is None:
		return []

	if isinstance(series_id, Iterable) and not isinstance(series_id, str):
		wrapped_args = map(lambda sid: ( (sid,), {'with_details': with_details} ), series_id)
		return _parallel_query(episodes, wrapped_args, progress_callback=progress)

	# unfortunately we must synchronously get the details first
	ser_details = details(series_id, type='series')

	num_seasons = (ser_details or {}).get('total_seasons', 1)
	has_specials = bool(ser_details.get('specials'))
	standard_ep_runtime = (ser_details or {}).get('episode_run_time')

	def fetch_season(season):
		data = _query(_qurl('tv/%s/season/%d' % (series_id, season))) or {}

		data = data.get('episodes', [])

		if not _raw_output:
			_rename_keys(data, {
				'name': 'title',
				'first_air_date': 'date',
				'original_name': 'original_title',
				'original_language': 'language',
				'origin_country': 'country',
				'air_date': 'date',
				'season_number': 'season',
				'episode_number': 'episode',
			})
			_set_values(data, {
				'director': lambda ep: _job_people(ep.get('crew', []), 'Director'),
				'writer': lambda ep: _job_people(ep.get('crew', []), 'Writer'),
				'guest_cast': lambda ep: list(map(lambda p: p.get('name') or '', ep.get('guest_stars', []))),
				'season': lambda ep: 'S' if ep.get('season') == 0 else ep.get('season'),
			})
			_del_keys(data, [
				'id',
				'show_id',
				'still_path',
				'crew',
				'guest_stars',
				'production_code',
				'vote_average',
				'vote_count',
			])
			_del_empty(data)

		return data

	# then fetch all the seasons, in parallel
	with __get_executor() as executor:
		promises = [
			executor.submit(fetch_season, season)
			for season in range(1, num_seasons + 1)
		]
		if has_specials:
			promises.append(executor.submit(fetch_season, 0))

	all_episodes = [
		episode
		for promise in promises
		for episode in promise.result()
	]

	# set runtime of each episode, if needed and known
	if standard_ep_runtime:
		for ep in all_episodes:
			if not ep.get('runtime'):
				ep['runtime'] = standard_ep_runtime

	if with_details:
		return ser_details, all_episodes

	return all_episodes


def changes(series_id:str|list[str], after:datetime, include:list|tuple|None=None, progress:Callable|None=None) -> list:

	if _qurl is None:
		return []

	if isinstance(series_id, Iterable) and not isinstance(series_id, str):
		wrapped_args = map(lambda sid: ( (sid, after), {'include': include} ), series_id)
		return _parallel_query(changes, wrapped_args, progress_callback=progress)

	now = datetime.now().date().isoformat()
	after_str = after.date().isoformat()

	data = _query(_qurl('tv/%s/changes' % series_id, {'start_date': after_str, 'end_date': now}))
	# TOOD: get all pages

	change_list = (data or {}).get('changes', [])

	# if specified, only include requested entries
	if change_list and isinstance(include, (tuple, list)):
		def accept_included(chg:dict) -> bool:
			ok = chg.get('key') in include  # type: ignore  # 'include' is a sequence
			# if not ok:
			# 	print(series_id, '\x1b[2mignored change:', chg.get('key'), '\x1b[m')
			return ok

		change_list = list(filter(accept_included, change_list))

	return change_list


def posters(series_id:str, season:int|list[int]|tuple[int]|None, language:str|None=None) -> dict:
	# 'season' = None: only main posters for the series
	# 'season' = 1: all posters for the specified season
	# 'season' = [2,3,4]: all posters for the specified seasons

	if _qurl is None:
		return []

	query = {}
	language = 'en'
	if language:
		query['language'] = language

	if season is None:
		data = _query(_qurl('tv/%s/images' % series_id, query))
	elif isinstance(season, int):
		data = _query(_qurl('tv/%s/season/%s/images' % (series_id, season), query))
	elif isinstance(season, (tuple, list)):
		wrapped_args = map(lambda season: ( (series_id, season), {'language': language} ), season)
		return _parallel_query(posters, wrapped_args)

	images = data.get('posters')

	if not _raw_output:
		_del_keys(images, [
			'aspect_ratio',
			'vote_count'
		])
		_rename_keys(images, {
			'iso_639_1': 'language',
		})
		_set_values(images, {
			'url': lambda poster: _image_url_prefix + poster['file_path'].lstrip('/'),
		})
		_del_keys(images, [
			'file_path',
		])

	return images


def find_imdb(imdb_id:str) -> dict:
	data = _query(_qurl('find/%s' % imdb_id, {'external_source': 'imdb_id'}))

	if not _raw_output:
		pass

	return data


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
	if isinstance(data, list):
		for item in data:
			_del_empty(item)

	elif isinstance(data, dict):
		for key, value in list(data.items()):
			if value is None:
				del data[key]

def _del_keys(data, keys):
	if isinstance(data, list):
		for item in data:
			_del_keys(item, keys)

	elif isinstance(data, dict):
		for key in keys:
			data.pop(key, 0)

def _lower_case_keys(data):
	if isinstance(data, list):
		for item in data:
			_lower_case_keys(item)

	elif isinstance(data, dict):
		for key, value in list(data.items()):
			if type(key) is str:
				keyL = key.lower()
				if keyL != key:
					del data[key]
					data[keyL] = value

_missing = object()

def _rename_keys(data, renames):
	if isinstance(data, list):
		for item in data:
			_rename_keys(item, renames)

	elif isinstance(data, dict):
		for old, new in renames.items():
			value = data.pop(old, _missing)
			if value is not _missing:
				data[new] = value

def _set_values(data, new_values):
	if isinstance(data, list):
		for item in data:
			_set_values(item, new_values)

	elif isinstance(data, dict):
		for key, setter in new_values.items():
			try:
				value = setter(data)
				if value not in (None, '', [], {}):
					data[key] = value
				else:
					data.pop(key, None)
			except Exception as e:
				print('_set_values: "%s":' % key, str(e), file=sys.stderr)


def _parallel_query(func:Callable, arg_list:list|map, progress_callback:Callable|None=None):

	completed = 0

	def func_wrap(idx, *args, **kw):
		t0 = time.time()

		res = func(*args, **kw)

		duration = time.time() - t0
		if progress_callback:
			nonlocal completed
			completed += 1
			progress_callback(completed, idx, duration, args)
		return res

	with __get_executor() as executor:
		promises = [
			executor.submit(func_wrap, idx, *args, **kw)
			for idx, (args, kw) in enumerate(arg_list)
		]

	try:
		return [
			p.result()
			for p in promises
		]
	except requests.exceptions.ConnectionError as ce:
		raise NetworkError(str(ce))



def _self_test(args):
	def next(required=True, conv=str):
		if required or args:
			return conv(args.pop(0))
		else:
			return None

	def all_next():
		v = list(args)
		del args[:]
		return v

	op = next()

	if op == 's':
		print('SEARCH', file=sys.stderr)
		info = search(next(), year=next(required=False, conv=int))

	elif op == 'i':  # IMDb
		print('IMDB', file=sys.stderr)
		info = find_imdb(next())

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
		series_id = next()
		dt = datetime.now() - timedelta(days=int(next()))
		info = changes(series_id, after=dt)#, include=('overview', 'season'))

	elif op == 'cp':
		print('CHANGES   PARALLEL', file=sys.stderr)
		dt = datetime.now() - timedelta(days=int(next()))
		info = changes(all_next(), after=dt, include=('overview', 'season'))

	elif op == 'im':
		print('IMAGES', file=sys.stderr)
		series_id = next()
		try: season = [int(n) for n in all_next()]
		except ValueError as ve:
			print('bad season:', ve, file=sys.stderr);
			sys.exit(1)
		if len(season) == 1:
			season = season[0]
		info = posters(series_id, season=season)

	else:
		print('_self_test: <op> [args...]', file=sys.stderr)
		print('   <op> one of s(earch) e(pisodes) d(etails) c(hanges)', file=sys.stderr)

	print(json.dumps(info, indent=2))
	print('ENTRIES: %d' % len(info), file=sys.stderr)


if __name__ == '__main__':
	set_api_key(key_from_env() or '')
	_self_test(sys.argv[1:])
