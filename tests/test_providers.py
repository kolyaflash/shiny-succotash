import pytest

from sgateway.core import gateway_exceptions
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.base.service import BaseService
from sgateway.services.registry import ServiceRegistry
from sgateway.services.request import ServiceRequest


@pytest.mark.asyncio
async def test_provider_selection_basic(gateway_app):
    class ServiceForTest(BaseService):
        __name__ = 'test_service'

    class TestProvider(BaseServiceProvider):
        __name__ = 'test_provider'

    with ServiceRegistry(_as_context=True) as registry:
        registry.register(ServiceForTest)

        service = registry.get_service('test_service', 1)(gateway_app)
        sreq = ServiceRequest(service, None, gateway_app, None)

        with pytest.raises(gateway_exceptions.ProviderUnavailable):
            await service.get_provider(sreq)

    with ServiceRegistry(_as_context=True) as registry:
        ServiceForTest.providers = (TestProvider,)
        registry.register(ServiceForTest)

        service = registry.get_service('test_service', 1)(gateway_app)
        sreq = ServiceRequest(service, None, gateway_app, None)

        provider = await service.get_provider(sreq)
        assert provider.name == 'test_provider'


@pytest.mark.asyncio
async def test_provider_selection_concrete(gateway_app, service_registry):

    class TestProvider1(BaseServiceProvider):
        __name__ = 'test_provider1'

    class TestProvider2(BaseServiceProvider):
        __name__ = 'test_provider2'

    class TestProvider3(BaseServiceProvider):
        __name__ = 'test_provider3'

    @service_registry.register()
    class ServiceForTest(BaseService):
        __name__ = 'test_service'
        providers = (TestProvider1, TestProvider2, TestProvider3)

    service = service_registry.get_service('test_service', 1)(gateway_app)
    sreq = ServiceRequest(service, None, gateway_app, None)

    provider = await service.get_provider(sreq, provider_name='test_provider2')
    assert provider.name == 'test_provider2'

    provider = await service.get_provider(sreq, provider_name='test_provider1')
    assert provider.name == 'test_provider1'
