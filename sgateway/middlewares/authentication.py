import jwt

from sgateway.core.gateway_exceptions import UnauthorizedApiException, TokenMalformed
from sgateway.services.base.middleware import BaseMiddleware


# from ssolib import ssoauth


class AuthMiddleware(BaseMiddleware):
    """
    Supported auth types:
        - Internal (Bearer Token) Using internal api key to decode JWT in "Authorization" header.
        - Debug/tests: omits any authorization


    Well... let's for now just work with requests on behalf of entity (entity_id required).
    user_id is optional and only some service methods will use user object.
    """
    INTERNAL_KEY = None

    def on_registered(self):
        self.INTERNAL_KEY = self.app.config.get('INTERNAL_GATEWAY_KEY')
        if not self.INTERNAL_KEY:
            raise Exception("INTERNAL_GATEWAY_KEY needs to be present to use AuthMiddleware")

    def process_request(self, service_request):
        auth_header = service_request.request.headers.get('Authorization', '')
        self.log.debug("Auth header: {}".format(auth_header))

        prefixes = ('Bearer', 'Token')
        bearer_token = None
        for prefix in prefixes:
            if prefix in auth_header:
                bearer_token = auth_header.partition(prefix)[-1].strip()
                break

        if not bearer_token and auth_header:
            raise TokenMalformed()

        if not bearer_token and self.app.config.get('IS_LOCAL', False):
            # username = service_request.request.app.name
            # service_request.add_extension('user', {'username': username})
            # self.log.debug("User authenticated: %s", username)
            self.log.debug('No auth for debug')
            service_request.add_lazy_property('entity_id', self.app.config['DEFAULT_ENTITY_ID'])
            service_request.add_lazy_property('user_id', self.app.config['DEFAULT_ENTITY_ID'])
            service_request.add_loggable_property('entity_id', self.app.config['DEFAULT_ENTITY_ID'])
            return

        elif not bearer_token:
            raise UnauthorizedApiException("No authorization provided")

        secret = self.INTERNAL_KEY
        try:
            token_data = jwt.decode(bearer_token, secret, algorithms=['HS256'])
        except jwt.exceptions.DecodeError:
            raise TokenMalformed("Unable to decode token. Value is: {}".format(bearer_token))

        self.log.debug("Auth data: {}".format(token_data))

        try:
            entity_id = token_data['entity_id'] or 1  # TODO: remove
        except KeyError:
            raise TokenMalformed("entity_id in credentials is required")

        service_request.add_lazy_property('entity_id', entity_id)
        service_request.add_loggable_property('entity_id', entity_id)
        service_request.add_lazy_property('user_id', token_data.get('user_id', None))
