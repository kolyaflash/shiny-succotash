It's a potential place where we can have endpoints for non-services APIs.
Something like current [External API](https://github.com/semilimes/external_api).

It would share the same App (sanic.app), but will have it's own auth/routing/middlewares/handlers/etc.

Basically, _service_ gateway is RPC, while _resources_ must be RESTful endpoints.
