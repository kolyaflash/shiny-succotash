#: Only this methods can be used for service methods
ALLOWED_METHODS = ['GET', 'POST']


def expose_method(http_method=None, request_schema=None, method_name=None, webhook=False):
    """
    Decorator to register method as service method and allow to expose it via url

    :param http_method: one of :data:`ALLOWED_METHODS`
    :param request_schema:
    :param method_name:
    :param webhook:
    :return:
    """
    # Mark class method
    http_method = (http_method or 'GET').upper()
    if http_method not in ALLOWED_METHODS:
        raise ValueError("HTTP method {} is not allowed for exposed method".format(http_method))

    def wrap(fn):
        fn._method_name = method_name or fn.__name__
        fn._service_method = True
        fn._webhook = webhook
        fn._http_method = http_method
        fn._request_schema = request_schema
        return fn

    return wrap


def webhook_callback(*args, **kwargs):
    """
    Decorator to register webhoock method

    :param args:
    :param kwargs:
    :return: :func:`expose_method` with webhook=True
    """
    def wrap(fn):
        return expose_method(*args, webhook=True, **kwargs)(fn)

    return wrap


def provide_method(**kwargs):
    def wrap(fn):
        fn._method_name = fn.__name__
        fn._provider_method = True
        return fn

    return wrap
