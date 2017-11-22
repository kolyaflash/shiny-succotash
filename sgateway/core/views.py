import json

from sanic import Blueprint, response

from sgateway.services import ServiceRegistry

common_blueprint = Blueprint('my_blueprint')

html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
}


@common_blueprint.route('/')
async def root(request):
    enabled_services = {}
    for serv in ServiceRegistry().get_services():
        serv = serv(request.app)
        enabled_services["{}_v{}".format(serv.__name__, serv.version)] = {
            'providers': [str(x(request.app).name) for x in ServiceRegistry().get_providers(serv.name, serv.version)],
        }

    data_str = json.dumps({
        'routes': [{'uri': route.uri, 'methods': list(route.methods)}
                   for route in request.app.router.routes_all.values()],
        'enabled_services': enabled_services,
    }, indent=4)

    return response.html(u'<pre>{}</pre>'.format("".join(html_escape_table.get(c, c) for c in data_str)))
