import asyncio
import json
from decimal import Decimal

from sl_mqlib.serializer import JsonSerializer

from sgateway.core.gateway_exceptions import (
    ServiceBadRequestError, UnauthorizedApiException, ServiceRestricted, ProviderError,
    ServiceUnavailable,
)
from sgateway.core.utils import get_domain_zone, get_schema_models
from sgateway.services.base.strategy import BaseProviderChoiceStrategy
from .models import IntentionTable, DomainsPurchasesTable, RegistrantAccountTable
from .providers import GoDaddyProvider, DomainIsNotAvailableYet
from .schemas import DomainRegistrationClientFormSchema, DNSRecordsSchema
from ..base.service import BaseService
from ..registry import ServiceRegistry
from ..utils import expose_method, webhook_callback

registry = ServiceRegistry()

# Kinda in USD
ZONES_PRICELIST = {
    'com': 0,
}


class DomainRegistrationWorkflow(object):
    def __init__(self, service_request, intention, provider):
        self._intention = intention
        self.provider = provider
        self.service_request = service_request
        self.domain = self._intention['domain']
        self.intention_id = self._intention['id']
        self.entity_id = self._intention['entity_id']

        # Filled during execution
        self.registration_data = None
        self.provider_account = None

    # Exposed execution methods

    async def execute(self):
        await self.step_validate_data()
        await self.step_collect_provider_account()
        await self.step_purchase_domain()
        await self.step_schedule_dns_update()

    async def update_dns(self):
        await self.step_collect_provider_account(no_creation=True)
        await self.step_setup_dns()

    # Internal methods and steps procedures

    @staticmethod
    async def get_registration_schema(provider, domain):
        registration_schema = DomainRegistrationClientFormSchema()
        registration_schema = registration_schema.get_schema()

        extra_props = {}
        if provider.has_method('get_registration_extra_fields'):
            extra_props = await provider.get_registration_extra_fields(domain)

        registration_schema['properties'].update(extra_props)
        registration_schema['required'].extend(extra_props.keys())
        return registration_schema

    async def step_schedule_dns_update(self):
        data = {
            'service': self.service_request.service.name,
            'version': self.service_request.service.version,
            'method': 'update_registered_dns',
            'payload': {
                'intention_id': self.intention_id,
            }
        }
        self.service_request.app.mq_channel.publish(
            'sl.topic',
            data=data,
            routing_key='sgateway.service_call',
            serializer_class=JsonSerializer,
        )

    async def step_validate_data(self):
        schema = await self.get_registration_schema(self.provider, self.domain)
        data = self.service_request.get_data(schema=schema)
        if self.provider.has_method('validate_registration_data'):
            await self.provider.validate_registration_data(
                self.domain, data, client_ip=self.service_request.get_client_ip())

        # We considering that now user input (inside `registration_data`) is all good (because of validation
        # against schema) and if we'll encounter any problems, they going to be related to our implementation or,
        # with a little chance, to registrator API.
        self.registration_data = data

    async def step_collect_provider_account(self, no_creation=False):
        """
        Get provider's account used for managing entity's domains (for this particular provider) or create a new one
        if not exists.
        For GoDaddy, such accounts called SubAccounts.
        """

        entity_id = str(self.entity_id)

        # Try to get existing
        async with self.service_request.app.db.connection() as conn:
            res = await conn.execute(
                RegistrantAccountTable.select()
                    .where((RegistrantAccountTable.c.provider == self.provider.name) &
                           (RegistrantAccountTable.c.entity_id == entity_id))
            )
            provider_account = await res.fetchone()

        # Creating a new account if provider supports it
        if not no_creation and not provider_account and self.provider.has_method('create_client_account'):
            try:
                created_account_data = await self.provider.call_method('create_client_account',
                                                                       self.registration_data,
                                                                       entity_id)
            except ProviderError as e:
                e.message = "Can not create client account on provider"
                raise e

            provider_account = {
                'provider': self.provider.name,
                'entity_id': entity_id,
                'account_data': created_account_data,
                'ip_address': self.service_request.get_client_ip()
            }

            async with self.service_request.app.db.connection() as conn:
                q = RegistrantAccountTable.insert(provider_account).values()
                await conn.execute(q)

        self.provider_account = provider_account

    async def step_purchase_domain(self):
        account_data = self.provider_account['account_data'] if self.provider_account else None
        purchase_result = await self.provider.purchase_domain(
            self.domain, self.registration_data,
            # Can't just use Account's ip, because we need the actual current ip.
            client_ip=self.service_request.get_client_ip(),
            account_data=account_data)

        async with self.service_request.app.db.connection() as conn:
            await conn.execute(
                IntentionTable.update()
                    .where(IntentionTable.c.id == self.intention_id)
                    .values(finished=True, registration_data=self.registration_data)
            )
            await conn.execute(
                DomainsPurchasesTable.insert()
                    .values(intention_id=self.intention_id,
                            provider_purchase_uid=purchase_result.get('uid'),
                            price=purchase_result.get('price'),
                            price_currency=purchase_result.get('currency'))
            )

    async def step_setup_dns(self):
        models = get_schema_models(DNSRecordsSchema)
        new_records = [
            {'type': 'A', 'name': '@', 'data': '127.0.0.1'},
            {'type': 'CNAME', 'name': 'www', 'data': 'some.semilimes.com'},
        ]

        instance = models.DomainDnsRecords()
        instance.records = []
        for rec_dict in new_records:
            instance.records.append(models.DNSRecord(**rec_dict))

        records_data = json.loads(instance.serialize())
        account_data = self.provider_account['account_data'] if self.provider_account else None

        """
        The thing is that provider (i.e. GoDaddy) may don't be available for immediate DNS setup right
        after domain registration. We don't know when it will become available, so we're trying to 
        make several attempts.
        
        If we fail during or after attempts - it's on message queue to repeat the process again.
        """
        attempts = 5
        time_to_sleep = 2
        update_done = False

        while attempts > 0:
            await asyncio.sleep(time_to_sleep)
            try:
                await self.provider.call_method('update_dns_records', self.domain, records_data, account_data)
                update_done = True
                break
            except DomainIsNotAvailableYet:
                attempts -= 1
                time_to_sleep = time_to_sleep * 2
                self.service_request.app.logger.info("DomainIsNotAvailableYet error. {} attemps left".format(attempts))

        if not update_done:
            raise DomainIsNotAvailableYet()

        async with self.service_request.app.db.connection() as conn:
            await conn.execute(
                DomainsPurchasesTable.update()
                    .where(DomainsPurchasesTable.c.intention_id == self.intention_id)
                    .values(post_registration_complete=True)
            )
        self.service_request.app.logger.info("Domain DNS updated successfully (domain: {})".format(self.domain))


class DomainRegistrantStrategy(BaseProviderChoiceStrategy):
    def __init__(self, domain, *args, **kwargs):
        self.domain = domain
        super(DomainRegistrantStrategy, self).__init__(*args, **kwargs)

    async def select(self, service_request, providers):
        providers_price_list = []

        for provider in providers:
            a = await provider.check_availability(self.domain)
            if not a['available']:
                continue

            providers_price_list.append((provider, Decimal(a['price'])))

        if len(providers_price_list) < 1:
            raise ServiceBadRequestError("This domain seems to be unavailable (or invalid). "
                                         "Check availability first or try again later.")

        # sort by price and get first
        providers_price_list.sort(key=lambda x: x[1])
        return providers_price_list[0][0]  # Cheapest


@registry.register()
class DomainService(BaseService):
    __name__ = 'domains'
    __version__ = 1
    __verbose_name__ = 'Domains registration and management'

    providers = (GoDaddyProvider,)

    def get_domain_price(self, domain):
        fixed_price = ZONES_PRICELIST.get(get_domain_zone(domain), None)
        if fixed_price is None:
            # TODO: We can try to dynamically find out a price for valid, but not "fixpriced" zones.
            raise ServiceBadRequestError("Domain zone is not supported")
        return fixed_price

    @expose_method(http_method='GET')
    async def check_availability(self, service_request):
        domain = service_request.get_arg('domain')
        if not domain:
            raise ServiceBadRequestError("domain is required")

        price = self.get_domain_price(domain)

        provider = await self.get_provider(service_request, required_methods=['check_availability'])
        provider_resp = await provider.check_availability(domain)

        return self.result({
            'price': price if provider_resp['available'] else None,
            'available': provider_resp['available'],
        })

    @expose_method(http_method='GET')
    async def create_registration_intention(self, service_request):
        domain = service_request.get_arg('domain')
        try:
            entity_id = await service_request.entity_id
        except AttributeError:
            raise ServiceRestricted("No entity_id")

        if not domain:
            raise ServiceBadRequestError("Domain arg is required")

        provider = await self.get_provider(service_request, strategy=DomainRegistrantStrategy(domain=domain))
        schema = await DomainRegistrationWorkflow.get_registration_schema(provider, domain)

        intention = {
            'domain': domain,
            'entity_id': entity_id,
            'provider': provider.name,
        }

        async with self.app.db.connection() as conn:
            trans = await conn.begin()
            try:
                res = await conn.execute(IntentionTable.insert().values(**intention).returning(IntentionTable.c.id))
                intention_id = await res.scalar()
            except:
                await trans.rollback()
                raise
            else:
                await trans.commit()

        return self.result({
            'intention_id': intention_id,
            'schema': schema,
        }, status_code=201)

    @webhook_callback()
    async def update_registered_dns(self, service_request):
        """
        Method for updating DNS records on provider after domain is purchased.
        :param service_request:
        :return:
        """
        data = service_request.get_data()
        intention_id = data.get('intention_id')

        async with self.app.db.connection() as conn:
            res = await conn.execute(IntentionTable.select().where(IntentionTable.c.id == intention_id))
            intention = await res.fetchone()

        provider = await self.get_provider(service_request, provider_name=intention['provider'])

        workflow = DomainRegistrationWorkflow(service_request, intention, provider)
        try:
            await workflow.update_dns()
        except DomainIsNotAvailableYet:
            raise ServiceUnavailable(client_retry=True)
        return self.result(None)

    @expose_method(http_method='POST')
    async def submit_registration_intention(self, service_request):
        """
        Validates registration data and if all fine then do:
        - creates subaccount for our customer at provider
        - purchase a domain
        - setup DNS
        """
        intention_id = service_request.get_arg('intention_id')
        entity_id = await service_request.entity_id

        if not intention_id:
            raise ServiceBadRequestError("intention_id is required")

        async with self.app.db.connection() as conn:
            res = await conn.execute(IntentionTable.select().where(IntentionTable.c.id == intention_id))
            intention = await res.fetchone()

        if not intention:
            raise ServiceBadRequestError("Intention not found")
        if str(intention['entity_id']) != str(entity_id):
            raise UnauthorizedApiException("%s %s" % (intention['entity_id'], await service_request.entity_id))

        # We never use random provider in this method, but use one that was selected earlier.
        provider = await self.get_provider(service_request, provider_name=intention['provider'])

        if intention['finished']:
            # Intention already processed. For now just do nothing and return ok response.
            registration_happened = False
        else:
            # Do all the steps required for registering domain.
            workflow = DomainRegistrationWorkflow(service_request, intention, provider)
            await workflow.execute()
            registration_happened = True

        return self.result({'domain': intention['domain'], 'registered': True},
                           request_fulfilled=True if registration_happened else False,
                           status_code=201 if registration_happened else 304)
