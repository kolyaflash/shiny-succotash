from decimal import Decimal

import aiohttp

from sgateway.core.gateway_exceptions import ProviderError
from sgateway.core.utils import get_schema_models
from .schemas import RatesSchema
from ..base.provider import BaseServiceProvider
from ..utils import provide_method


class CurrencyExchangeProvider(BaseServiceProvider):
    def __init__(self, *args, **kwargs):
        super(CurrencyExchangeProvider, self).__init__(*args, **kwargs)
        self.models_ns = get_schema_models(RatesSchema)

    def _default_request_headers(self):
        return {}

    @property
    def aiosession(self):
        return aiohttp.ClientSession(loop=self.app.loop, headers=self._default_request_headers())


class MockedProvider(CurrencyExchangeProvider):
    __name__ = '_mocked_'

    @provide_method()
    async def get_rates(self, base, date=None, currencies=None):
        rates = {curr: 1 for curr in currencies}

        rates_schema = self.models_ns.Rates(base=base, datetime=date.isoformat())
        rates_schema.rates = [self.models_ns.Rate(currency=k, value=v) for k, v in rates.items()]
        return rates_schema

    @provide_method()
    async def convert(self, query):
        rates = await self.get_rates(base=query.from_currency, currencies=query.to_currency)
        return {
            rate.currency: Decimal(query.amount * rate.value) for rate in rates.rates
        }


class FixerioProvider(CurrencyExchangeProvider):
    __name__ = 'fixer_io'
    __verbose_name__ = 'Fixer.io'
    __maintainer_details__ = """
    http://fixer.io/
    Fixer.io is a free JSON API for current and historical foreign exchange rates published by the
    European Central Bank.
    
    Foreign exchange rates and currency conversion API
    The rates are updated daily around 4PM CET.
    """

    @provide_method()
    async def get_rates(self, base, date=None, currencies=None):
        # E.g.
        # http://api.fixer.io/2000-01-03
        # http://api.fixer.io/latest?symbols=USD,GBP

        if date:
            date = date.isoformat()
        else:
            date = 'latest'

        url = "http://api.fixer.io/{date}".format(date=date)
        params = {'base': base}
        if currencies:
            params['symbols'] = u','.join(currencies)

        async with self.aiosession as session:

            async with session.get(url, verify_ssl=True, params=params) as resp:
                resp_data = None
                if resp.status != 200:
                    raise ProviderError("Provider error when get '{}': {}".format(url, await resp.text()))
                try:
                    resp_data = await resp.json()
                except:
                    raise ProviderError("Unexpected error [{}]: {}".format(resp.status, await resp.text()))

        rates_schema = self.models_ns.Rates(base=resp_data['base'], datetime=resp_data['date'])
        rates_schema.rates = [self.models_ns.Rate(currency=k, value=v) for k, v in resp_data['rates'].items()]
        return rates_schema

    async def _get_currency_rate(self, from_currency, to_currency):
        """
        Could be cached.
        :return:
        """
        rates_schemed = await self.get_rates(base=from_currency, currencies=[str(x) for x in to_currency])
        try:
            rates = rates_schemed.rates
        except IndexError:
            raise ProviderError("Provider was not able to provide rate for {} -> {}".format(
                from_currency, list(to_currency)))

        return {rate.currency: rate.value for rate in rates}

    @provide_method()
    async def convert(self, query):
        rates = await self._get_currency_rate(query.from_currency, query.to_currency)
        return {
            k: Decimal(query.amount * v) for k, v in rates.items()
        }


class JsonratesProvider(CurrencyExchangeProvider):
    __name__ = 'jsonrates'
    __verbose_name__ = 'jsonrates'
    __maintainer_details__ = """
    http://jsonrates.com/
    Reliable, fast and free JSON API for exchange rates and currency conversion
    """
    api_key = '123'

    @provide_method()
    def get_rates(self, date=None):
        raise ProviderError('Not available now')

    @provide_method()
    def convert(self, from_, to, amount):
        raise ProviderError('Not available now')


class DummyProvider(CurrencyExchangeProvider):
    __name__ = 'dummy'
    __verbose_name__ = 'dummy test'
