import copy

import aiohttp
import sendgrid

from sgateway.core.gateway_exceptions import ProviderError
from sgateway.services.base.provider import BaseServiceProvider
from sgateway.services.utils import provide_method
from .schemas import person_format


class MockedProvider(BaseServiceProvider):
    __name__ = '_mocked_'

    @provide_method()
    async def send(self, data):
        return True


class SendgridProvider(BaseServiceProvider):
    __name__ = 'sendgrid'
    __verbose_name__ = 'Sendgrid'
    __maintainer_details__ = """
    https://sendgrid.com/docs/API_Reference/api_v3.html
    
    RESTful V3 API provides functionality for managing user unsubscribes, templating emails,
    managing IP addresses, and enforcing TLS.
    """

    def __init__(self, *args, **kwargs):
        super(SendgridProvider, self).__init__(*args, **kwargs)
        SENDGRID_API_KEY = self.require_config('SENDGRID_API_KEY')

        self.sendgrid = sendgrid.SendGridAPIClient(apikey=SENDGRID_API_KEY)

    @property
    def aiosession(self):
        return aiohttp.ClientSession(loop=self.app.loop, headers=self.sendgrid._get_default_headers())

    async def send_via_http(self, data):
        """
        :param data: email object (dict)
        :return: Errors if any or None
        """
        url = self.sendgrid.client.mail.send._build_url(query_params={})

        async with self.aiosession as session:
            async with session.post(url, json=data) as resp:
                if resp.status != 202:
                    try:
                        resp = await resp.json()
                    except:
                        raise ProviderError("Unexpected error [{}]: {}".format(resp.status, await resp.text()))
                    return resp['errors']

    @provide_method()
    async def send(self, data):
        """
        TODO: don't parse data manually here; better error handling

        :param data: :ref:`EmailMessage` schema friendly data.
        :return: bool (sent or not)
        """
        payload = copy.deepcopy(data)

        payload['from'] = payload.pop('from_email', None)
        payload['reply_to'] = payload.pop('reply_to', None)
        payload['personalizations'] = [{
            'subject': payload.pop('subject'),
            'to': payload.pop('to'),
            'cc': payload.pop('cc', None),
            'bcc': payload.pop('bcc', None),
        }]
        payload['content'] = []

        plain_text = payload.pop('body_plain_text', None)
        html_body = payload.pop('body_html', None)

        if plain_text:
            payload['content'].append({
                'type': 'text/plain',
                'value': plain_text,
            })

        if html_body:
            payload['content'].append({
                'type': 'text/html',
                'value': html_body,
            })

        errors = await self.send_via_http(payload)

        if errors:
            self.log.error(u"Sendgrid error: %s" % errors[0]['message'])
            return False

        return True


class MailgunProvider(BaseServiceProvider):
    __name__ = 'mailgun'
    __verbose_name__ = 'Mailgun'
    __maintainer_details__ = """
    https://documentation.mailgun.com/en/latest/api-sending.html#examples
    """

    def __init__(self, *args, **kwargs):
        super(MailgunProvider, self).__init__(*args, **kwargs)
        MAILGUN_DOMAIN = self.require_config('MAILGUN_DOMAIN')
        self.api_url = "https://api.mailgun.net/v3/{}/messages".format(MAILGUN_DOMAIN)

    @property
    def aiosession(self):
        MAILGUN_API_KEY = self.require_config('MAILGUN_API_KEY')

        return aiohttp.ClientSession(loop=self.app.loop, headers={
            'Accept': 'application/json',
        }, auth=aiohttp.BasicAuth('api', MAILGUN_API_KEY))

    @provide_method()
    async def send(self, data):
        """
        Note - mailgun is not a json api, it accepts multipart/form-data.
        :param data:
        :return: True
        """
        # Mailgun doesn't accepts nulls, so.
        mailgun_payload = {k: v for k, v in dict({
            'from': person_format(data['from_email']),
            'to': person_format(data.get('to')),
            "cc": person_format(data.get('cc')),
            "bcc": person_format(data.get('bcc')),
            "subject": data['subject'],
            "text": data.get('body_plain_text'),
            "html": data.get('body_html'),
        }).items() if v is not None}

        response_data = None
        async with self.aiosession as session:
            async with session.post(self.api_url, data=mailgun_payload) as response:
                try:
                    response_data = await response.json()
                except:
                    raise ProviderError("Unexpected error [{}]: {}".format(response.status,
                                                                           await response.text()))

        if response_data.get('id'):
            return True

        self.log.error("Mailgun sending fails: %s" % response_data)
        raise ProviderError("Mailgun error %s" % response_data)


class PostmarkProvider(BaseServiceProvider):
    __name__ = 'postmark'
    __verbose_name__ = 'Postmark'
    __maintainer_details__ = """
    https://postmarkapp.com/developer/user-guide/sending-email/sending-with-api

    In a nutshell, the service replaces SMTP (or Sendmail) with a far more reliable, scalable and
    care-free environment.
    In addition, you can track statistics such as number of emails sent or processed, opens,
    bounces and spam complaints.
    """

    @property
    def aiosession(self):
        POSTMARK_API_KEY = self.require_config('POSTMARK_API_KEY')

        return aiohttp.ClientSession(loop=self.app.loop, headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Postmark-Server-Token': POSTMARK_API_KEY,
        })

    @provide_method()
    async def send(self, data):

        postmark_payload = {
            # "From": person_format(data['from_email']),
            "From": self.app.config['POSTMARK_SENDER'],
            "To": person_format(data.get('to')),
            "Cc": person_format(data.get('cc')),
            "Bcc": person_format(data.get('bcc')),
            "Subject": data['subject'],
            "TextBody": data.get('body_plain_text'),
            "HtmlBody": data.get('body_html'),
        }

        response_data = None
        async with self.aiosession as session:
            async with session.post('https://api.postmarkapp.com/email', json=postmark_payload) as response:
                try:
                    response_data = await response.json()
                except:
                    raise ProviderError("Unexpected error [{}]: {}".format(response.status,
                                                                           await response.text()))

        if response_data.get('MessageID'):
            return True

        self.log.error("Postmark sending fails: %s" % response_data)
        raise ProviderError("Postmark error %s" % response_data['ErrorCode'])
