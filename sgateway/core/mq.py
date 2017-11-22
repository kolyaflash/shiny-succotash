from pydoc import locate

from sanic.request import Request
from sl_mqlib.base import BaseMessageHandler
from sl_mqlib.exceptions import MessageRequireRequeue, AbandonMessage

from sgateway.core.gateway_exceptions import BaseApiException, ServiceUnavailable, ServiceBadRequestError
from sgateway.core.logs import app_logger
from sgateway.services.registry import ServiceRegistry
from sgateway.services.request import ServiceRequest, RequestHandler


class GatewayMQRequest(Request):
    def __init__(self, app, message, *args, **kwargs):
        super(GatewayMQRequest, self).__init__(*args, **kwargs)
        self.app = app
        self.message = message
        try:
            self.parsed_json = message.data.get('payload', {})
        except AttributeError:
            raise ServiceBadRequestError("Unexpected data")

    @property
    def scheme(self):
        return 'amqp'


class GatewayMQHandler(BaseMessageHandler):
    QUEUE_NAME = 'sgateway_calls'

    def __init__(self, app, channel=None, middlewares=None, **kwargs):
        self.app = app
        self.registry = kwargs.pop('service_registry', ServiceRegistry())
        self.middlewares = self._locate_middleware_classes(app) if middlewares is None else middlewares
        self.log = app_logger.getChild('mq.handler.{}'.format(self.QUEUE_NAME))

        super(GatewayMQHandler, self).__init__(**kwargs)

        if channel and self.QUEUE_NAME:
            channel.allocate_queue(None, self, self.QUEUE_NAME, dynamic=False)

    @staticmethod
    def _locate_middleware_classes(app):
        """
        :param app: current app
        :return: generator
        """
        middlewares = []

        for class_path in app.config['SERVICES_PIPELINE_MIDDLEWARES']:
            middleware_class = locate(class_path)
            if not middleware_class:
                raise ImportError("Can not import service middleware: {}".format(class_path))
            middlewares.append(middleware_class(app))
        return middlewares

    def build_service_request(self, message):
        request = GatewayMQRequest(self.app, message, '//{}'.format(self.QUEUE_NAME).encode(), {}, None, None, None)

        try:
            _service_name, _service_version, _service_method = (
                message.data['service'],
                message.data.get('version', 1),
                message.data['method'])
        except KeyError:
            raise ServiceBadRequestError("Message data has wrong format")

        service_class = self.registry.get_service(_service_name, _service_version)
        if not service_class:
            raise ServiceUnavailable("Service {} v.{} is unavailable".format(_service_name, _service_version))

        service = service_class(self.app)
        method = service.get_method(_service_method)
        if not method:
            raise ServiceUnavailable("Method {} is unavailable".format(_service_method))

        service_request = ServiceRequest(service, method, self.app, request=request)
        self.log.debug("Message via '{}' to '{}/{}' received".format(message.routing_key, service.name, method.name))
        return service_request

    async def handle(self, message):
        assert type(message.data) is dict, "Bad message data format. Did you provide content_type?"

        service_request = self.build_service_request(message)
        handler = RequestHandler(service_request)

        try:
            response = await handler.make_response(self.middlewares)
        except BaseApiException as e:
            if e.client_retry:
                self.log.info("Service call via MQ produced error, but will be requeued")
                raise MessageRequireRequeue()
            else:
                self.log.error("Service call via MQ produced permanent error")
                raise AbandonMessage()
        except Exception as e:
            self.log.error(e)
            # Since we didn't get known error, we don't know what to do.
            raise AbandonMessage()
        else:
            self.log.debug("Handled message: {}. Resp: {}".format(message, response))
