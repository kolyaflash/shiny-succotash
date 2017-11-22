try:
    from types import AsyncGeneratorType
except ImportError:
    raise Exception("Unsupported python installation. PEP 525 required (available in CPython 3.6)")

from .providers import SemilimesProvider
from ..base.service import BaseService
from ..registry import ServiceRegistry
from ..utils import expose_method

registry = ServiceRegistry()


@registry.register()
class DocsService(BaseService):
    __name__ = 'docs'
    __version__ = 1
    __verbose_name__ = 'Docs'

    providers = (SemilimesProvider,)

    @expose_method(http_method='POST')
    async def html_to_pdf(self, service_request):
        prov = await self.get_provider(service_request, required_methods=['html_to_pdf'])
        gen_or_res = prov.html_to_pdf(service_request.get_data())

        if not isinstance(gen_or_res, AsyncGeneratorType):
            # So treat this as simply kinda dict. But anyway it's not expected now.
            # return self.result({)
            raise NotImplementedError("Don't know what to do with non-generator")

        # Besides for getting content_type, it's also important to start out iteration and get errors here
        # rather than after response-to-browser channel already opened.
        content_type = await gen_or_res.__anext__()
        return self.stream_response(gen_or_res, content_type)
