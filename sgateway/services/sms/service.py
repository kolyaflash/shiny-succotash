from sgateway.core.gateway_exceptions import ServiceInternalError
from sgateway.core.utils import get_schema_models
from sgateway.services import BaseService, expose_method
from .providers import TwillioProvider
from .schemas import SMSMessage
from ..registry import ServiceRegistry

registry = ServiceRegistry()


@registry.register
class SMSService(BaseService):
    __name__ = 'sms'
    __verbose_name__ = 'SMS Service'

    providers = (
        TwillioProvider,
    )

    @expose_method(request_schema=SMSMessage.get_schema(), http_method='POST')
    async def send(self, service_request):
        data = service_request.get_data()
        self.log.debug("data is: %s", data)

        SmsMessage = get_schema_models(SMSMessage).SmsMessage
        data_obj = SmsMessage(**data)

        result = await self.failover_provider_call(service_request, 'send_sms', data_obj)
        if not result:
            raise ServiceInternalError("Sorry, can't send the SMS")
        return self.result({})
