import premailer
from sgateway.core.gateway_exceptions import ServiceInternalError
from sgateway.services import BaseService, expose_method, webhook_callback
from .providers import SendgridProvider, PostmarkProvider, MailgunProvider
from .schemas import EmailMessage
from ..registry import ServiceRegistry

registry = ServiceRegistry()


@registry.register
class EmailService(BaseService):
    __name__ = 'email'
    __verbose_name__ = 'Emails service'

    providers = (
        SendgridProvider,
        PostmarkProvider,
        MailgunProvider,
    )

    @expose_method(request_schema=EmailMessage.get_schema(), http_method='POST')
    async def send(self, service_request):
        data = service_request.get_data()
        self.log.debug("data is: %s", data)
        if data.get('transform_css', False) and 'body_html' in data:
            # Use premailer to turns CSS blocks into style attributes
            # TODO: make async
            data['body_html'] = premailer.transform(data['body_html'])

        result = await self.failover_provider_call(service_request, 'send', data)
        if not result:
            raise ServiceInternalError("Sorry, can't send the email")
        return self.result({'sent': True})

    @webhook_callback(method_name='save_email_status')
    async def email_callback(self, service_request):
        return self.result({})
