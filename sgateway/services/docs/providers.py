import aiohttp

from sgateway.core.gateway_exceptions import ProviderError
from ..base.provider import BaseServiceProvider
from ..utils import provide_method


class SemilimesProvider(BaseServiceProvider):
    __name__ = 'semilimes'
    __verbose_name__ = 'Semilimes'
    __maintainer_details__ = """
    Our hosted PDF generator API.
    """

    def __init__(self, *args, **kwargs):
        super(SemilimesProvider, self).__init__(*args, **kwargs)
        self.DOCS_API_URL = self.require_config('DOCS_API_URL')

    @provide_method()
    async def html_to_pdf(self, data):
        """
        Yielding chunked response (pdf file).
        !!! First yielded item is actual `content-type`.

        :returns: binary file's chunks or raise exception
        """
        aiosession = aiohttp.ClientSession(loop=self.app.loop, headers={})
        url = '{}/{}/'.format(self.DOCS_API_URL.rstrip('/'), 'htmltopdf')
        chunk_size = 1024 * 1024  # 1 MB

        async with aiosession as session:
            async with session.post(url, json=data) as resp:
                if resp.status == 200:
                    # This hack is needed, because any other ways would need execution outside of contextmanager
                    # and request session would be closed.
                    yield resp.content_type
                    while True:
                        chunk = await resp.content.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
                    return

                self.log.error(u"Docs API error {}.".format(resp.status))
                self.log.debug(u"Body was: {}.".format(await resp.read()))
                raise ProviderError("Error rendering your document ({})".format(resp.status))
