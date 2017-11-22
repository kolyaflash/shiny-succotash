class BaseApiException(Exception):
    """
    message - the text for developers with some specific info if provided
    description - the text for developers
    error_code - arbitrarily assigned error number used for documentation and debugging.
    """
    status_code = 400
    error_code = '000'
    description = None
    client_retry = False  # Means it's recommended to retry request immediately or soon.

    def __init__(self, message=None, status_code=None, payload=None, client_retry=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload
        self.client_retry = client_retry if client_retry is not None else self.client_retry
        self.error_name = self.__class__.__name__

    def __str__(self):
        return self.message

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        rv['description'] = self.description or ''
        rv['error_code'] = self.error_code
        rv['error_name'] = self.error_name
        rv['retry_suggested'] = self.client_retry
        return rv


# Common exceptions

class InternalError(BaseApiException):
    status_code = 500
    error_code = '000'
    description = 'Something went wrong internally. Ask developers.'


# Auth and access errors

class AuthException(BaseApiException):
    status_code = 403
    description = 'Not valid auth credentials or access denied'


class UnauthorizedApiException(AuthException):
    status_code = 401
    description = 'Access Denied'
    error_code = '001'


class UnauthenticatedApiException(AuthException):
    error_code = '002'


class TokenMalformed(AuthException):
    error_code = '003'
    description = 'Token passed has invalid content'


# Service errors

class ServiceUnavailable(BaseApiException):
    status_code = 400
    description = 'Service you requested can not be accessed at the moment'


class ServiceNotFound(ServiceUnavailable):
    error_code = '004'
    status_code = 404
    description = 'Service you requested is not registered or method is unavailable'


class ProviderUnavailable(ServiceUnavailable):
    status_code = 500
    error_code = '005'


class ServiceRestricted(ServiceUnavailable):
    status_code = 403
    error_code = '006'
    description = 'Service not available for the requester'


class ServiceBadRequestError(BaseApiException):
    error_code = '007'
    status_code = 400
    description = 'Request data or args are invalid'


class RequestIdempotencyError(ServiceBadRequestError):
    description = 'Request is not idempotent'


class ServiceInternalError(ServiceUnavailable):
    status_code = 500
    description = 'Request can not be processed because of service/provider problem'


class InsufficientFunds(ServiceRestricted):
    pass


class FailoverFailError(ServiceUnavailable):
    status_code = 500
    description = 'Available providers was not able to handle request'
    client_retry = True


class ProviderError(ServiceUnavailable):
    status_code = 500
    description = 'Error happened in provider operations'
    error_code = '008'


class ConfigurationError(ServiceUnavailable):
    status_code = 500
    description = "System configuration can't satisfy provider needs"
    error_code = '009'


# Rate limiting

class QuotaExceeded(BaseApiException):
    status_code = 429
    error_code = '020'
    description = "You've made too many requests. But quota resets every hour."


class TotalQuotaExceeded(QuotaExceeded):
    error_code = '021'


class ServiceQuotaExceeded(QuotaExceeded):
    error_code = '022'
