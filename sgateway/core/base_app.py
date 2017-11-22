import configparser
import importlib
import os

import aioredis
from sanic import Sanic
from sanic import response as http_response
from sanic.handlers import ErrorHandler
from sanic.request import Request
from sl_mqlib.async import AsyncioUniversalChannel

from sgateway.core.db import GatewayDB
from sgateway.core.gateway_exceptions import BaseApiException, InternalError
from sgateway.core.logs import app_logger
from sgateway.core.logs import get_config as get_logging_config
from sgateway.core.mq import GatewayMQHandler


class SGatewayRequest(Request):
    pass


class GatewayErrorHandler(ErrorHandler):
    def response(self, request, exception):
        """Returns detailed json response for API-related errors.

        :param request: Request
        :param exception: Exception to handle
        :return: Response object
        """
        if (request and not request.app.debug) and not isinstance(exception, BaseApiException):
            # Show html-formatted stacktrace only in debug mode.
            exception = InternalError(payload={
                'error_details': str(exception),
            })

        if isinstance(exception, BaseApiException):
            headers = {
                'X-Error-Code': exception.error_code,
            }
            return http_response.json(exception.to_dict(), status=exception.status_code, headers=headers)

        return super(GatewayErrorHandler, self).response(request, exception)


class GatewayApp(Sanic):
    """
    Sanic app class, overrired and extended. Contains all custom stuff that could be done on the app level.
    """
    default_request_class = SGatewayRequest
    # Available configs:
    # sgateway.config.local
    # sgateway.config.tests
    # sgateway.config.dev
    # sgateway.config.stage
    # sgateway.config.prod
    default_config_module = lambda self: os.environ.get('APP_CONFIG_MODULE')
    logger = app_logger

    def __init__(self, *args, loop=None, **kwargs):
        self._loop = loop
        self.debug = kwargs.pop('debug', None)

        config_module = kwargs.pop('config_module', None)
        if config_module is None:
            config_module = self.default_config_module() if callable(
                self.default_config_module) else self.default_config_module

        kwargs.setdefault('request_class', self.default_request_class)
        kwargs.setdefault('error_handler', GatewayErrorHandler())
        kwargs.setdefault('log_config', get_logging_config('DEBUG' if self.debug else 'INFO'))
        super(GatewayApp, self).__init__(*args, **kwargs)

        self.load_config(config_module)
        self.logger.setLevel(self.config['APP_LOG_LEVEL'])
        self.db = self._init_db()

        self.redis_pool = None
        self._init_redis()

        self.mq_channel = self._init_message_queue()

    @property
    def loop(self):
        """
        Make it possible to set custom ioloop.
        :return:
        """
        if self._loop:
            return self._loop
        return super(GatewayApp, self).loop

    def load_config(self, config_module):
        assert config_module, "No config module specified. Use APP_CONFIG_MODULE env."

        # Load config vars from py files
        mod = importlib.import_module(config_module)
        for setting in dir(mod):
            if setting.isupper():
                setting_value = getattr(mod, setting)
                self.config.update({setting: setting_value})

        """
        Load config vars (credentials) from cfg files.
        Those files originally stored encrypted and ones must decrypt them first before parse.
        TODO: It's not that safe to store decrypted credentials on disk as to put them in memory instead.
        """
        if self.config.CREDENTIALS_DIR_PATH:
            config_module_name = config_module.split('.')[-1]
            self.credentials_file_path = self.config.CREDENTIALS_DIR_PATH.joinpath('{}.cfg'.format(config_module_name))

            cp = configparser.ConfigParser()
            cp.read(self.credentials_file_path)
            try:
                credentials_config = cp[config_module_name]
            except KeyError:
                self.logger.error("Credentials config can not be loaded. Check file exists and is valid: {}".format(
                    self.credentials_file_path
                ))
            else:
                self.config.update({k.upper(): v for k, v in credentials_config.items()})

    def _init_db(self):
        db = GatewayDB(self)

        @self.listener('before_server_start')
        async def _tearup_db(app, loop):
            await db.create_engine(loop)

        @self.listener('before_server_stop')
        async def _teardown_db(app, loop):
            await db.stop_engine()

        return db

    def _init_redis(self):
        @self.listener('before_server_start')
        async def _create_redis(app, loop):
            self.redis_pool = await aioredis.create_pool(
                (app.config['REDIS_CONFIG']['HOST'], app.config['REDIS_CONFIG']['PORT']),
                db=int(app.config['REDIS_CONFIG'].get('DB', 0)),
                minsize=2, maxsize=10,
                loop=loop)

        @self.listener('before_server_stop')
        async def _teardown_redis(app, loop):
            # graceful shutdown
            self.redis_pool.close()
            await self.redis_pool.wait_closed()

    def _init_message_queue(self):
        AMQP_URL = self.config.get('AMQP_URL')
        if not AMQP_URL:
            self.logger.warning("Semilimes Message Queue is not set up. Add AMQP_URL to config to use it.")
            return

        mq_channel = AsyncioUniversalChannel(amqp_url=AMQP_URL)
        GatewayMQHandler(self, mq_channel)

        @self.listener('after_server_start')
        async def _tearup_channel(app, loop):
            mq_channel.set_loop(loop)
            connected = await mq_channel.connect(fail_silently=True)
            if not connected:
                raise NotImplementedError('Ignore this later')

        @self.listener('after_server_stop')
        async def _teardown_channel(app, loop):
            if mq_channel.connected():
                await mq_channel.wait_closed()

        return mq_channel


class AdminApp(Sanic):
    pass
