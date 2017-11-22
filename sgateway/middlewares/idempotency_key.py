import time

from sqlalchemy import Table, Column, Integer, String, desc

from sgateway.core.db import metadata
from sgateway.core.gateway_exceptions import RequestIdempotencyError
from sgateway.services.base.middleware import BaseMiddleware

IDEMPOTENCY_TTL = 60 * 60 * 24  # One day

IdempotencyModel = Table(
    'idempotancy_request', metadata,
    Column('key', String(32)),
    Column('timestamp', Integer, nullable=False, default=time.time),
    Column('scope_id', String(60)),
    # UniqueConstraint('key', 'scope_id', name='uix_1')
)


class IdempotencyKeyMiddleware(BaseMiddleware):
    """
    Refer to https://brandur.org/idempotency-keys.
    TLDR; Assume you have service method that initiate money transfer. To make sure that the same (from client point
    of view) transfer can't happen twice, because of e.g. network problems - you send idempotency_key with
    every request, so gateway can understand that those requests are the same.

    Now it's just decline inidempotent requests. But actually that's not the right way. I see two options here:
    - on a duplicated request, we can return the saved response (e.g. pickled and stored in IdempotencyModel),
    like we do for cache.
    - or we can try to delegate decision to Service Method. So, in case with money transfer, service would lookup
    database for the transfer with e.g. provided transaction id and return this transfer's status without creating
    a new one. (in real world though it obviously would be a different scenario)
    """

    webhook_friendly = True

    def __init__(self, *args, ttl=IDEMPOTENCY_TTL, **kwargs):
        self.ttl = ttl
        super(IdempotencyKeyMiddleware, self).__init__(*args, **kwargs)

    async def get_scope(self, service_request):
        try:
            entity_id = await service_request.entity_id
        except AttributeError:
            entity_id = None

        return "{}.{}".format(
            entity_id or 'any',
            service_request.path_repr,
        )

    async def check(self, service_request, key):
        scope_id = await self.get_scope(service_request)

        async with service_request.db_connection() as connection:
            q = IdempotencyModel.select(
                ((IdempotencyModel.c.key == key) &
                 (IdempotencyModel.c.scope_id == scope_id) &
                 (IdempotencyModel.c.timestamp > (time.time() - self.ttl))),
                for_update=True).order_by(desc(IdempotencyModel.c.timestamp))
            cursor = await connection.execute(q)
            idempotency_obj = await cursor.fetchone()
            if idempotency_obj:
                # We disallow new requests until previous request finished with some error (key will be deleted)
                # or when timer expired.
                raise RequestIdempotencyError("Lock expiring in {} sec".format(
                    idempotency_obj.timestamp - int(time.time() - self.ttl)))

            await connection.execute(IdempotencyModel.insert().values(key=key, scope_id=scope_id))

    async def process_request(self, service_request):
        if service_request.request is None:
            return

        idempotency_key = service_request.request.headers.get('X-Idempotency-Key',
                                                              service_request.request.args.get('idempotency_key'))
        if not idempotency_key:
            return

        await self.check(service_request, idempotency_key)
        service_request.add_extension('_idempotency_key', idempotency_key)

    async def process_response(self, service_request, service_response, gateway_error):
        idempotency_key = service_request.get_extension('_idempotency_key')
        if not idempotency_key:
            return

        if not service_response or not service_response.request_fulfilled:
            # Free up on error:
            # We treat it like non-executed task, so it is now safe to repeat it.
            scope_id = await self.get_scope(service_request)

            async with service_request.db_connection() as connection:
                q = IdempotencyModel.delete().where((IdempotencyModel.c.key == idempotency_key) &
                                                    (IdempotencyModel.c.scope_id == scope_id))
                await connection.execute(q)
