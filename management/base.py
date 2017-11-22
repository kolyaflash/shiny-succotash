from argparse import ArgumentParser
import os


class BaseCommand(object):
    """Base management command class."""

    # create_parser method is from Django with significant edits.
    def create_parser(self, prog_name, subcommand):
        """Create and return the ``ArgumentParser`` which will be used to parse the arguments to this command.
        :param prog_name: String. Program name.
        :param subcommand: String. subcommand.
        """
        return ArgumentParser(
            prog='{0} {1}'.format(os.path.basename(prog_name), subcommand),
            description=None,
        )

    def add_arguments(self, parser):
        """Override in subclasses to add arguments to the parser."""
        pass

    def execute(self, **options):
        pass

