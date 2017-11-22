from sgateway.core.logs import app_logger


class BaseProviderChoiceStrategy(object):
    def __init__(self, app=None, locals=None):
        self.app = app
        self.locals = locals
        self.log = app_logger.getChild('strategies.{}'.format(self.__class__.__name__))

    def select(self, request, providers):
        """
        :param request: HTTP request
        :param providers: list of provider classes
        :return: provider instance or None
        """
        return
