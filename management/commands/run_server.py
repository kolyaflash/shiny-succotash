from sgateway.app import get_application
from ..base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--host', help='Server host')
        parser.add_argument('--port', help='Server port')
        parser.add_argument('--debug', help='Debug Mode', default='true')
        parser.add_argument('--workers', help='Workers')

    def execute(self, **options):
        app = get_application()
        host = options['host'] if options['host'] else '0.0.0.0'
        port = options['port'] if options['port'] else 8000
        debug = (options['debug'].lower() == 'true') if options['debug'] else True
        app.run(host=host, port=port, debug=debug)
