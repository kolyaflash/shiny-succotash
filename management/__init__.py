import os
import sys
from importlib import import_module

from sgateway.core.core_exceptions import ImproperlyConfigured
from .base import BaseCommand


def discover():
    """Discover management commands in the application.
    :return: List of commands to run.
    """
    commands = {}
    path = sys.modules[__name__].__file__
    package, _, file_name = path.rpartition('/')
    commands_path = '%s/commands' % package
    for filename in os.listdir(commands_path):
        if filename[0] != '_':
            command_name = os.path.splitext(filename)[0]
            mod_path = 'management.commands.%s' % command_name
            mod = import_module(mod_path)

            try:
                command_cls = getattr(mod, 'Command')
            except AttributeError:
                raise

            if not issubclass(command_cls, BaseCommand):
                raise ImproperlyConfigured(
                    "'%s' is not a subclass of BaseCommand." % command_cls)

            commands[command_name] = mod_path

    return commands


def execute_from_command_line():
    commands = discover()
    args = sys.argv[:]
    try:
        command = args[1]
        command = command.replace('-', '_')
    except IndexError:
        # No argument? Display help.
        command = 'help'
    if not command in commands:
        command = 'help'
    if command == 'help':
        args = args[:2]
    execute_command(commands[command], args)


def import_command_class(command_path):
    mod = import_module(command_path)
    return mod.Command()


def execute_command(command_path, args):
    command_class = import_command_class(command_path)
    parser = command_class.create_parser(args[0], args[1] if len(args) > 1 else None)
    command_class.add_arguments(parser)
    if len(args) > 2:
        args = args[2:]
    else:
        args = []
    # Run with command line arguments
    known, unknown = parser.parse_known_args(args)
    known = vars(known)
    known['unknown'] = unknown
    command_class.execute(**known)
