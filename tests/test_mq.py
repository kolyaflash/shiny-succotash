import pytest
from pika.spec import BasicProperties, Basic
from sl_mqlib.channel import Message

from sgateway.core import gateway_exceptions
from sgateway.core.mq import GatewayMQHandler, GatewayMQRequest, AbandonMessage, MessageRequireRequeue
from sgateway.services.request import ServiceRequest


def get_mq_message(data):
    return Message(BasicProperties(), data, Basic.Deliver(routing_key='test.test'))


@pytest.mark.asyncio
async def test_msg_parse(gateway_app, service_registry, service_factory):
    handler = GatewayMQHandler(gateway_app, registry=service_registry)

    msg = get_mq_message({"bad": "data"})
    with pytest.raises(gateway_exceptions.ServiceBadRequestError):
        handler.build_service_request(msg)

    msg = get_mq_message({"service": "test", "but_no": "method name"})
    with pytest.raises(gateway_exceptions.ServiceBadRequestError):
        handler.build_service_request(msg)

    msg = get_mq_message({"service": "test", "method": "test"})
    with pytest.raises(gateway_exceptions.ServiceUnavailable):
        handler.build_service_request(msg)

    service_factory(registry=service_registry)

    msg = get_mq_message({"service": "test", "method": "test"})
    res = handler.build_service_request(msg)
    assert isinstance(res, ServiceRequest)
    assert isinstance(res.request, GatewayMQRequest)

    msg = get_mq_message({"service": "test", "method": "test222"})
    with pytest.raises(gateway_exceptions.ServiceUnavailable):
        handler.build_service_request(msg)


@pytest.mark.asyncio
async def test_msg_handling(gateway_app, service_registry, service_factory, middleware_factory):
    def process_response(self, request, response, error):
        if response:
            response.response_data['middleware_run'] = True

    mw = middleware_factory(process_response=process_response)(gateway_app)
    handler = GatewayMQHandler(gateway_app, registry=service_registry,
                               middlewares=[mw])
    results_ = []

    def some_method(self, service_request):
        res = {'echo': service_request.get_data()['echo'][::-1]}
        results_.append(res)
        return self.result(res)

    def some_error_method(self, service_request):
        raise NotImplementedError

    def api_error_method(self, service_request):
        raise gateway_exceptions.ServiceBadRequestError(client_retry=True)

    service_factory(methods=[some_method, some_error_method, api_error_method], registry=service_registry)

    # OK call
    msg = get_mq_message({"service": "test", "method": "some_method", "payload": {"echo": "hello"}})
    assert await handler.handle(msg) is None
    assert results_[0]['echo'] == 'olleh'
    assert 'middleware_run' in results_[0]

    # Error calls
    msg = get_mq_message({"service": "test", "method": "some_error_method"})
    with pytest.raises(AbandonMessage):
        assert await handler.handle(msg) is None

    msg = get_mq_message({"service": "test", "method": "api_error_method"})
    with pytest.raises(MessageRequireRequeue):
        assert await handler.handle(msg) is None
