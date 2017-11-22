import json

import pytest

from sgateway.core import gateway_exceptions
from sgateway.core.utils import get_schema_models
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.base.service import BaseService
from sgateway.services.email.providers import MockedProvider as EmailMockedProvider
from sgateway.services.email.schemas import EmailMessage
from sgateway.services.email.service import EmailService
from sgateway.services.registry import ServiceRegistry
from sgateway.services.tax_rates.providers import MockedProvider as TaxratesMockedProvider
from sgateway.services.tax_rates.service import TaxRatesService
from sgateway.services.utils import expose_method
from .base import BaseServiceTestCase


def test_registry(gateway_app):
    class TestProvider(BaseServiceProvider):
        __name__ = 'testprovider'

    class TestService1(BaseService):
        __name__ = 'testservice'
        __version__ = 1
        providers = (TestProvider,)

    class TestService2(TestService1):
        __name__ = 'testservice'
        __version__ = 2

        @expose_method()
        def test_method(self):
            return

    with ServiceRegistry(_as_context=True) as registry:
        registry.register(TestService1)
        registry.register(TestService2)

        s1 = registry.get_service('testservice', 1)(gateway_app)
        s2 = registry.get_service('testservice', 2)(gateway_app)
        assert int(s1.version) == 1
        assert int(s2.version) == 2

        assert registry.get_providers(s1.name, s1.version) == [TestProvider]
        assert registry.get_providers(s2.name, s2.version) == [TestProvider]

        prov = registry.get_provider(s1.name, s1.version, 'testprovider')(gateway_app)
        assert isinstance(prov, TestProvider)


def test_request_schema(gateway_app, service_factory, request_factory):
    TEST_SCHEMA = {
        "id": "http://json-schema.org/geo",
        "$schema": "http://json-schema.org/draft-06/schema#",
        "description": "A geographical coordinate",
        "type": "object",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"}
        },
        "required": ["latitude", "longitude"]
    }

    @expose_method(request_schema=TEST_SCHEMA)
    def test_method(self, service_request):
        data = service_request.get_data()
        return self.result(data)

    service = service_factory(methods=[test_method])(gateway_app)

    # Bad data
    with pytest.raises(gateway_exceptions.ServiceBadRequestError, match='.* schema error.*') as exc_info:
        service.call_method('test_method', request_factory(service, 'test_method', data={'bad': 'data'}))
    assert exc_info.value.payload['error_message']

    # Good data

    # POST request
    data = {'latitude': 111, 'longitude': 222.5}
    response = service.call_method('test_method', request_factory(service, 'test_method', data=data))
    assert response.response_data['latitude'] == data['latitude']
    assert response.response_data['longitude'] == data['longitude']

    # GET request
    response = service.call_method('test_method', request_factory(service, 'test_method', args=data))
    assert response.response_data['latitude'] == data['latitude']
    assert response.response_data['longitude'] == data['longitude']


class TestEmail(BaseServiceTestCase):
    service_cls = EmailService
    providers_cls = [EmailMockedProvider]

    @pytest.mark.service_method_test
    async def test_send(self):
        request = self.service_request_factory(data={'bad': 'data'})
        with pytest.raises(gateway_exceptions.ServiceBadRequestError) as exc_info:
            await self.service.call_method(request.method.name, request)

        models = get_schema_models(EmailMessage)
        email = models.EmailMessage()
        email.body_plain_text = 'test'
        email.body_html = 'test <b>bold</b>'
        email.subject = u'привет'
        email.to = [models.Person(email='test@email.com')]
        email.from_email = models.Person(email='test2@email.com')

        request = self.service_request_factory(data=json.loads(email.serialize()))
        resp = await self.service.call_method(request.method.name, request)
        assert resp.response_data['sent']
        assert request.get_loggable_properties()['provider'] == '_mocked_'


class TestTaxRates(BaseServiceTestCase):
    service_cls = TaxRatesService
    providers_cls = [TaxratesMockedProvider]

    @pytest.mark.service_method_test
    @pytest.mark.parametrize(('data', 'expected_resp'), [
        ({'test': 'test'}, 'test'),
        ({'test': 'test2'}, 'test2'),
    ])
    async def test_taxes_for_address(self, data, expected_resp):
        request = self.service_request_factory(data=data)
        r = await self.service.call_method(request.method.name, request)
        assert r == expected_resp

    @pytest.mark.service_method_test
    async def test_taxes_for_sale(self):
        request = self.service_request_factory(data={})
        with pytest.raises(gateway_exceptions.ServiceBadRequestError) as exc_info:
            await self.service.call_method(request.method.name, request)

        req_data = {
            'sale_id': '1',
            'customer_id': '1',
            'date': '1970-01-01',
            'lines': [
                {'line_number': 1, 'quantity': 1, 'amount_total': 100, 'item_code': 'T123'}
            ],
            'currency': 'USD',
            'ship_from_address': {

            },
            'ship_to_address': {

            }
        }
        request = self.service_request_factory(data=req_data)
        r = await self.service.call_method(request.method.name, request)
        assert r.response_data['total_tax'] == 0.0

        assert len(r.response_data['lines']) == len(req_data['lines'])

        tax_line = r.response_data['lines'][0]['taxes'][0]

        assert r.response_data['lines'][0]['line_number'] == req_data['lines'][0]['line_number']
        assert tax_line['rate'] == 0.0
        assert tax_line['tax_name'] == 'FL STATE TAX'
        assert tax_line['tax_code_id'] == 'US_STA_FLORIDA'
        assert tax_line['tax_jurisdiction'] == 'FLORIDA'
        assert tax_line['country'] == 'US'
        assert tax_line['region'] == 'FL'
        assert tax_line['tax_type'] == 'Sales'
