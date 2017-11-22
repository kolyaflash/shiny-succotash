import base64
import pickle

from sgateway.services.base.middleware import BaseMiddleware
from sgateway.services.request import ServiceResponse

"""
This straightforward CacheMiddleware is more about demonstration of how it could be implemented.

Release version must be much more thought through. E.g. pickling is not the best way to serialize response,
and quering redis all the time will get a lot of cache misses.
"""


class CacheMiddleware(BaseMiddleware):
    """
    Middleware expects `global_cache` param in `service_response.extra_params` and if presents -
    saves response's `response_data` as binary.

    It returns new `ServiceResponse` from process_request.
    """
    _cache_key = "cached_response_{request_uniform}"

    def _get_request_uniform(self, service_request):
        query_string = base64.b64encode(service_request.request.query_string.encode()).decode()
        return base64.b64encode("{}_{}".format(service_request.path_repr,
                                               query_string).encode()).decode()

    async def process_request(self, service_request):
        if service_request.request.method != 'GET':
            return

        cache_key = self._cache_key.format(request_uniform=self._get_request_uniform(service_request))
        self.log.debug('cache_key: {}'.format(cache_key))

        with await self.app.redis_pool as conn:
            cached_val = await conn.get(cache_key)

        if cached_val:
            val = pickle.loads(cached_val)
            self.log.debug("Use cached val: {}".format(val))
            service_request.add_loggable_property('from_cache', True)
            return ServiceResponse(val, request_fulfilled=True)

    async def process_response(self, service_request, service_response, gateway_error):
        if service_request.request.method != 'GET':
            return
        if not service_response:
            return

        if service_response.extra_params.get('global_cache'):
            cache_val = pickle.dumps(service_response.response_data)
            cache_key = self._cache_key.format(request_uniform=self._get_request_uniform(service_request))
            with await self.app.redis_pool as conn:
                # Cache for 5 mins
                await conn.setex(cache_key, 60 * 5, cache_val)
            self.log.debug("Put resp in cache. Key: {}".format(cache_key))
