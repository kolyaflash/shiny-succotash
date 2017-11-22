from sgateway.core.logs import app_logger
from sgateway.services.request import ServiceRequest, ServiceResponse
from sgateway.core.gateway_exceptions import BaseApiException


class BaseMiddleware(object):
    """
    This middlewares are the last place where it's safe to work with `request` and `response` as such.
    Underlying request handling will go with `service_request` instead, which is filled with
    extra functionality by this middlewares.
    """
    webhook_friendly = False

    def __init__(self, app):
        self.app = app
        self.log = app_logger.getChild('middlewares.{}'.format(self.__class__.__name__))

    def on_registered(self):
        """
        Override it to do something in app initiate phase.
        :return:
        """
        return

    def _process_request(self, service_request: ServiceRequest):
        if hasattr(self, 'process_request'):
            return self.process_request(service_request)

    def _process_response(self, service_request: ServiceRequest, service_response: ServiceResponse,
                          gateway_error: BaseApiException):
        """
        :param service_request: ServiceRequest
        :param service_response: CAN BE "None"!
        :return: None or new ServiceResponse
        """
        if hasattr(self, 'process_response'):
            return self.process_response(service_request, service_response, gateway_error)
