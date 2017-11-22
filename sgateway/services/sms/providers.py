import aiohttp

from sgateway.core.gateway_exceptions import ProviderError
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.utils import provide_method


class MockedProvider(BaseServiceProvider):
    __name__ = '_mocked_'

    @provide_method()
    async def send_sms(self, obj):
        return True

    @provide_method()
    def send_mms(self, obj):
        raise NotImplementedError()


class TwillioProvider(BaseServiceProvider):
    __name__ = 'twillio'
    __verbose_name__ = 'Twillio'
    __maintainer_details__ = """
    https://www.twilio.com/docs/api/messaging/send-messages

    Sending a message is as simple as POSTing to the Messages resource. We'll outline required and optional
    parameters, messaging services, alphanumeric sender ID, rate limiting, and handling message replies below.
    """

    def __init__(self, *args, **kwargs):
        super(TwillioProvider, self).__init__(*args, **kwargs)
        TWILLIO_SID = self.require_config('TWILLIO_SID')

        self.api_url = "https://api.twilio.com//2010-04-01/Accounts/{AccountSid}/".format(
            AccountSid=TWILLIO_SID) + '{method}.json'

    @property
    def aiosession(self):
        TWILLIO_SID = self.require_config('TWILLIO_SID')
        TWILLIO_TOKEN = self.require_config('TWILLIO_TOKEN')

        return aiohttp.ClientSession(loop=self.app.loop, headers={
            'Accept': 'application/json',
        }, auth=aiohttp.BasicAuth(TWILLIO_SID, TWILLIO_TOKEN))

    @provide_method()
    async def send_sms(self, obj):
        payload = {
            'To': obj.to_number,
            'From': obj.sender.value,
            'Body': obj.body,
        }

        response_data = None
        async with self.aiosession as session:
            url = self.api_url.format(method='Messages')
            self.log.debug("Request url is: {}".format(url))
            async with session.post(url, data=payload) as response:
                try:
                    response_data = await response.json()
                except:
                    raise ProviderError("Unexpected error [{}]: {}".format(response.status,
                                                                           await response.text()))
        if response_data.get('sid'):
            self.log.debug("SMS successfully sent. Details: {}".format(response_data))
            return True
        else:
            raise ProviderError("Twillio error: {}. Details: {}".format(
                response_data['error_code'],
                response_data
            ))

    @provide_method()
    def send_mms(self, obj):
        raise NotImplementedError()
