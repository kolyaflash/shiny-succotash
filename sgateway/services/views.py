import importlib
from pydoc import locate

from sanic import Blueprint, response

from sgateway.core.gateway_exceptions import ServiceNotFound, ServiceUnavailable
from . import ServiceRegistry, ServiceRequest, RequestHandler


class ServicesBlueprint(Blueprint):
    """
    When registered in app, this customized blueprint automatically finds and build service routes.
    """

    def __init__(self, *args, **kwargs):
        self.service_registry = kwargs.pop('service_registry', ServiceRegistry())
        self._middleware_classes = kwargs.pop('middleware_classes', None)
        self._registered_for_app = None
        super(ServicesBlueprint, self).__init__(*args, **kwargs)

    def _service_request_handler_factory(self, service, method):
        async def request_handler(request, *args, **kwargs):
            """
            :return: HttpResponse
            """
            service_request = ServiceRequest(service, method, request.app, request)
            handler = RequestHandler(service_request)
            service_response = await handler.make_response(self.gateway_middlewares)
            if not service_response:
                raise ServiceUnavailable("Service didn't return any response")
            return service_response.render_to_http_response(service_request)

        # __name__ needed for Sanic internals
        request_handler.__name__ = '{}_v{}_{}'.format(service.name, service.version, method.name)
        return request_handler

    def _locate_middleware_classes(self, app):
        """
        :param app: current app
        :return: generator
        """
        for class_path in app.config['SERVICES_PIPELINE_MIDDLEWARES']:
            middleware_class = locate(class_path)
            if not middleware_class:
                raise ImportError("Can not import service middleware: {}".format(class_path))
            yield middleware_class

    def register_services_routes(self, app):
        # By importing modules, we make them register themselves at the registry.
        for mod_path in app.config['INSTALLED_SERVICES']:
            importlib.import_module(mod_path)

        # Register service methods and webhooks routes
        for service_cls in self.service_registry.get_services():
            service = service_cls(app)
            for method_name, method in service.iter_exposed_methods():
                prefix = '/' if not method.webhook else '/_webhooks/'
                uri = '{prefix}{service_name}/v{version}/{method_name}'.format(
                    prefix=prefix, service_name=service.name,
                    version=service.version,
                    method_name=method_name)
                self.route(
                    uri=uri,
                    methods=[method.http_method],
                    strict_slashes=True,
                    stream=False,
                )(self._service_request_handler_factory(service, method))

            service.on_registered()

    def register_middlewares(self, app):
        # Register services specific middlewares
        self.gateway_middlewares = []

        if self._middleware_classes is not None:
            middlewares = self._middleware_classes
        else:
            middlewares = self._locate_middleware_classes(app)

        for middleware_class in middlewares:
            mw = middleware_class(app)
            mw.on_registered()
            self.gateway_middlewares.append(mw)

    def register(self, app, options):
        if self._registered_for_app and self._registered_for_app is not app:
            raise RuntimeError("Blueprint already registered in another app")

        if not self._registered_for_app:
            self.register_services_routes(app)
            self.register_middlewares(app)
            self._registered_for_app = app
        return super(ServicesBlueprint, self).register(app, options)


def services_schema(request):
    service_registry = ServiceRegistry()
    schema = []
    for service in service_registry.get_services():
        schema.append(service(request.app).get_service_schema())
    return response.json(schema)


def service_schema(request, service_name, service_version):
    service_registry = ServiceRegistry()

    service = service_registry.get_service(service_name, service_version)
    if not service:
        raise ServiceNotFound()

    schema = service(request.app).get_service_schema()
    return response.json(schema)


def create_blueprint(service_registry=None, middleware_classes=None):
    if service_registry is None:
        service_registry = ServiceRegistry()

    services_blueprint = ServicesBlueprint('services', '/services',
                                           service_registry=service_registry,
                                           middleware_classes=middleware_classes)
    services_blueprint.add_route(services_schema, '/_schema', methods=['GET'], strict_slashes=False)
    # Should comes last.
    services_blueprint.add_route(service_schema, '/<service_name>/v<service_version>', methods=['GET', 'OPTIONS'],
                                 strict_slashes=False)
    return services_blueprint
