import datetime
from abc import ABCMeta
from collections import defaultdict

import aiohttp

from sgateway.core.gateway_exceptions import BaseApiException, ProviderError, ServiceInternalError
from sgateway.core.utils import get_domain_zone
from ..base.provider import BaseServiceProvider
from ..utils import provide_method


class DomainIsNotAvailableYet(BaseApiException):
    pass


class DomainsProvider(BaseServiceProvider, metaclass=ABCMeta):
    def __init__(self, *args, **kwargs):
        super(DomainsProvider, self).__init__(*args, **kwargs)
        self.CLIENT_ACCOUNT_PASSWORD = self.require_config('DOMAINS_CLIENT_ACCOUNT_PASSWORD')
        self.SEMILIMES_CONTACT = self.require_config('SEMILIMES_CONTACT')


class NamecheapProvider(DomainsProvider):
    __name__ = 'namecheap'
    __verbose_name__ = 'Namecheap'
    __maintainer_details__ = """
    Cool API with all the features.
    """


class GoDaddyProvider(DomainsProvider):
    __name__ = 'godaddy'
    __verbose_name__ = 'GoDaddy'
    __maintainer_details__ = """
    Cool API with all the features.
    
    https://developer.godaddy.com/doc#!/_v1_domains/available
    """

    def api_url_build(self, resource):
        GODADDY_API_URL = self.require_config("GODADDY_API_URL")
        return "{}/{}".format(GODADDY_API_URL.rstrip("/"), resource.lstrip("/"))

    @property
    def aiosession(self):
        GODADDY_KEY = self.require_config('GODADDY_KEY')
        GODADDY_SECRET = self.require_config('GODADDY_SECRET')

        return aiohttp.ClientSession(loop=self.app.loop, headers={
            'Authorization': 'sso-key {API_KEY}:{API_SECRET}'.format(API_KEY=GODADDY_KEY, API_SECRET=GODADDY_SECRET),
        })

    @provide_method()
    async def check_availability(self, domain):
        """
        https://developer.godaddy.com/doc#!/_v1_domains/available

        :param domain:
        :return: {domain, available, price)
        """

        data = None
        async with self.aiosession as session:
            async with session.get(self.api_url_build('domains/available'),
                                   params={'domain': domain, 'checkType': 'full'}) as resp:
                if not resp.status == 200:
                    self.log.error("Bad Provider's API response: {}".format(await resp.text()))
                    raise ProviderError("Bad Provider's API response")
                data = await resp.json()
        if not data['period'] == 1:
            # TODO: what to do in this sutiation?
            raise ServiceInternalError("Domain price provided is not per-year based.")
        return {
            'available': data['available'],
            'price': data['price'],
            'currency': data['currency'],
        }

    @provide_method()
    async def get_registration_extra_fields(self, domain):
        params = {
            'tlds': get_domain_zone(domain),
            'privacy': 0,
        }
        agreements_list = []

        async with self.aiosession as session:
            async with session.get(self.api_url_build('domains/agreements'), params=params) as resp:
                resp_data = await resp.json()
                if resp.status != 200:
                    raise ProviderError(resp_data['message'])
                agreements_list = resp_data

        extra_fields = {}
        if agreements_list:
            extra_fields['agreed_agreements'] = {
                "type": "array",
                "description": "",
                "items": {
                    "type": "string",
                    "enum": [x['agreementKey'] for x in agreements_list],
                }
            }

        return extra_fields

    def _adopt_purchase_data(self, domain, data, client_ip):
        dt = datetime.datetime.utcnow().isoformat() + 'Z'

        default_values = {
            'domain': domain,
            'renewAuto': False,
            'privacy': False,
            'nameServers': [],
            'period': 1,
            'consent': {
                'agreementKeys': data['agreed_agreements'],
                'agreedBy': client_ip or '',
                'agreedAt': dt,
            }
        }

        def format_phone(inp):
            if type(inp) != dict:
                return inp if inp else ''
            return "{}.{}".format(inp['country_code'], inp['global_number'])

        def format_contact(inp):
            return {
                "nameFirst": inp['first_name'],
                "nameMiddle": inp.get('middle_name', ''),
                "nameLast": inp['last_name'],
                "organization": inp.get('organization', ''),
                "jobTitle": inp.get('job_title', ''),
                "email": inp['email'],
                "phone": format_phone(inp.get('phone')),  # /^\\+([0-9]){1,3}\\.([0-9]\\ ?){6,14}$/
                "fax": format_phone(inp.get('fax')),  # /^\\+([0-9]){1,3}\\.([0-9]\\ ?){6,14}$/
                "addressMailing": {
                    "address1": inp['mailing_address']['address1'],
                    "address2": inp['mailing_address'].get('address2', ''),
                    "city": inp['mailing_address']['city'],
                    "state": inp['mailing_address']['state'],
                    "postalCode": inp['mailing_address']['postal_code'],
                    "country": inp['mailing_address']['country'],
                }
            }

        adopted_data = {}
        adopted_data.update(default_values)
        adopted_data.update({
            'contactRegistrant': format_contact(data['registrant_contact']),
            'contactAdmin': format_contact(data['registrant_contact']),
            'contactTech': format_contact(self.SEMILIMES_CONTACT),
            'contactBilling': format_contact(self.SEMILIMES_CONTACT),
        })
        return adopted_data

    @provide_method()
    async def validate_registration_data(self, domain, data, client_ip=None):
        purchase_data = self._adopt_purchase_data(domain, data, client_ip)

        async with self.aiosession as session:
            async with session.post(self.api_url_build('domains/purchase/validate'), json=purchase_data) as resp:
                if not resp.status == 200:
                    self.log.error("Bad Provider's API response: {}".format(await resp.text()))
                    raise ProviderError("Bad Provider's API response")
        return True

    @provide_method()
    async def create_client_account(self, purchase_data, client_id):
        """
        Creates GoDaddy subaccount:
        https://developer.godaddy.com/doc#!/_v1_shoppers/Shopper_createSubaccount
        """
        try:
            client_id = int(client_id)
        except (TypeError, ValueError):
            raise ServiceInternalError("GoDaddy require client_id to be int")

        registrant_contact = purchase_data['registrant_contact']
        subaccount_data = {
            "email": registrant_contact['email'],
            "password": self.CLIENT_ACCOUNT_PASSWORD,
            "nameFirst": registrant_contact['first_name'],
            "nameLast": registrant_contact['last_name'],
            "externalId": client_id,
            "marketId": "en-US"
        }

        async with self.aiosession as session:
            async with session.post(self.api_url_build('shoppers/subaccount'), json=subaccount_data) as resp:
                if not resp.status == 200:
                    raise ProviderError(payload={'response_body': await resp.text()})
                return await resp.json()

    @provide_method()
    async def purchase_domain(self, domain, purchase_data, account_data, client_ip):
        if not account_data:
            raise ServiceInternalError("GoDaddy subaccount data is required")

        purchase_data = self._adopt_purchase_data(domain, purchase_data, client_ip)
        shopper_id = account_data['shopperId']
        resp_data = None

        async with self.aiosession as session:
            async with session.post(self.api_url_build('domains/purchase'), headers={
                'X-Shopper-Id': shopper_id,
            }, json=purchase_data) as resp:
                if not resp.status == 200:
                    try:
                        error_data = await resp.json()
                    except:
                        self.log.error("Unknown registration API response: {}".format(await resp.text()))
                        raise ProviderError("Bad Provider's API response")
                    raise ProviderError(error_data['message'])
                resp_data = await resp.json()

        return {
            'uid': resp_data['orderId'],
            'price': resp_data['total'],
            'currency': resp_data['currency'],
        }

    @provide_method()
    async def update_dns_records(self, domain, schemed_data, account_data=None):
        headers = {
            'X-Shopper-Id': account_data.get('shopperId') if account_data else '',
        }

        """
        With GoDaddy we can't just replace all records with a new one, because it require to have NS records then.
        So we must update records type by type.
        See https://developer.godaddy.com/doc#!/_v1_domains/recordReplaceType/
        """
        records_by_type = defaultdict(list)
        for record in schemed_data['records']:
            records_by_type[record['type']].append(record)

        async def handle_resp(resp):
            if resp.status == 404:
                self.log.error("GoDaddy DNS update error: {}".format(await resp.text()))
                raise DomainIsNotAvailableYet(
                    "Domain {} is not available for DNS updating".format(domain))
            if not resp.status == 200:
                try:
                    error_data = await resp.json()
                except:
                    self.log.error("Unknown dns update API response: {}".format(await resp.text()))
                    raise ProviderError("Bad Provider's API response")

                self.log.error("GoDaddy DNS update error: {}".format(error_data))
                raise ProviderError(payload={'response_message': error_data['message']})

        async with self.aiosession as session:
            for rec_type, records in records_by_type.items():
                url = self.api_url_build('domains/{domain}/records/{type}'.format(domain=domain, type=rec_type))
                async with session.put(url, headers=headers, json=records) as resp:
                    await handle_resp(resp)
