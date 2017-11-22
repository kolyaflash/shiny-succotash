from sgateway.core.base_app import SGatewayRequest
from sgateway.core.gateway_exceptions import ServiceInternalError
from sgateway.services.base.middleware import BaseMiddleware
from sgateway.services.base.service import BaseService
from sgateway.services.utils import expose_method, webhook_callback
from sgateway.services.views import ServicesBlueprint, create_blueprint

TEST_SCHEMA = {
    "id": "http://json-schema.org/geo",
    "$schema": "http://json-schema.org/draft-06/schema#",
    "description": "A geographical coordinate",
    "type": "object",
    "properties": {
        "latitude": {"type": "number"},
        "longitude": {"type": "number"}
    }
}


def test_blueprint(gateway_app):
    bp = ServicesBlueprint('test_bp')
    gateway_app.blueprint(bp)


def test_middlewares(gateway_app):
    is_registered = {
        'value': False
    }

    class TestMiddleware(BaseMiddleware):
        def on_registered(self):
            is_registered['value'] = True

    bp = ServicesBlueprint('test_bp', middleware_classes=[TestMiddleware])
    gateway_app.blueprint(bp)
    assert is_registered['value']


def test_services(gateway_app, mocker, service_registry):
    class TestService(BaseService):
        __name__ = 'test'

        @expose_method(method_name='testtest')
        def test_method(self):
            return

    service_registry.register(TestService)

    bp = ServicesBlueprint('test_bp', '/services', service_registry=service_registry)
    gateway_app.blueprint(bp, )

    assert ['/services/test/v1/testtest'] == list(gateway_app.router.routes_all.keys())


async def test_service_call(gateway_app, app_cli, service_registry):
    class TestService(BaseService):
        __name__ = 'test_service'

        @expose_method()
        def test_method(self, service_request):
            return self.result({'success': service_request.get_extension('success_value')})

        @expose_method()
        def test_error_method(self, service_request):
            raise ServiceInternalError("test error")

        @webhook_callback()
        def test_webhook(self, service_request):
            assert service_request.get_extension('success_value') is None
            return self.result({'success': True})

        @expose_method()
        def test_stream_method(self, service_request):
            def gen_func():
                yield service_request.get_extension('success_value')

            return self.stream_response(gen_func(), content_type='text/plain')

    service_registry.register(TestService)

    success_value = 'test ok'
    another_val = 'works'

    class TestMiddleware(BaseMiddleware):
        def process_request(self, service_request):
            assert service_request.app == gateway_app
            assert isinstance(service_request.request, SGatewayRequest)
            service_request.add_extension('success_value', success_value)

        def process_response(self, service_request, service_response, gateway_error):
            if service_response and service_response.response_data:
                service_response.response_data['another_val'] = another_val

    bp = ServicesBlueprint('test_bp', '/services', service_registry=service_registry, middleware_classes=[
        TestMiddleware])
    gateway_app.blueprint(bp)

    # Method request
    url = gateway_app.url_for('test_bp.test_service_v1_test_method')
    response = await app_cli.get(url)
    assert response.status == 200
    resp = await response.json()
    assert resp['success'] == success_value
    assert resp['another_val'] == another_val

    # Method error request
    url = gateway_app.url_for('test_bp.test_service_v1_test_error_method')
    response = await app_cli.get(url)
    assert response.status == ServiceInternalError.status_code
    resp = await response.json()
    assert resp['description'] == ServiceInternalError.description
    assert resp['error_code'] == ServiceInternalError.error_code
    assert resp['error_name'] == 'ServiceInternalError'
    assert resp['message'] == 'test error'

    # Webhook request
    url = gateway_app.url_for('test_bp.test_service_v1_test_webhook')
    response = await app_cli.get(url)
    assert response.status == 200
    resp = await response.json()
    assert resp['success'] == True
    assert 'another_val' not in resp

    # Stream response request
    url = gateway_app.url_for('test_bp.test_service_v1_test_stream_method')
    response = await app_cli.get(url)
    assert response.status == 200
    assert response.content_type == 'text/plain'
    assert await response.text() == success_value


async def test_services_schema(gateway_app, app_cli, service_registry, service_factory):
    @expose_method(method_name='test1', http_method='GET')
    def test_method1():
        return

    @expose_method(method_name='test2', http_method='POST', request_schema=TEST_SCHEMA)
    def test_method2():
        return

    services_blueprint = create_blueprint(service_registry=service_registry)
    service = service_factory(registry=service_registry, methods=[test_method1, test_method2])(gateway_app)
    gateway_app.blueprint(services_blueprint)

    resp = await app_cli.get(gateway_app.url_for('services.services_schema'))
    _schemas = await resp.json()
    schema = _schemas[0]
    assert schema['name'] == service.name
    assert schema['version'] == service.version
    assert schema['verbose_name'] == service.__verbose_name__
    assert set(schema['methods'].keys()) == {'test1', 'test2'}

    assert schema['methods']['test1']['http_method'] == 'GET'
    assert schema['methods']['test1']['request_schema'] == {}

    assert schema['methods']['test2']['http_method'] == 'POST'
    assert schema['methods']['test2']['request_schema'] == TEST_SCHEMA

    # Schema of single service
    resp = await app_cli.get(gateway_app.url_for('services.service_schema',
                                                 service_name=service.name, service_version=service.version))
    data = await resp.json()
    assert data['name'] == service.name

    assert schema['methods']['test1']['http_method'] == 'GET'
    assert schema['methods']['test1']['request_schema'] == {}

    assert schema['methods']['test2']['http_method'] == 'POST'
    assert schema['methods']['test2']['request_schema'] == TEST_SCHEMA
