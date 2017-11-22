import time
from urllib.parse import urlparse

from aiopg.sa import create_engine
from sqlalchemy import MetaData
from sqlalchemy import create_engine as create_blocking_engine
from sqlalchemy_utils import database_exists, create_database, drop_database

metadata = MetaData()


class GatewayDB(object):
    """
    Simple helper and SQLAlchemy engine holder.
    Can provide tests compatible database.

    TODO: cleanup test database management.
    """

    def __init__(self, app, loop=None):
        self.app = app
        self.loop = loop
        self.db_config = self.app.config.DB_CONFIG
        self.url = self.db_config['connection_string']

        self.tmp_database = None
        if self.db_config.get('create_tmp_db'):
            self.tmp_database = '{}_test_{}'.format(self.app.name, str(time.time()).replace('.', '_'))

    async def create_engine(self, loop=None):

        if self.tmp_database:
            """
            This automatically creates temporary database that will be automatically deleted after server stops.
            """
            self.url = urlparse(self.url)._replace(path='/{}'.format(self.tmp_database)).geturl()
            if not database_exists(self.url):
                create_database(self.url)

            tmp_engine = create_blocking_engine(self.url)
            metadata.create_all(tmp_engine)
            tmp_engine.dispose()

        self.engine = await create_engine(dsn=self.url, loop=loop if loop else self.loop)

    async def stop_engine(self):
        self.engine.close()
        await self.engine.wait_closed()
        if self.tmp_database:
            drop_database(self.url)

        if hasattr(self, '_blocking_connection'):
            self._blocking_connection.close()

    def get_metadata(self):
        return metadata

    def connection(self):
        return self.engine.acquire()

    def blocking_connection(self, **kwargs):
        """
        For some testing/debugging purpose.
        :param kwargs: engine params
        :return: opened connection
        """
        if not hasattr(self, '_connection'):
            self._blocking_connection = create_blocking_engine(self.url, **kwargs).connect()
        return self._blocking_connection
