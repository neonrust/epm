import unittest
import os

from episode_manager import config

test_config_file = 'test_config'

class TestConfig(unittest.TestCase):
	def test_load_nonexistent(self) -> None:
		config.app_config_file = 'this-file-does-not-exist'
		config.load()

	def test_load(self) -> None:
		self.load_config('{ "key": "value" }')

	def test_get(self) -> None:
		self.load_config('{ "key": "value" }')

		self.assertEqual(config.get('key'), 'value')

	def test_get_fallback(self) -> None:
		self.load_config('{ "nothing": "useful" }')

		self.assertEqual(config.get('max-age'), 2)

	def test_set_override(self) -> None:
		self.load_config('{ "nothing": "useful" }')
		self.assertEqual(config.get('max-age'), 2)

		config.set('max-age', 42, store=config.Store.Memory)
		self.assertFalse(config.save())

	def test_get_override(self) -> None:
		self.load_config('{ "nothing": "useful" }')

		self.assertEqual(config.get('max-age'), 2)

		config.set('max-age', 42, store=config.Store.Memory)

		val = config.get_int('max-age')
		self.assertEqual(val, 42)


	def tearDown(self) -> None:
		try:
			os.remove(test_config_file)
		except:
			pass
		config.forget_all(config.Store.Memory)

	def load_config(self, content):
		# print('create config file:', content)
		with open(test_config_file, 'w') as fp:
			print(content, file=fp)
		config.app_config_file = test_config_file
		config.load()
		# config.print_json(config._app_config)
