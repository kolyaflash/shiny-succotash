from sgateway.services.base.middleware import BaseMiddleware

PRICELIST = {
    'email': {
        'send': {
            'cost': 0.01,
        },
    },
    'sms': {
        'send': {
            'cost': 0.5,
        }
    },
    'currency_exchange': {
        'rates': {
            'cost': 0.001,
        }
    }
}


class BillingMiddleware(BaseMiddleware):
    async def process_request(self, service_request):
        # Hold funds here and check if funds sufficient.
        # So, there we obviously need to know entity/user and provider we are going to use
        return

    async def process_response(self, service_request, service_response, gateway_error):
        if not service_response:
            return

        try:
            entity_id = await service_request.entity_id
            assert entity_id is not None
        except (AttributeError, AssertionError):
            self.log.error("Can not bill request that doesn't provide entity")
            return

        try:
            cost = PRICELIST[service_request.service.name][service_request.method.name]['cost']
        except KeyError:
            return

        self.log.debug("Request billed: %s", cost)
        service_response.add_header('X-Request-Cost', cost)
        service_response.add_header('X-Request-Cost-Currency', 'USD')
        service_request.add_loggable_property('cost', cost)
