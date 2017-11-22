from sgateway.services.base.middleware import BaseMiddleware


class TranslationMiddleware(BaseMiddleware):
    """
    prototype
    """

    async def translate(self, request, data):
        lang = request.get_lang()
        translated_data = data
        return translated_data

    async def process_response(self, service_request, service_response, gateway_error):
        if hasattr(service_response, 'fields_to_translate'):
            service_response.response_data = await self.translate(service_request, service_response.response_data)
