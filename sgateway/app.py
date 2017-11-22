import asyncio

import uvloop

from sgateway.core.base_app import GatewayApp
from sgateway.core.views import common_blueprint
from sgateway.services.views import create_blueprint as create_services_blueprint

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


def get_application(loop=None, debug=None, config_module=None):
    app = GatewayApp('sgateway', loop=loop, debug=debug, config_module=config_module)
    app.blueprint(common_blueprint)
    app.blueprint(create_services_blueprint())
    return app


if __name__ == '__main__':
    debug = True
    app = get_application(debug=debug)
    app.run(host="0.0.0.0", port=8000, debug=debug)  # Sanic ingores debug=False anyway
