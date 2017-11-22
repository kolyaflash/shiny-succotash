from sgateway.services import BaseService, expose_method
from sgateway.services.base.strategy import BaseProviderChoiceStrategy
from .providers import AvataxProvider, TaxJarProvider
from .schemas import SaleTaxQuery
from ..registry import ServiceRegistry

registry = ServiceRegistry()


class DomesticSaleStrategy(BaseProviderChoiceStrategy):
    """
    Just a PROTOTYPE. Expect providers to have `supported_countries` attributes, so only country-specific
    providers can be selected.
    """

    def __init__(self, country, *args, **kwargs):
        self.country = country
        super(DomesticSaleStrategy, self).__init__(*args, **kwargs)

    async def select(self, service_request, providers):
        suitable_providers = []
        for provider in providers:
            if not self.country in getattr(provider, 'supported_countries', []):
                continue
            suitable_providers.append(provider)
        return suitable_providers[0]


@registry.register
class TaxRatesService(BaseService):
    __name__ = 'tax_rates'
    __verbose_name__ = 'Sales tax rates (for a specified address and other)'

    providers = (
        AvataxProvider,
        TaxJarProvider,
    )

    @expose_method(request_schema=SaleTaxQuery.get_schema(), http_method='POST')
    async def taxes_for_sale(self, service_request):
        query_data = service_request.get_data()
        provider = await self.get_provider(service_request, required_methods=['taxes_for_sale'],
                                           strategy=DomesticSaleStrategy('US'))

        resp = await provider.call_method('taxes_for_sale', query_data)
        resp_data = resp.for_json()
        return self.result(resp_data)

    @expose_method(http_method='POST')
    async def taxes_for_address(self, service_request):
        data = service_request.get_data()
        return data['test']
