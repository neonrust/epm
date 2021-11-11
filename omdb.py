import sys
import requests
from urllib.parse import quote as url_escape
from http import HTTPStatus
import json
import concurrent.futures
from datetime import datetime, date
import re
import os

_bad_key = 'NO_OMDB_API_KEY_SET'
_base_url_tmpl = 'https://www.omdbapi.com/?apikey=%s'
_base_url = _base_url_tmpl % os.getenv('OMDB_API_KEY', _bad_key)

def set_api_key(key):
	global _base_url
	_base_url = _base_url_tmpl % key

__recent_searches = {}

def search(search, type='series', year=None):

	if _bad_key in _base_url:
		raise RuntimeError('API key not set')

	search_mode = 's'  # search by title
	if search.startswith('tt'): # assume it's an IMDb ID
		search_mode = 'i' # search by IMDb ID

	url = _base_url + f'&type={type}&{search_mode}={search}'
	if year is not None:
		url += f'&y={year}'

	url += '&detail=full'

	if url in __recent_searches:
		return __recent_searches.get(url)

	resp = requests.get(url)
	if resp.status_code != HTTPStatus.OK:
		return []

	data = json.loads(resp.content)
	hits = data.get('Search', [])

	_lower_case_keys(hits)
	_strip_keys(hits, ['type'])
	_rename_keys(hits, [('imdbid', 'id')])
	_set_values(hits, {
		'year': lambda v: list(
			filter(
				lambda v: isinstance(v, int),
				(int(y) if y else '' for y in re.split(r'[^\d]+', v.strip())),
			)
		),
	})

	__recent_searches[url] = hits

	return hits


def episodes(series_id, details=False):

	if _bad_key in _base_url:
		raise RuntimeError('API key not set')

	episodes = []

	def fetch_season(season):
		url = _base_url + '&i=%s&Season=%d' % (series_id, season)
		if details:
			url += '&detail=full'

		resp = requests.get(url)
		if resp.status_code != HTTPStatus.OK:
			return

		data = json.loads(resp.content)
		episodes = data.get('Episodes', [])

		_del_na(episodes)
		_del_keys(episodes, ['rated'])
		_lower_case_keys(episodes)
		_rename_keys(episodes, [('imdbid', 'id'), ('released', 'date')])
		_set_values(episodes, {
			'season': lambda _: season,
			'episode': int,
			'date': lambda v: str(datetime.strptime(v, '%d %b %Y').date()) if len(v.split()) == 3 else str(date.fromisoformat(v)),
			'runtime': lambda v: int(v.split()[0])*60,
			'year': int,
		})
		_del_keys(episodes, ['year'])

		if season == 1:
			return int(data.get('totalSeasons', 1)), episodes
		return episodes

	# fetch first season, also returning the total number of seasons
	last_season, episodes = fetch_season(1)

	if last_season > 1:
		# then fetch the rest of the seasons, in parallel
		with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
			promises = [
				executor.submit(fetch_season, season)
				for season in range(2, last_season + 1)
			]
			concurrent.futures.wait(promises)
	else:
		promises = []

	for promise in promises:
		episodes += promise.result()

	return episodes

def _del_na(data):
	if type(data) is list:
		for item in data:
			_del_na(item)

	elif type(data) is dict:
		for key, value in list(data.items()):
			if isinstance(value, str) and value.lower().strip() == 'n/a':
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

def _strip_keys(data, strip):
	if type(data) is list:
		for item in data:
			_strip_keys(item, strip)

	elif type(data) is dict:
		for key in strip:
			data.pop(key, None)

_missing = object()

def _rename_keys(data, renames):
	if type(data) is list:
		for item in data:
			_rename_keys(item, renames)

	elif type(data) is dict:
		for old, new in renames:
			value = data.pop(old, _missing)
			if value is not _missing:
				data[new] = value

def _set_values(data, new_values):
	if type(data) is list:
		for item in data:
			_set_values(item, new_values)

	elif type(data) is dict:
		for key, setter in new_values.items():
			existing = data.get(key)
			try:
				data[key] = setter(existing)
			except Exception as e:
				if existing is not None:
					print('_set_values:', key, existing, str(e), file=sys.stderr)
