import aiohttp

from sgateway.core import gateway_exceptions
from sgateway.core.utils import get_schema_models
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.utils import provide_method
from .constants import ALAVARA_MOCK_RESPONSE
from .schemas import SaleTaxResponse


def parse_alavara_tax_rates_response(data):
    models = get_schema_models(SaleTaxResponse)

    resp = models.SaleTaxResponse()
    resp.total_tax = data['totalTax']
    resp.lines = []

    for line in data['lines']:
        line_taxes = []

        for tax in line['details']:
            tax_code_id = u'{country}_{jurisType}_{jurisName}'.format(**tax)

            line_taxes.append(models.SaleLineTaxes(
                rate=tax['rate'], tax_name=tax['taxName'],
                country=tax.get('country', ''),
                region=tax.get('region', ''),
                tax_code_id=tax_code_id,
                tax_type=tax.get('taxType', ''),
                tax_jurisdiction=tax.get('jurisName', ''),
            ))

        resp.lines.append(models.SaleLineTaxResult(
            line_number=int(line['lineNumber']),
            taxes=line_taxes,
        ))
    return resp


def parse_taxjar_tax_rates_response(data):
    models = get_schema_models(SaleTaxResponse)
    resp = models.SaleTaxResponse()
    # return resp
    raise NotImplementedError


class MockedProvider(BaseServiceProvider):
    __name__ = '_mocked_'
    supported_countries = ['US']

    @provide_method()
    def taxes_for_sale(self, sale_data):
        test_data = ALAVARA_MOCK_RESPONSE
        return parse_alavara_tax_rates_response(test_data)


class AvataxProvider(BaseServiceProvider):
    __name__ = 'avatax'
    __verbose_name__ = 'AvaTax by Alavara'
    __maintainer_details__ = """
    https://developer.avalara.com/avatax/

    Real-time tax calculation for financial applications.
    """

    supported_countries = ['US']

    @property
    def aiosession(self):
        # See https://developer.avalara.com/avatax/authentication-in-rest/
        ALAVARA_ACCOUNT_ID = self.require_config('ALAVARA_ACCOUNT_ID')
        ALAVARA_LICENCE_KEY = self.require_config('ALAVARA_LICENCE_KEY')

        return aiohttp.ClientSession(loop=self.app.loop, headers={
            'Accept': 'application/json',
        }, auth=aiohttp.BasicAuth(ALAVARA_ACCOUNT_ID, ALAVARA_LICENCE_KEY))

    def api_url_build(self, resource):
        AVATAX_API_URL = self.require_config("AVATAX_API_URL")
        return "{}/{}".format(AVATAX_API_URL.rstrip("/"), resource.lstrip("/"))

    @provide_method()
    async def taxes_for_sale(self, sale_data):
        """
        It uses `CreateTransaction`:
        https://developer.avalara.com/api-reference/avatax/rest/v2/methods/Transactions/CreateTransaction/

        Always creates type `SalesOrder` (`SaleInvoice` is also available).
        :return:
        """

        def parse_address(addr):
            if not addr:
                return {}
            res = {
                'line1': addr.get('street_line1', ''),
                'line2': addr.get('street_line2', ''),
                'city': addr.get('city', ''),
                'postalCode': addr.get('postal_code', ''),
            }
            if addr.get('country_code'):
                res['country'] = addr['country_code']
            if addr.get('region_code'):
                res['region'] = addr['region_code']
            return res

        data = {
            "type": "SalesOrder",
            "code": sale_data.get('sale_id', ''),
            "customerCode": sale_data['customer_id'],
            "currencyCode": sale_data['currency'],
            "salespersonCode": sale_data.get('salesperson_id', ''),
            "date": sale_data['date'],
            "lines": [
                {
                    "number": x['line_number'],
                    "quantity": x['quantity'],
                    "amount": x['amount_total'],
                    "itemCode": x.get('item_code', ''),
                    "taxCode": x.get('tax_code', ''),
                    "description": x.get('description', ''),
                } for x in sale_data['lines']
            ],
            "addresses": {
                "shipFrom": parse_address(sale_data['ship_from_address']),
                "shipTo": parse_address(sale_data['ship_to_address']),
                "pointOfOrderOrigin": (
                    parse_address(sale_data['ordered_at_address'])
                    if sale_data.get('ordered_at_address') else
                    parse_address(sale_data['ship_from_address'])
                ),
                "pointOfOrderAcceptance": (
                    parse_address(sale_data['acceptence_at_address'])
                    if sale_data.get('acceptence_at_address') else
                    parse_address(sale_data['ship_to_address'])
                ),
            },
        }

        def _build_resp_error(error_data):
            if error.get('target') == 'IncorrectData':
                raise gateway_exceptions.ServiceBadRequestError(error['message'], payload={
                    'error_details': error_data.get('details'),
                })
            else:
                raise gateway_exceptions.ProviderError(error['message'])

        async with self.aiosession as session:
            async with session.post(self.api_url_build('transactions/create'), json=data) as resp:
                resp_data = await resp.json()
                error = resp_data.get('error')
                if error:
                    _build_resp_error(error)
                if 'code' not in resp_data:
                    raise gateway_exceptions.ProviderError("Unknown response from upstream")
        self.log.info("resp_data: {}".format(resp_data))
        return parse_alavara_tax_rates_response(resp_data)


class TaxJarProvider(BaseServiceProvider):
    __name__ = 'taxjar'
    __verbose_name__ = 'TaxJar'
    __maintainer_details__ = """
    https://www.taxjar.com/api/docs/#smart-sales-tax-api-enhanced
    
    The Sales Tax API supports calculating the amount of taxes due given line item amounts, quantities and discounts.     
    """

    supported_countries = []

    @property
    def aiosession(self):
        # See https://developers.taxjar.com/api/reference/#authentication
        TAXJAR_API_TOKEN = self.require_config('TAXJAR_API_TOKEN')

        return aiohttp.ClientSession(loop=self.app.loop, headers={
            'Accept': 'application/json',
            'Authorization': 'Bearer {}'.format(TAXJAR_API_TOKEN),
        })

    def api_url_build(self, resource):
        TAXJAR_API_URL = self.require_config("TAXJAR_API_URL")
        return "{}/{}".format(TAXJAR_API_URL.rstrip("/"), resource.lstrip("/"))

    @provide_method()
    async def taxes_for_sale(self, sale_data):
        data = {
            'amount': sale_data['amount'],
            'shipping': 0,  # TODO ?
            'nexus_addresses': [],  # TODO ?
            'line_items': [],
        }

        def parse_address(dir):
            addr_data = sale_data['ship_{}_address'.format(dir)]
            res = {}
            res['zip'] = addr_data.get('postal_code', '')
            res['country'] = addr_data.get('country_code', '')
            res['state'] = addr_data.get('region_code')
            res['city'] = addr_data.get('city')
            res['street'] = u"{} {}".format(addr_data.get('street_line1', ''),
                                            addr_data.get('street_line2', '')).strip()

            for key in res.keys():
                if res[key]:
                    data['{}_{}'.format(dir, key)] = res[key]

        parse_address('to')
        parse_address('from')

        for line in sale_data['lines']:
            unit_price = line['amount_total'] / line['quantity'] if line.get('amount_total') else None
            line_data = {
                "id": line['line_number'],
                "quantity": line['quantity'],
                "product_tax_code": line.get('tax_code', ''),
            }
            if unit_price:
                line_data['unit_price'] = unit_price
            data['line_items'].append(line_data)

        async with self.aiosession as session:
            async with session.post(self.api_url_build('taxes'), json=data) as resp:
                resp_data = await resp.json()

                if resp_data.get('error') and resp_data.get('status') == 400:
                    raise gateway_exceptions.ServiceBadRequestError(resp_data['detail'])
                elif resp_data.get('error'):
                    raise gateway_exceptions.ProviderError(resp_data.get('detail'))

        return parse_taxjar_tax_rates_response(resp_data)
