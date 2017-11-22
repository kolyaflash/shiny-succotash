import uuid

import pytest

from sgateway.core.base_app import SGatewayRequest
from sgateway.core.gateway_exceptions import ServiceInternalError, ServiceBadRequestError, InternalError
from sgateway.middlewares.idempotency_key import IdempotencyKeyMiddleware
from sgateway.services.base.service import BaseService, ServiceMethod
from sgateway.services.request import ServiceRequest, ServiceResponse
from sgateway.services.utils import expose_method, webhook_callback


class ServiceForTest(BaseService):
    __name__ = 'test_service'

    @expose_method()
    def test_method(self, service_request):
        return self.result({'success': True})

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


@pytest.mark.asyncio
async def test_key_idempotency(gateway_app, app_database):
    """
    TODO: rewrite as class test suite
    """
    mw = IdempotencyKeyMiddleware(gateway_app, ttl=999)
    request_with_key = SGatewayRequest('/'.encode(), {'X-Idempotency-Key': str(uuid.uuid4())[:32]}, None, method='GET',
                                       transport=None)
    request_no_key = SGatewayRequest('/'.encode(), {}, None, method='GET', transport=None)

    service = ServiceForTest(gateway_app)
    method = ServiceMethod('test', 'test_method', False, 'GET', None)

    # Request without key specified
    sr = ServiceRequest(service, method, gateway_app, request_no_key)
    res = await mw.process_request(sr)
    with pytest.raises(InternalError):
        sr.require_extension('_idempotency_key')
    assert res is None

    # Request with key specified
    sr = ServiceRequest(service, method, gateway_app, request_with_key)
    res = await mw.process_request(sr)
    assert sr.get_extension('_idempotency_key')
    assert res is None

    # Duplicated parallel requests with the same key
    for _ in range(3):
        sr = ServiceRequest(service, method, gateway_app, request_with_key)
        with pytest.raises(ServiceBadRequestError):
            await mw.process_request(sr)

    # Check if successful request processing didn't change anything
    ok_resp = ServiceResponse({}, request_fulfilled=True)
    await mw.process_response(sr, ok_resp, None)
    sr = ServiceRequest(service, method, gateway_app, request_with_key)
    with pytest.raises(ServiceBadRequestError):
        await mw.process_request(sr)

    # Check TTL
    mw_ttl_0 = IdempotencyKeyMiddleware(gateway_app, ttl=-1)
    sr = ServiceRequest(service, method, gateway_app, request_with_key)
    await mw_ttl_0.process_request(sr)

    # Check if it still works for non-0 ttl
    sr = ServiceRequest(service, method, gateway_app, request_with_key)
    with pytest.raises(ServiceBadRequestError):
        await mw.process_request(sr)

    # Make sure that same (though unfulfilled) request can not drop the lock
    sr = ServiceRequest(service, method, gateway_app, request_with_key)
    with pytest.raises(ServiceBadRequestError):
        await mw.process_request(sr)
    bad_resp = ServiceResponse({}, request_fulfilled=False)
    await mw.process_response(sr, bad_resp, None)
    # just make sure lock still there
    sr = ServiceRequest(service, method, gateway_app, request_with_key)
    with pytest.raises(ServiceBadRequestError):
        await mw.process_request(sr)

    # And now make sure lock is dropped on unfulfilled request
    request_with_key = SGatewayRequest('/'.encode(), {'X-Idempotency-Key': str(uuid.uuid4())[:32]}, None, method='GET',
                                       transport=None)
    sr1 = ServiceRequest(service, method, gateway_app, request_with_key)
    assert not await mw.process_request(sr1)

    sr2 = ServiceRequest(service, method, gateway_app, request_with_key)
    with pytest.raises(ServiceBadRequestError):
        await mw.process_request(sr2)

    bad_resp = ServiceResponse({}, request_fulfilled=False)
    await mw.process_response(sr1, bad_resp, None)

    # and third request works like a charm
    sr3 = ServiceRequest(service, method, gateway_app, request_with_key)
    assert not await mw.process_request(sr3)
