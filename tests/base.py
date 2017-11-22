import pytest

from sgateway.services.registry import ServiceRegistry


@pytest.mark.usefixtures('gateway_app', 'service_registry', 'request_factory')
class BaseServiceTestCase(object):
    def setup(self):
        class TestService(self.service_cls):
            providers = self.providers_cls

        with ServiceRegistry(_as_context=True) as registry:
            self.registry = registry

        self.service_cls = TestService
        self.service = TestService(self.gateway_app)
        self.registry.register(self.service)

        def _factory(**kwargs):
            return self.request_factory(self.service, self._test_service_method_name, **kwargs)

        self.service_request_factory = _factory

    def setup_method(self, method):
        if getattr(method, 'service_method_test', None):
            self._test_service_method_name = method.__name__.replace('test_', '')
