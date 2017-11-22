import os

from sanic.exceptions import NotFound
from sanic.response import text

from sgateway.app import get_application


# Affects logging, auth, etc.
debug = os.environ.get("DEBUG_MODE", False)

app = get_application(debug=debug)


@app.exception(NotFound)
def ignore_404s(request, exception):
    return text("URL not found: {}".format(request.url), status=404)
