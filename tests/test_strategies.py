import pytest

from sgateway.core.gateway_exceptions import InternalError, FailoverFailError
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.base.service import BaseService
from sgateway.services.registry import ServiceRegistry
from sgateway.services.request import ServiceRequest
from sgateway.services.strategies import RoundRobinStrategy
from sgateway.services.utils import provide_method


@pytest.mark.asyncio
async def test_roundrobin_strategy(gateway_app, service_registry):
    class TestProvider1(BaseServiceProvider):
        __name__ = 'test_provider1'

    class TestProvider2(BaseServiceProvider):
        __name__ = 'test_provider2'

    @service_registry.register()
    class ServiceForTest(BaseService):
        __name__ = 'test_service'
        provider_strategy = RoundRobinStrategy
        providers = (TestProvider1, TestProvider2)

    service = service_registry.get_service('test_service', 1)(gateway_app)
    sreq = ServiceRequest(service, None, gateway_app, None)
    provider1 = await service.get_provider(sreq)
    provider2 = await service.get_provider(sreq)

    assert isinstance(provider1, TestProvider1)
    assert isinstance(provider2, TestProvider2)

    assert sreq.get_loggable_properties()['provider']


@pytest.mark.asyncio
async def test_roundrobin_strategy_state(gateway_app):
    class TestProvider(BaseServiceProvider):
        __name__ = 'test_provider'

    class ServiceForTest(BaseService):
        __name__ = 'test_service'
        provider_strategy = RoundRobinStrategy
        providers = (TestProvider,)

    with pytest.raises(InternalError, message="Impossible to use *"):
        ServiceForTest.provider_strategy(app=gateway_app, locals=None)

    with ServiceRegistry(_as_context=True) as registry:
        registry.register(ServiceForTest)
        service = registry.get_service('test_service', 1)(gateway_app)
        sreq = ServiceRequest(service, None, gateway_app, None)

        strategy = service._get_strategy()
        assert strategy.calls_storage.get('test_provider') == 0
        strategy.select(sreq, service._get_available_providers())
        assert strategy.calls_storage.get('test_provider') == 1

        # Make sure state is persistent
        service = registry.get_service('test_service', 1)(gateway_app)
        strategy = service._get_strategy()
        assert strategy.calls_storage.get('test_provider') == 1

    # Make sure it's a new state
    with ServiceRegistry(_as_context=True) as registry:
        registry.register(ServiceForTest)
        service = registry.get_service('test_service', 1)(gateway_app)
        strategy = service._get_strategy()
        assert strategy.calls_storage.get('test_provider') == 0


@pytest.mark.asyncio
async def test_failover(gateway_app):
    test_value = {'success': False}

    class TestProvider1(BaseServiceProvider):
        __name__ = 'test_provider1'

        @provide_method()
        def test(self):
            raise NotImplementedError()

    class TestProvider2(BaseServiceProvider):
        __name__ = 'test_provider2'

        @provide_method()
        def test(self):
            raise NotImplementedError()

    class TestProvider3(BaseServiceProvider):
        __name__ = 'test_provider3'

        @provide_method()
        def test(self):
            test_value['success'] = True
            return test_value

    class ServiceForTest(BaseService):
        __name__ = 'test_service'
        providers = (TestProvider1, TestProvider2, TestProvider3)

    with ServiceRegistry(_as_context=True) as registry:
        registry.register(ServiceForTest)
        service = ServiceForTest(gateway_app)
        sreq = ServiceRequest(service, None, gateway_app, None)

        res = await service.failover_provider_call(sreq, 'test', _silent=True)
        assert res['success'] == True
        assert test_value['success'] == True

    class ServiceForTest(BaseService):
        __name__ = 'test_service'
        providers = (TestProvider1, TestProvider2)  # No good provider

    with ServiceRegistry(_as_context=True) as registry:
        registry.register(ServiceForTest)
        service = ServiceForTest(gateway_app)
        sreq = ServiceRequest(service, None, gateway_app, None)

        with pytest.raises(FailoverFailError):
            await service.failover_provider_call(sreq, 'test', _silent=True)
