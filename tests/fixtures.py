import sys

import pytest
from pytest_redis import factories

from sgateway.core.base_app import GatewayApp, SGatewayRequest
from sgateway.core.logs import get_config
from sgateway.services.base.middleware import BaseMiddleware
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.base.service import BaseService
from sgateway.services.registry import ServiceRegistry
from sgateway.services.utils import expose_method
from sgateway.services.request import ServiceRequest


"""
Used extensions:

https://github.com/pytest-dev/pytest-mock/ (mocker)
https://github.com/ClearcodeHQ/pytest-redis (redis_proc)
https://github.com/yunstanford/pytest-sanic (test_server, test_client, etc.)
"""

if sys.platform == 'darwin':
    # Installed via brew on MacOS redis
    _rs_kwargs = {'executable': '/usr/local/bin/redis-server'}
else:
    _rs_kwargs = {}

redis_proc = factories.redis_proc(**_rs_kwargs)


@pytest.fixture(scope='function')
def gateway_app(request, redis_proc):
    log_config = get_config(disable_sanic_handlers=True)
    app = GatewayApp('test_app', config_module='sgateway.config.tests', log_config=log_config)
    if request.instance:
        request.instance.gateway_app = gateway_app
    return app


@pytest.yield_fixture()
def app_server(loop, gateway_app, test_server):
    gateway_app._loop = loop
    yield loop.run_until_complete(test_server(gateway_app))


@pytest.fixture
def app_cli(loop, gateway_app, test_client):
    return loop.run_until_complete(test_client(gateway_app))


@pytest.fixture()
async def app_database(gateway_app):
    await gateway_app.db.create_engine()
    try:
        yield gateway_app.db.engine
    finally:
        await gateway_app.db.stop_engine()


@pytest.yield_fixture(scope='function')
def service_registry():

    with ServiceRegistry(_as_context=True) as sr:
        yield sr


@pytest.fixture()
def service_factory(request):
    """
    DRY way to create a simple service class. It's possible to set custom attrs and methods and add to registry.
    :return: factory funcs
    """

    def _factory(name='test', version=1, methods=None, registry=None):
        """
        :param name: service name
        :param version: service version
        :param methods: list that can contain either string (method name to create), func, expose_method func.
        :param registry: if `ServiceRegistry` provided - service auto-registered in it.
        :return: `BaseService` class
        """

        if methods is None:
            methods = ['test']

        class TestProvider(BaseServiceProvider):
            pass

        class TestService(BaseService):
            __name__ = name
            __version__ = version
            __verbose_name__ = 'Test Service'
            providers = (TestProvider,)

        def method_func(self, service_request):
            return self.result({"result": True})

        for _method in methods:
            if callable(_method):
                if not hasattr(_method, '_service_method'):
                    _method = expose_method()(_method)
                setattr(TestService, _method.__name__, _method)
            else:
                setattr(TestService, _method, expose_method(method_name=_method)(method_func))

        if registry:
            registry.register(TestService)

        return TestService

    if request.instance:
        request.instance.service_factory = _factory
    return _factory


@pytest.fixture()
def middleware_factory(request):
    """
    DRY way to create a simple middleware class.
    :return: factory funcs
    """

    def _factory(process_request=None, process_response=None):
        class TestMiddleware(BaseMiddleware):
            pass

        if process_request:
            TestMiddleware.process_request = process_request
        if process_response:
            TestMiddleware.process_response = process_response

        return TestMiddleware

    if request.instance:
        request.instance.middleware_factory = _factory
    return _factory


@pytest.fixture()
def request_factory(request, gateway_app):
    """
    DRY way to create a ServiceRequest object.
    :return: factory funcs
    """

    def _factory(service, method_name, data=None, args=None, app=gateway_app, method=None):
        if method is None:
            method = 'POST' if data else 'GET'

        request = SGatewayRequest('/'.encode(), {}, None, method, None)
        if data:
            request.parsed_json = data
        if args:
            request.parsed_args = args

        return ServiceRequest(service, service.get_method(method_name), app, request)

    if request.instance:
        request.instance.request_factory = _factory
    return _factory
