import inspect
from collections import namedtuple

from sgateway.core.gateway_exceptions import ProviderUnavailable, FailoverFailError
from sgateway.core.gateway_exceptions import ServiceBadRequestError, ServiceInternalError
from sgateway.core.logs import app_logger
from sgateway.services.request import ServiceResponse, ServiceStreamResponse
from sgateway.services.strategies import RoundRobinStrategy

ServiceMethod = namedtuple('ServiceMethod', ['name', 'class_attr', 'webhook', 'http_method', 'request_schema'])


class BaseService(object):
    __verbose_name__ = None
    __version__ = 1
    _registered = False
    #: _locals is a special memory that is maintained thought registry.
    #: It can be unavailable if service wasn't received thought registry, so be careful.
    _locals = None
    _service_registry = None
    providers = ()
    provider_strategy = RoundRobinStrategy  #: The default strategy

    @property
    def name(self):
        return self.__name__

    @property
    def version(cls):
        return cls.__version__

    def __init__(self, app, service_registry=None):
        super(BaseService, self).__init__()
        self.app = app
        self.log = app_logger.getChild('services.{}'.format(self.__class__.__name__))
        self._methods = self._collect_methods()
        if service_registry is not None:
            self._service_registry = service_registry

    def on_registered(self):
        return

    @classmethod
    def _collect_methods(cls):
        found_methods = []
        for method_name, method_fn in [(n, m) for n, m in inspect.getmembers(cls)
                                       if hasattr(m, '_service_method')]:
            found_methods.append(ServiceMethod(method_fn._method_name,
                                               method_fn.__name__,
                                               method_fn._webhook,
                                               method_fn._http_method,
                                               method_fn._request_schema or {}))
        return tuple(found_methods)

    def iter_exposed_methods(self):
        """
        It's not ok to work with methods as a dataset, so you can just iterate over them.
        :return: iterator
        """
        yield from ((x.name, x) for x in self._methods)

    def _get_available_providers(self, required_methods=None):
        available_providers = self._service_registry.get_providers(self.name,
                                                                   self.version,
                                                                   required_methods=required_methods)
        if not available_providers:
            raise ProviderUnavailable("No providers available")
        return (provider_class(self.app) for provider_class in available_providers)

    def _serialize_service(self):
        methods = {method.name: {
            'name': method.name,
            'http_method': method.http_method,
            'request_schema': method.request_schema or {},
        } for _, method in self.iter_exposed_methods()}

        return {
            'name': self.name,
            'version': self.version,
            'verbose_name': self.__verbose_name__,
            'methods': methods,
        }

    def get_service_schema(self):
        return self._serialize_service()

    """
    Public methods
    """

    def get_method(self, method_name):
        for name, func in self.iter_exposed_methods():
            if name == method_name:
                return func

    def call_method(self, attr_name, service_request, *args, **kwargs):
        """
        :param attr_name: attribute name to call
        :param service_request: ServiceRequest obj
        :param args: passed to class method on call
        :param kwargs: passed to class method on call
        :return: `ServiceResponse` or awaitable
        """
        method_ = getattr(self, attr_name)
        assert hasattr(method_, '_service_method'), "Not allowed to be called"
        resp = method_(service_request, *args, **kwargs)
        return resp

    """
    Internal use methods
    """

    def _get_locals(self, scope=None):
        """
        :param scope: attr name of substorage obj
        :return: locals storage obj or None
        """
        _service_locals = getattr(self, '_locals', None)
        strategy_locals = None
        if _service_locals is not None:
            strategy_locals = _service_locals if scope is None else getattr(_service_locals, scope)
        return strategy_locals

    def _get_strategy(self):
        return self.provider_strategy(self.app, locals=self._get_locals('strategies_scope'))

    async def get_provider(self, service_request, required_methods=None, provider_name=None, strategy=None):
        """
        :param required_methods: list of required Provider method names.
        :param provider_name: Name of concrete provider to get (strategy won't be used)
        :param strategy: :ref:`BaseProviderChoiceStrategy` instance
        :return: ServiceProvider
        """
        if provider_name and (required_methods or strategy):
            raise UserWarning("It doesn't make sense to call it additional arguments when provider_name provided")

        selected = None

        # We don't even need strategy for this case. Just try to find provider among available.
        if provider_name is not None:
            found_class = self._service_registry.get_provider(
                service_request.service.name, service_request.service.version, provider_name)
            if not found_class:
                raise ProviderUnavailable("Provider '{}' is unavailable for this service.".format(provider_name))
            selected = found_class(self.app)

        # When we need to come up with best suitable
        if not selected:
            strategy = strategy if strategy is not None else self._get_strategy()
            available_providers = self._get_available_providers(required_methods)
            selected_ = strategy.select(service_request, available_providers)
            selected = await selected_ if inspect.isawaitable(selected_) else selected_

            if not selected:
                self.log.info("Can not select provider using `{}` strategy".format(strategy.__class__.__name__))
                raise ProviderUnavailable("Can not select service provider")

            self.log.debug("Provider `{}` selected via `{}` strategy".format(selected.name,
                                                                             strategy.__class__.__name__))

        # TODO: can we get out of this implicity?
        service_request.add_loggable_property('provider', selected.name)
        return selected

    async def failover_provider_call(self, service_request, method_name, *args, **kwargs):
        """
        Trying to call method over suitable providers one by one (using strategy), until ones returned result.
        This method tries to guaranty at-least-once delivery. It's up to providers to satisfy at-most-once delivery,
        so be careful.

        :param service_request:
        :param method_name:
        :param args: passed to provider method
        :param kwargs: passed to provider method
        :return:
        """
        available_providers = list(self._get_available_providers([method_name]))
        strategy = self._get_strategy()
        silent = kwargs.pop('_silent', False)

        i = 1
        while available_providers:
            provider = strategy.select(service_request, available_providers)
            try:
                result = await provider.call_method(method_name, *args, _silent=silent, **kwargs)
            except Exception as e:
                available_providers.remove(provider)
                if not silent:
                    self.log.exception(e)
                i += 1
                continue
            else:
                if i > 1:
                    self.log.info("Failover provider call `{}` was successful in {} attempts (via {})".format(
                        method_name,
                        i,
                        provider.name,
                    ))

                # TODO: can we get out of this implicity?
                service_request.add_loggable_property('provider', provider.name)

                return result

        raise FailoverFailError()

    def result(self, resp_data, **kwargs):
        request_fulfilled = kwargs.pop('request_fulfilled', True)
        return ServiceResponse(resp_data, request_fulfilled, **kwargs)

    def stream_response(self, response_generator, content_type, **kwargs):
        request_fulfilled = kwargs.pop('request_fulfilled', True)
        return ServiceStreamResponse(response_generator, content_type, request_fulfilled, **kwargs)

    def request_error(self, resp_data, *args, **kwargs):
        raise ServiceBadRequestError()

    def internal_error(self, message, details_payload=None):
        raise ServiceInternalError(message=message, payload=details_payload)
