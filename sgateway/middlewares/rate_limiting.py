from sgateway.core.gateway_exceptions import TotalQuotaExceeded, ServiceQuotaExceeded
from sgateway.services.base.middleware import BaseMiddleware

ONE_HOUR = 60 * 60

"""
Rate limiting config must be stored in Central Config and be manageable by admins.
So something like `expose_method` decorator parameters is actually not a good place for it.

Rate limits are applied on per-entity level. The quota could be extended by additional payments to Semilimes,
so don't consider those as a constant values anyway. 
"""

RATE_LIMITS = {
    # 5000 in hour
    'total': {
        'quota': 5000,
        'window': ONE_HOUR,
    },
    'per_service': {
        'email': {
            'quota': 100,
            'window': ONE_HOUR,
            'only_limit_fulfilled': True,
        },
        'currency_exchange': {
            'quota': 100,
            'window': 60,
            'only_limit_fulfilled': True,
        }
    },
}


class RateLimitingMiddleware(BaseMiddleware):
    def __init__(self, *args, **kwargs):
        super(RateLimitingMiddleware, self).__init__(*args, **kwargs)

    async def _get_total_key(self, service_request, entity_id):
        return 'total_api_usage_{}'.format(entity_id)

    async def _get_service_key(self, service_request, entity_id):
        return 'service_usage_{}_{}'.format(service_request.service.name, entity_id)

    async def process_request(self, service_request):

        async def number_left(rconn, key_name, quota, expire):
            """
            :param rconn: aioredis.connection.RedisConnection or Pool
            :param key_name: redis key
            :param quota: int
            :param expire: int
            :return: Bool (if do need to raise error)
            """

            if quota >= 0:
                current_usage = await rconn.get(key_name)
                if current_usage is None:
                    if expire:
                        rconn.setex(key_name, expire, 0)
                    else:
                        rconn.set(key_name, 0)
                    current_usage = 0
            else:
                current_usage = 0

            return quota - int(current_usage)

        try:
            entity_id = await service_request.entity_id
        except AttributeError:
            return

        total_limit, total_expire = RATE_LIMITS['total']['quota'], RATE_LIMITS['total']['window']
        _service_limit = RATE_LIMITS['per_service'].get(service_request.service.name, {})
        service_limit, service_expire = _service_limit.get('quota', -1), _service_limit.get('window', None)

        with await self.app.redis_pool as conn:
            # Check service requests quota
            service_requests_left = await number_left(conn, await self._get_service_key(service_request, entity_id),
                                                      service_limit, service_expire)

            if service_requests_left == 0:
                raise ServiceQuotaExceeded()

            if service_requests_left > 0:
                service_request.add_extension('service_requests_left', service_requests_left)

            # Check overall requests quota
            total_requests_left = await number_left(conn, await self._get_total_key(service_request, entity_id),
                                                    total_limit, total_expire)
            if total_requests_left == 0:
                raise TotalQuotaExceeded()

            if total_requests_left > 0:
                service_request.add_extension('total_requests_left', total_requests_left)

        self.log.debug("Rate Limit Quota is OK")

    async def process_response(self, service_request, service_response, gateway_error):
        try:
            entity_id = await service_request.entity_id
        except AttributeError:
            return

        _only_fulfilled = lambda: RATE_LIMITS['per_service'].get(
            service_request.service.name, {}).get('only_limit_fulfilled', False)

        if not service_response or (not service_response.request_fulfilled and _only_fulfilled()):
            # Don't count this request in quotas.
            return

        with await self.app.redis_pool as conn:
            pipe = conn.pipeline()
            pipe.incr(await self._get_service_key(service_request, entity_id))
            pipe.incr(await self._get_total_key(service_request, entity_id))
            self.app.loop.create_task(pipe.execute())

        total_requests_left = service_request.get_extension('total_requests_left')
        if total_requests_left is not None:
            service_response.add_header('X-Total-Quota', total_requests_left - 1)

        service_requests_left = service_request.get_extension('service_requests_left')
        if service_requests_left is not None:
            service_response.add_header('X-Service-Quota', service_requests_left - 1)
