try:
    from types import AsyncGeneratorType
except ImportError:
    raise Exception("Unsupported python installation. PEP 525 required (available in CPython 3.6)")
from collections import namedtuple
from inspect import isawaitable
from types import GeneratorType

from jsonschema.exceptions import ValidationError
from jsonschema.validators import validate as validate_schema
from sanic.exceptions import InvalidUsage
from sanic.response import json as json_response
from sanic.response import stream

from sgateway.core.gateway_exceptions import BaseApiException, ServiceBadRequestError, InternalError
from sgateway.core.helpers import LazyProperty
from sgateway.core.logs import app_logger

LoggableProperty = namedtuple('LoggableProperty', ['name', 'value'])


class ServiceRequest(object):
    """
    ServiceRequest is an abstraction used for providing request's service handlers with context.
    Technically, not only HTTP requests could be wrapped in ServiceRequest, but AMQP/websockets/etc.

    Can be extended with `extensions`.
    """

    __slots__ = ('service', 'method', 'app', 'request', 'is_webhook', 'log',
                 '_extensions', '_loggable_properties')

    def __init__(self, service, method, app, request=None):
        """
        :param service: :class:`services.base.service.BaseService`
        :param method: :class:`services.base.service.ServiceMethod`
        :param app: :class:`core.base_app.GatewayApp`
        :param request: :class:`core.base_app.SGatewayRequest`
        """

        self.service = service
        self.method = method
        self.app = app
        self.request = request
        self.is_webhook = method.webhook if method else None
        self._extensions = {}
        self.log = app_logger.getChild('request')

        # Service query properties that are important to be observable via logs/etc.
        # They are not welcome to be set on Service level, but on a system level (e.g. by middlewares).
        self._loggable_properties = []

    def __repr__(self):
        return repr("<Request {}>".format(self.path_repr))

    @property
    def path_repr(self):
        return "{service}.v{version}.{method}".format(
            service=self.service.name,
            version=self.service.version,
            method=self.method.name,
        )

    def db_connection(self):
        """
        :return: coroutine
        """

        if not hasattr(self.app, 'db'):
            raise InternalError("App has no db extension available.")
        return self.app.db.connection()

    def add_extension(self, key, obj):
        self._extensions[key] = obj

    def get_extension(self, key):
        return self._extensions.get(key, None)

    def require_extension(self, key):
        ext = self.get_extension(key)
        if not ext:
            raise InternalError("No required request extension: {}".format(key))
        return ext

    def add_lazy_property(self, name, var_or_callable):
        """
        :param name: attribute name that will be added to instance
        :param var_or_callable: var, function or coroutine.
        :return:
        """
        setattr(self.__class__, name, property(LazyProperty(self.app.loop, var_or_callable)))

    def add_loggable_property(self, name, value):
        """
        :param name: str
        :param value: JSON serializable value. But no validation here (EAFP)
        :return:
        """
        self._loggable_properties.append(LoggableProperty(str(name), value))

    def get_loggable_properties(self):
        return {
            prop.name: prop.value for prop in self._loggable_properties
        }

    def get_data(self, schema=None, allow_use_args=True):
        """
        If called for HTTP GET request - uses data from querystring. Otherwise, for HTTP POST/mq request
        trying to use request.json.

        Validates input if request_schema presents.
        :return: *validated* data from request
        """

        schema = schema if schema else self.method.request_schema

        if self.request is None:
            raise NotImplementedError("request required")

        if self.request.method == 'GET' and allow_use_args:
            data = self.request.args
        else:
            try:
                data = self.request.json
            except InvalidUsage:
                raise ServiceBadRequestError("JSON data expected")

        if schema:
            try:
                validate_schema(data, schema)
            except ValidationError as e:
                raise ServiceBadRequestError("Input schema error", payload={'error_path': list(e.absolute_path),
                                                                            'error_message': e.message})
        return data


    def get_arg(self, name, default=None, list=False):
        if self.request is not None:
            if not list:
                return self.request.args.get(name, default=default)
            else:
                return self.request.args.getlist(name, default=default)
        raise NotImplementedError("request required")

    def get_client_ip(self):
        if self.request is not None:
            return self.request.remote_addr


class ServiceResponse(object):
    """
    The general idea is the same as for ServiceRequest.
    ServiceResponse is a abstraction for request handling which could be represented as
    HTTP/other response in different formats.

    ServiceResponse always contains a result of calling service. It's not a general purpose response, e.g.
    errors are handled with exceptions.
    """

    def __init__(self, response_data, request_fulfilled, **kwargs):
        """
        :param response_data: dict or whatever serializable.
        :param request_fulfilled: True or False, indicates if service really did the job that party requested.
        """
        self.extra_headers = {}
        self.response_data = response_data
        self.request_fulfilled = request_fulfilled
        self.extra_params = kwargs

    def render_to_http_response(self, service_request):
        """
        TODO: extend

        :param service_request: :class:`services.ServiceRequest`
        :return: HttpResponse
        """
        response_format = 'json'

        if response_format == 'json':
            return json_response(self.response_data, headers=self.extra_headers,
                                 status=self.extra_params.get('status_code', 200))

        raise NotImplementedError("Format is not supported")

    def add_header(self, name, value):
        self.extra_headers[name] = value


class ServiceStreamResponse(ServiceResponse):
    """
    Chunked response class. Basically used for binary content transfer.
    """

    def __init__(self, response_generator, content_type, request_fulfilled, **kwargs):
        """
        :param response_generator: generator or async generator that generates response chunks
        :param content_type: content type string
        """
        super(ServiceStreamResponse, self).__init__(None, request_fulfilled, **kwargs)
        self._response_generator = response_generator
        self._content_type = content_type

    def render_to_http_response(self, service_request):
        """
        :param service_request: :class:`services.ServiceRequest`
        :return: StreamingHTTPResponse
        """

        async def streaming_fn(response):
            """
            http://sanic.readthedocs.io/en/latest/sanic/response.html#streaming
            :param response:
            :return:
            """
            if isinstance(self._response_generator, AsyncGeneratorType):
                async for chunk in self._response_generator:
                    response.write(chunk)
            elif isinstance(self._response_generator, GeneratorType):
                for chunk in self._response_generator:
                    response.write(chunk)
            else:
                raise TypeError("{} is not supported type".format(type(self._response_generator)))

        return stream(streaming_fn, content_type=self._content_type, headers=self.extra_headers)


class RequestHandler(object):
    """
    Dispatching request (`ServiceRequest`) to service methods calls.
    Implements wrapping request into custom middlewares, that represents
    gateway's request pipeline.
    """

    def __init__(self, service_request: ServiceRequest):
        self.service_request = service_request
        self.service = service_request.service
        self.method = service_request.method

    async def make_response(self, middlewares):
        service_response = None
        exception = None

        try:
            service_response = await self._run_gateway_middlewares('request', middlewares)
            if not service_response:
                service_response_ = self.service.call_method(self.method.class_attr, self.service_request)

                if isawaitable(service_response_):
                    service_response = await service_response_
                else:
                    service_response = service_response_
                assert isinstance(service_response, ServiceResponse), \
                    "Response must be instance of ServiceResponse"
        except BaseApiException as e:
            exception = e
            raise
        finally:
            service_response_ = await self._run_gateway_middlewares('response', middlewares, service_response,
                                                                    exception)
            if service_response_:
                assert isinstance(service_response, ServiceResponse), \
                    "Response must be instance of ServiceResponse"
                service_response = service_response_

        return service_response

    async def _run_gateway_middlewares(self, handle_phase,
                                       middlewares,
                                       service_response: ServiceResponse = None,
                                       gateway_error: BaseApiException = None):
        """
        There is a difference in Incoming Pipleline (request phase) and Outgoing Pipeline (response phase):
        *
            During Incoming processing, if middleware returns HttpResponse - we DON'T stop executing next middlewares,
            but instead give them a chance to get called. BUT, exactly first not-None response is eventually returned.
        *
            During Outgoing processing - we go thought all the middlewares before return response.
            So response could be overrided/altered by underlying middlewares.

        :param handle_phase: str, 'request'/'response'
        :param middlewares: list of middlewares
        :param service_response: ServiceResponse instance or None
        :return: ServiceResponse or None
        """
        assert handle_phase in ('request', 'response')

        for middleware_obj in middlewares:
            if self.service_request.is_webhook and not middleware_obj.webhook_friendly:
                # Skip middlewares for webhooks. E.g., we don't need auth there.
                continue

            if handle_phase == 'request':
                _response = middleware_obj._process_request(self.service_request)
                if isawaitable(_response):
                    _response = await _response
                if _response:
                    if service_response is None:
                        service_response = _response
            elif handle_phase == 'response':
                _response = middleware_obj._process_response(self.service_request, service_response, gateway_error)
                if isawaitable(_response):
                    _response = await _response
                if _response:
                    service_response = _response
        return service_response
