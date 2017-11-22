import inspect
from collections import defaultdict
from threading import local

from sgateway.core.helpers import Singleton


class AlreadyRegistered(Exception):
    pass


class _ServiceLocals(local):
    """
    Registry maintainable service state space that allow services to have some persistence,
    but still being pluggable.
    """

    def __init__(self):
        # Storage for strategies state holder
        self.strategies_scope = {}


class ServiceRegistry(metaclass=Singleton):
    """
    A registry which stores configurations off all installed services.

    Can be used as context manager, e.g.:

    ```
    with ServiceRegistry(_as_context=True) as sr:
        assert sr == ServiceRegistry()
    ```
    """

    __slots__ = ['_services', '_service_locals', '_providers']

    def __init__(self, *args, **kwargs):
        self._services = {}
        self._providers = {}
        self._service_locals = defaultdict(_ServiceLocals)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def register(self, service_cls_=None, **kwargs):
        # Decorator

        def wrapper(service_cls):
            _service_key = self.build_service_key(
                inspect.getattr_static(service_cls, '__name__'),
                inspect.getattr_static(service_cls, '__version__')
            )
            if _service_key in self._services:
                raise AlreadyRegistered("Service {} already registered in registry".format(_service_key))

            self._services[_service_key] = service_cls
            self._services[_service_key]._locals = self._service_locals[_service_key]
            self._providers[_service_key] = self._get_service_providers(service_cls)
            service_cls._service_registry = self
            return service_cls

        if service_cls_ is not None:
            return wrapper(service_cls_)

        return wrapper

    @staticmethod
    def build_service_key(name, version):
        assert name, "Service name is required"
        assert version, "Service version is required"
        return "{}_{}".format(name, version)

    @classmethod
    def _get_service_providers(cls, service_cls):
        items = {}

        for provider_class in service_cls.providers:
            items[inspect.getattr_static(provider_class, '__name__')] = {
                'class': provider_class,
                'methods': provider_class._collect_methods(),
            }

        return items

    def get_service(self, name, version=None):
        try:
            return self._services[self.build_service_key(name, version)]
        except KeyError:
            return None

    def get_services(self):
        return tuple(self._services.values())

    def get_provider(self, service_name, service_version, provider_name):
        try:
            return self._providers[self.build_service_key(service_name, service_version)][provider_name]['class']
        except KeyError:
            return

    def get_providers(self, service_name, service_version=None, required_methods=None):
        """
        Returns providers that have all methods listed in required_methods.

        :param service_name: str
        :param required_methods: list of str
        :return:
        """
        try:
            all_providers = self._providers[self.build_service_key(service_name, service_version)]
        except KeyError:
            return []

        if required_methods:
            providers = [name for name in all_providers
                         if not set(required_methods) - set([m.name for m in all_providers[name]['methods']])]
        else:
            providers = all_providers.keys()

        return [all_providers[name]['class'] for name in providers]
