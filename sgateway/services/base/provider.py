import inspect
from collections import namedtuple

from sgateway.core.gateway_exceptions import ConfigurationError, ProviderError, BaseApiException
from sgateway.core.logs import app_logger

ProviderMethod = namedtuple('ProviderMethod', ['name', 'class_attr'])


class BaseServiceProvider(object):
    __verbose_name__ = None
    __maintainer_details__ = None
    _registered = False

    @property
    def name(self):
        return self.__name__

    def __init__(self, app, *args, **kwargs):
        super(BaseServiceProvider, self).__init__()
        self.app = app
        self.log = app_logger.getChild('providers.{}'.format(self.__class__.__name__))

    @classmethod
    def _collect_methods(cls):
        found_methods = []
        for method_name, method_fn in [(n, m) for n, m in inspect.getmembers(cls)
                                       if hasattr(m, '_provider_method')]:
            found_methods.append(ProviderMethod(method_fn._method_name,
                                                method_fn.__name__))
        return tuple(found_methods)

    def require_config(self, name):
        value = self.app.config.get(name, None)
        if value is None:
            raise ConfigurationError("{} is required to use {} provider".format(name, self.name))
        return value

    def has_method(self, method_name):
        method = getattr(self, method_name, None)
        return (method and hasattr(method, '_provider_method'))

    async def call_method(self, method_name, *args, **kwargs):
        method_ = getattr(self, method_name)
        silent = kwargs.pop('_silent', False)
        assert hasattr(method_, '_provider_method'), "Not allowed to be called"
        try:
            res = method_(*args, **kwargs)
            if inspect.isawaitable(res):
                res = await res
        except Exception as e:
            if isinstance(e, BaseApiException):
                raise
            # Catch any unexpected errors.
            if not silent:
                self.log.exception(e)
            raise ProviderError("Error occurred during provider call. Try again later.")

        return res
