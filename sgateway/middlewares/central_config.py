from pydoc import locate

from sgateway.services.base.middleware import BaseMiddleware


class CentralConfigProvider(object):
    pass


class DummyCentralConfig(CentralConfigProvider):
    pass


class ConsulCentralConfig(CentralConfigProvider):
    pass


class CentralConfigMiddleware(BaseMiddleware):
    def __init__(self, *args, **kwargs):
        super(CentralConfigMiddleware, self).__init__(*args, **kwargs)
        self.config_provider = locate(self.app.config['CENTRAL_CONFIG_CLASS'])()

    async def process_request(self, service_request):
        service_request.add_extension('central_config', self.config_provider)

    async def process_response(self, request, response, gateway_error):
        pass
