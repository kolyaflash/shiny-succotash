import pytest
from sanic.exceptions import SanicException

from sgateway.app import get_application


def test_gateway_app():
    with pytest.raises(AssertionError, match=r'.* APP_CONFIG_MODULE .*'):
        get_application()

    app = get_application(config_module='sgateway.config.tests')
    assert not app.debug
    assert app.config['IS_TEST']

    with pytest.raises(SanicException, match=r'.* can only be retrieved after the app has started .*'):
        print(app.loop)

    assert app.router.routes_all


def test_gateway_app_running(gateway_app, app_server):
    assert gateway_app.loop
    assert gateway_app.redis_pool
    assert gateway_app.db


def test_wsgi_app(monkeypatch):
    monkeypatch.setenv('APP_CONFIG_MODULE', 'sgateway.config.tests')

    from wsgi import app
    assert not app.debug
    assert app.config.IS_TEST
