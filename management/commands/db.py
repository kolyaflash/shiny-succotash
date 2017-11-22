from ..base import BaseCommand
# from sgateway.core.db import metadata
from alembic.config import Config, CommandLine
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory

from sgateway.app import get_application
from ..base import BaseCommand

"""
IT DOESN'T WORK!

But might be helpful for future.
"""


class Command(BaseCommand):
    def __init__(self):
        app = get_application(debug=True)

        self.alembic_cfg = Config()
        self.alembic_cfg.set_main_option("script_location", "migrations")
        self.alembic_cfg.set_main_option("url", "postgresql://user:pass@postgres:5432/mydb")

        self.alembic_script = ScriptDirectory.from_config(self.alembic_cfg)
        self.alembic_env = EnvironmentContext(self.alembic_cfg, self.alembic_script)

        conn = app.db.get_conn()
        self.metadata = app.db.get_metadata()

        self.alembic_env.configure(connection=conn, target_metadata=self.metadata)
        self.alembic_context = self.alembic_env.get_context()

    def add_arguments(self, parser):
        parser.add_argument('db_command', nargs='?', help='DB manager command')
        parser.add_argument('command_args', nargs='*')

    def execute(self, **options):

        # a = autogenerate.compare_metadata(alembic_context, metadata)

        # with alembic_env.begin_transaction():
        #     alembic_env.run_migrations()


        cmd_name = options['db_command']
        cmd_func = None
        if cmd_name:
            cmd_func = getattr(self, cmd_name, None)

        if cmd_func:
            # Call our func
            a = cmd_func(*options['command_args'])
            if a:
                raise Exception(a)
        else:
            # Call alembic directly
            cl = CommandLine()
            argv = list(options['command_args'])
            if cmd_name:
                argv.insert(0, cmd_name)

            if options.get('unknown'):
                argv.extend(options['unknown'])
            # raise Exception(argv)

            options = cl.parser.parse_args(argv)

            if not hasattr(options, "cmd"):
                # see http://bugs.python.org/issue9253, argparse
                # behavior changed incompatibly in py3.3
                cl.parser.error("too few arguments")
            else:

                a = cl.run_cmd(self.alembic_cfg, options)
                if a:
                    raise Exception(a)
                    # raise Exception(options)

    def check(self, *args):
        return autogenerate.compare_metadata(self.alembic_context, self.metadata)

    def current(self, *args):
        """Get the list of current revisions."""
        return self.alembic_script.get_revisions(self.alembic_context.get_current_heads())

    def revisions(self, *args):
        raise Exception("args", args)
        return
