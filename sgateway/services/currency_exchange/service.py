from decimal import Decimal

import dateutil.parser

from sgateway.core.core_exceptions import ValidationError
from sgateway.core.gateway_exceptions import ServiceBadRequestError
from sgateway.core.utils import get_schema_models
from .providers import FixerioProvider, DummyProvider
from .schemas import ConvertQuerySchema
from ..base.service import BaseService
from ..registry import ServiceRegistry
from ..strategies import RoundRobinStrategy
from ..utils import expose_method

registry = ServiceRegistry()


@registry.register()
class CurrencyExchangeService(BaseService):
    __name__ = 'currency_exchange'
    __version__ = 1
    __verbose_name__ = 'Currency Exchange service'

    providers = (FixerioProvider, DummyProvider)
    provider_strategy = RoundRobinStrategy

    @expose_method(http_method='GET')
    async def rates(self, service_request):
        prov = await self.get_provider(service_request, required_methods=['get_rates'])

        date = service_request.get_arg('date')
        if date is not None:
            try:
                date = dateutil.parser.parse(date).date()
            except ValueError:
                raise ServiceBadRequestError("`date` is incorrect")

        currencies = [x.strip() for x in service_request.get_arg('currencies', '').split(',')]
        base = service_request.get_arg('base', 'USD')
        res = await prov.call_method('get_rates', base, date=date, currencies=currencies)

        return self.result(res.as_dict(), global_cache=True)

    @expose_method(http_method='GET')
    async def convert(self, service_request):

        try:
            amount = Decimal(service_request.get_arg('amount'))
        except (TypeError, ValueError):
            raise ServiceBadRequestError("`amount` must be a valid number")

        ns = get_schema_models(ConvertQuerySchema)
        try:
            query = ns.ConvertQuery(to_currency=service_request.get_arg('to', '').split(','),
                                    from_currency=service_request.get_arg('from'),
                                    amount=float(amount))
        except ValidationError as e:
            raise ServiceBadRequestError(str(e))

        prov = await self.get_provider(service_request, required_methods=['convert'])
        return self.result(await prov.convert(query), global_cache=True)
