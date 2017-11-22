from operator import itemgetter

from sgateway.core.gateway_exceptions import InternalError
from .base.strategy import BaseProviderChoiceStrategy


class RoundRobinStrategy(BaseProviderChoiceStrategy):
    """
    Straightforward round-robin implementation. State is stored as incremented value in the service locals (so it's
    not distributed and is threadsafe).
    See :ref:`Services reliability` section in docs.
    """

    class LocalsStorage(object):
        namespace = 'round_robin_calls'

        def __init__(self, storage_obj):
            if storage_obj is None:
                raise InternalError("Impossible to use RoundRobinStrategy due to unavailable `locals`")

            self.storage_obj = storage_obj
            if not self.namespace in self.storage_obj:
                self.storage_obj[self.namespace] = {}

        def get(self, provider_name):
            try:
                return self.storage_obj[self.namespace][provider_name]
            except KeyError:
                return 0

        def incr(self, provider_name):
            try:
                self.storage_obj[self.namespace][provider_name] += 1
            except KeyError:
                self.storage_obj[self.namespace][provider_name] = 1

    def __init__(self, *args, calls_storage=LocalsStorage, **kwargs):
        super(RoundRobinStrategy, self).__init__(*args, **kwargs)
        self.calls_storage = calls_storage(self.locals)

    def select(self, request, providers):
        call_rates = []
        for provider in providers:
            call_rates.append((provider, self.calls_storage.get(provider.name)))

        call_rates = sorted(call_rates, key=itemgetter(1))

        try:
            provider = call_rates[0][0]
        except IndexError:
            return None

        self.calls_storage.incr(provider.name)

        # print("%s num_calls: %s", provider.__name__, self.calls_storage.get(provider.name))
        return provider
