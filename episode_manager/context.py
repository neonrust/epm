from . import config, db

from typing import Callable

class BadUsageError(RuntimeError):
	pass


class context:
	def __init__(self):
		self.global_options = {
			'debug': config.get_bool('debug', False),
		}
		self.command:str|None = None
		self.command_options:dict = {
			'max-age': config.get_int('max-age'),
		}
		self.command_arguments:list = []

		self.handler:Callable = self._no_command
		self.db:dict[str,dict] = {}

	def invoke(self, width:int) -> str|None:
		self.db = db.load()

		return self.handler(self, width=width)


	def configure_handler(self, handler_map:dict) -> bool:
		if self.command is not None:
			self.handler = handler_map[self.command]['handler']
			return True

		return False


	def parse_args(self, args:list) -> None:

		default_command = str(config.get('commands/default', 'unseen'))

		while args:
			arg = args.pop(0)

			# print('check arg: "%s"' % arg)

			if arg.startswith('-'):
				if not self.command:
					if arg in '--help':
						raise BadUsageError()

					# attempt to interpret as a global option
					# print('  try global opt: "%s"' % arg)
					if self.eat_option(None, arg, args, self.global_options, unknown_ok=True):
						# print('  -> global opt:', arg)
						continue

					self._set_command(default_command)
					# print('  -> cmd: %s (default)' % self.command)

				# print('  opt:', arg, '(cmd: %s)' % self.command)
				self.eat_option(self.command, arg, args, self.command_options)  # will exit if not correct
				continue

			if not self.command and not arg.startswith('.'):
				# print('  try cmd: "%s"' % arg)
				cmd = self.resolve_cmd(arg)
				if cmd:
					self._set_command(cmd)
					# print('  -> cmd = %s' % self.command)
					continue

			if not self.command:
				if arg.startswith('.'):
					arg = arg[1: ]

				self._set_command(default_command)
				# print('  -> cmd = %s (default)' % self.command)

			if self.command:
				self._add_argument(arg)
				# print('  -> "%s" [%s]' % (self.command, ' '.join(self.command_arguments)))

			else:
				raise RuntimeError('Bug: unhandled argument: "%s"' % arg)


		if not self.command:
			self._set_command(default_command)

		if self.command == 'help':
			raise BadUsageError()


	def _set_command(self, name:str) -> None:
		self.command = name

		# insert configured default arguments and options
		args = config.get('commands/%s/default_arguments' % self.command, [])
		if args and isinstance(args, list):
			self.command_arguments = args

		opts = config.get('commands/%s/default_options' % self.command, [])
		while isinstance(opts, list) and opts:
			self.eat_option(self.command, opts.pop(0), opts, self.command_options)


	def _add_argument(self, argument:str) -> None:
		self.command_arguments.append(argument)

	def _no_command(self, *a, **kw):
		raise RuntimeError('no command set')

	def resolve_cmd(self, *a, **kw):
		raise RuntimeError('resolve_cmd not set')

	def eat_option(self, *a, **kw):
		raise RuntimeError('eat_option not set')
