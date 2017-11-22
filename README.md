#### Documentation
See [docs for docs](docs/README.md) to get docs and see docs.


### Requirements

python3.6, postgres, redis, sl_mqlib


#### Install for devs

	pip install -r ./requirements/local.txt
	APP_CONFIG_MODULE=sgateway.config.local python manage.py run_server

#### Install on prod

	pip install -r ./requirements.txt
	export APP_CONFIG_MODULE='sgateway.config.prod'
	python ./manage.py credentials decrypt --passphrase 123 --override 
	alembic upgrade head
	gunicorn wsgi:app --bind 0.0.0.0:8000 --worker-class sanic.worker.GunicornWorker -w 2

#### Testing

	pip install -r ./requirements/tests.txt
	pytest ./tests/
	
	
#### DB managment

New revision (migration):

	APP_CONFIG_MODULE=sgateway.config.local alembic revision --autogenerate

Apply latest revision (migration):

	APP_CONFIG_MODULE=sgateway.config.local alembic upgrade head
	
Rollback last revision:

	APP_CONFIG_MODULE=sgateway.config.local alembic downgrade -1



#### Configuration

#####  Env vars

`LOG_LEVEL` (default `info`)

`DB_URL` (postgresql://localhost:5432/sgateway_default)

`INTERNAL_GATEWAY_KEY`

`REDIS_HOST` (localhost)
`REDIS_PORT` (default 6379)
`REDIS_DB` (default 0)

`MESSAGE_BUS_AMQP_URL` (Semilimes Message Bus RabbitMQ)

`DOCS_API_URL` (https://docs.semilimes.info)

##### Credentials vars

Just refer to vars in `local.cfg`.


### Credentials Config

Credentials (e.g. third party services tokens) are stored in encrypted `.cfg` files. Filename must follow config module name
(e.g. `local.cfg` for `sgateway.config.local`).

If you know passphrase for needed credentials config, you can decrypt it and unencrypted `.cfg` file 
will be automatically loaded by the app and settings available at `app.config`.
	
For example, for local: 

	APP_CONFIG_MODULE=sgateway.config.local ./manage.py credentials decrypt --passphrase 123 


After you added/modified config vars in credentials config, you encrypt it back and commit to repo:
 
	APP_CONFIG_MODULE=sgateway.config.local ./manage.py credentials encrypt --passphrase 123
	git add config/credentials/local.cfg.aes && git commit -m 'update credentials config'



Business goals
-----------------------

*
	**provide highly available service.** for example, we have service for currency exchange rates (Service).
	so when the request to get latest exchange rates (Method) came in, and fixer.io (Provider) is currently
	down, we, instead of return error to client, trying to get rates from (currencylayer.com).

*
	**cost efficiency.** depending on a requester party, we could be in favour of provider A rather than
	provider B, because calling provider A is cheaper because of, let's say, requester's country of residency.
	Same time, it can be cheaper to call some provider A for particular task (e.g. convert currency), but
	expensive for another one (e.g. get all currency rates).

*
	**apply charges for requesting service gateway.** but the idea is to charge user independently of
	used provider. so *cost efficiency* matters, because saved costs is our revenue.

*
	**incapsulation.** Provides the optimal API for each client.
	Simplifies the client by moving logic for calling multiple services from the client to API gateway.
	Translates from a “standard” public web-friendly API protocol to whatever protocols are used internally. Etc.


*
	**be analysable.** we must know as much metrics of services usage as possible. also, we must be able
	to easily find a particular request to find out about e.g. it's cost, source and destination.



Architecture overview
-----------------------

#### Central Config

???
 

#### Services Blueprint

`sgateway.services.views.ServicesBlueprint` is a special Sanic's blueprint that automatically discover 
services (specified in config), discover gateway middlewares and adds routes with custom handler
(that handler runs gateway middlewares) and generated urls.


#### Services Registry

`sgateway.services.registry.ServiceRegistry` is a class (singleton) that holds list of
services and providers. Registry is also able to provide meta schema of services (used in python client).



#### ServiceRequest/ServiceResponse

`sgateway.services.request.ServiceRequest` / `sgateway.services.request.ServiceResponse` are abstractions
that intended to incapsulate different sources: regular HTTP requests, webhooks callbacks, websockets or even Semilimes Message Queue messages.
They are used all over underlying levels of request processing starting from Router's handler.  

#### Request Pipeline

Request Pipeline is basically a set of middlewares (`sgateway.services.base.middleware.BaseGatewayMiddleware`) 
specified in Blueprint.

Those middlewares works with request/response abstractions
and can change request flow or modify response; do extra things, like apply billing costs or check
API rate limits.


#### Service/Provider

Service (`sgateway.services.base.service.BaseService`) can expose it's methods to be accessible by
clients. To do the job, Service do call one of the Service Providers. E.g. `Emails` is a Service.
`send` is a Service Method and `Sendrid` is a Provider. Service _inderectly_ returns data to client. 

#### Provider Strategy

Service may require a Provider to do the job. Different Strategies (`sgateway.services.base.strategy.BaseProviderChoiceStrategy`)
can be used to define which Provider is better in taking this particular job.

There is also a few special ways of choosing provider: 

* 
	`sgateway.services.base.service.BaseService#failover_provider_call` can try to accomplish result by
	calling different Providers (sequentially) until one of them finally done without errors.

*
	Always using same Provider when request means not provider-agnostic operations. E.g. if we
	purchased a domain name from GoDaddy - we should also manage this domain thought GoDaddy. 

	`provider = await self.get_provider(service_request, provider_name='godaddy])`


### Persistence Layer

##### Postgres

Can be used for anything, from Core to Providers. `aiopg` + `SQLAlchemy` (without ORM obviously) is used to access database.

One can simply use `Table` and use global `metadata`, so table will be registered in migrations 
(just make sure that module containing Model is importing during app startup).

```python
from sqlalchemy import Table, Column, Integer, String
from sgateway.core.db import metadata

UserModel = Table('user', metadata,
    Column('user_id', Integer, primary_key=True),
    Column('user_name', String(16), nullable=False),
    Column('email_address', String(60)),
    Column('password', String(20), nullable=False)
)

# ...

async def handler(app):
	async with app.db.connection() as conn:
		cursor = await conn.execute(UserModel.select())
		user = await cursor.fetch_one()
		return user
``` 
	
##### Redis

Redis is available via `aioredis`.

```python
async def handler(app):
	with await app.redis_pool as conn:
		conn.set('key', 'cached val')
	return
```


##### Semilimes Message Queue

See `sl_mqlib`. `AsyncioUniversalChannel` from sl_mqlib is used.
 
There is a `sgateway.core.mq.GatewayMQHandler` that listening for messages on a queue and turn
them into Service calls (one way only; no request's responses).
 

**Publisher is available:**
```python
from sl_mqlib.serializer import JsonSerializer

async def handler(app):
	data = {'foo': 'bar'}
	app.mq_channel.publish('sl.topic', data, routing_key='test.test', serializer_class=JsonSerializer)
```



### Service Example

```python

class Provider1(BaseServiceProvider):
		
	@provide_method()
	def send_email(self, email):
		self.send_via_http(email)


class Provider2(BaseServiceProvider):
	
	@provide_method()
	def send_email(self, email):
		self.send_via_smtp(email)

class EmailCostSaving(RoundRobinStrategy):

	def select(self, request, providers):
		return self.best_for_this_email(request.get_data()['to_email'], providers)


registry = ServiceRegistry()

@registry.register()
class TestService(BaseService):
    __name__ = 'test_service'
    __version__ = 1
    providers = (Provider1, Provider2)
    provider_strategy = EmailCostSaving 

    @expose_method(http_method='POST', request_schema=EmailSchema)
    async def test_method(self, service_request):
    	provider = await self.get_provider(service_request, required_methods=['send_email'])
    	provider.send_email(service_request.get_data())
        return self.result({'success': True})
```
