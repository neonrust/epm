from . import config, db

from typing import Callable

class BadUsageError(RuntimeError):
	pass


class context:
	def __init__(self, eo:Callable, rc:Callable):
		self.debug:bool = False

		self._eat_option = eo
		self._resolve_cmd = rc

		self.global_options = {
			'debug': config.get_bool('debug', False),
		}
		self.command:str|None = None
		self.command_options:dict = {}
		self.command_arguments:list = []

		self.default_command_options:dict = {}
		self.default_command_arguments:list = []

		self.handler:Callable = self._no_command
		self.db:dict[str,dict] = {}

	def invoke(self, width:int) -> str|None:
		load_db = getattr(self.handler, 'load_db', True)
		if load_db:
			self.db = db.load()

		if self.debug:
			print('ARGS:', self.command_arguments)
			print('OPTS:', self.command_options)

		if not self.command_arguments and not self.command_options:
			self.command_arguments = [*self.default_command_arguments]
			self.command_options = {**self.default_command_options}

		return self.handler(self, width=width)


	def configure_handler(self, handler_map:dict) -> bool:
		if self.command is not None:
			self.handler = handler_map[self.command]['handler']
			return True

		return False


	def parse_args(self, args:list, default=False) -> None:

		default_command = str(config.get('commands/default', 'unseen'))

		command_options = self.command_options
		if default:
			command_options = self.default_command_options
		command_arguments = self.command_arguments
		if default:
			command_arguments =self.default_command_arguments

		while args:
			arg = args.pop(0)

			if self.debug:
				print('check arg: "%s"' % arg)

			if arg.startswith('-'):
				if not self.command:
					if arg in '--help':
						raise BadUsageError()

					# attempt to interpret as a global option
					if self.debug:
						print('  try global opt: "%s"' % arg)
					if self._eat_option(None, arg, args, self.global_options, unknown_ok=True):
						if self.debug:
							print('  -> global opt:', arg)
						continue

					self.set_command(default_command)
					if self.debug:
						print('  -> cmd: %s (default)' % self.command)

				if self.debug:
					print('  opt:', arg, '(cmd: %s)' % self.command)

				self._eat_option(self.command, arg, args, command_options)  # will exit if not correct
				continue

			if not self.command and not arg.startswith('.'):
				if self.debug:
					print('  try cmd: "%s"' % arg)
				cmd = self._resolve_cmd(arg)
				if cmd:
					self.set_command(cmd)
					if self.debug:
						print('  -> cmd = %s' % self.command)
					continue

			if not self.command:
				if arg.startswith('.'):
					arg = arg[1: ]

				self.set_command(default_command)
				if self.debug:
					print('  -> cmd = %s (default)' % self.command)

			if self.command:
				command_arguments.append(arg)
				if self.debug:
					print('  -> "%s" [%s]' % (self.command, ' '.join(command_arguments)))

			else:
				raise RuntimeError('Bug: unhandled argument: "%s"' % arg)


		if not self.command:
			self.set_command(default_command)

		if self.command == 'help':
			raise BadUsageError()


	def set_command(self, name:str, apply_args:bool=True) -> None:
		self.command = name

		if apply_args:
			# insert configured arguments
			args = config.get('commands/%s/arguments' % self.command, [])
			# arguments added here will be ignored if arguments were specified on the command-line
			self.parse_args(args, default=True)


	def _no_command(self, *a, **kw):
		raise RuntimeError('no command set')

	def __str__(self) -> str:
		return '[CTX "%s" %s %s]' % (self.command, self.command_options, self.command_arguments)