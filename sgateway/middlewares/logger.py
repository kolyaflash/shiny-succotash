import time

from sl_mqlib.serializer import JsonSerializer

from sgateway.services.base.middleware import BaseMiddleware


class RequestStartTimeMiddleware(BaseMiddleware):
    webhook_friendly = True

    def process_request(self, service_request):
        service_request.add_extension("_start_time", time.time())


class LoggerMiddleware(BaseMiddleware):
    webhook_friendly = True

    def log_via_mq(self, service_name, data):
        if not self.app.mq_channel:
            raise ConnectionError("MQ producer not available")

        if not self.app.mq_channel.connected():
            raise ConnectionError("Logging unavailable due to MQ disconnection")

        self.app.mq_channel.publish('sl.topic', data,
                                     routing_key='sgateway.log.service_request.{}'.format(service_name),
                                     serializer_class=JsonSerializer)

    def process_response(self, service_request, service_response, gateway_error):

        # Do internal debug logging
        if not service_response:
            self.log.debug("REQUEST ERROR: {}".format(
                gateway_error.to_dict() if gateway_error else str(gateway_error)))

        # Do external service request logging
        log_data = {'log_message': ""}
        if service_request.request is not None:
            if service_request.is_webhook:
                log_data['log_message'] = u'Webhook callback on {} [{}]'.format(
                    service_request.request.url,
                    service_request.request.method)
            else:
                log_data['log_message'] = u'Request to {} [{}]'.format(
                    service_request.request.url,
                    service_request.request.method)
            log_data['protocol'] = service_request.request.scheme
        else:
            raise NotImplementedError("How to log this?")

        log_data['service'] = service_request.service.name
        log_data['version'] = service_request.service.version
        log_data['method'] = service_request.method.name
        log_data['request_fulfilled'] = service_response.request_fulfilled if service_response else False

        # Measure time
        _start_time = service_request.get_extension("_start_time")
        if _start_time:
            service_request.add_loggable_property('processing_time', round(time.time() - _start_time, 3))

        # E.g. {'prop_cost': 1, 'prop_superhero_name': 'Halk'}
        log_data.update({"prop_{}".format(k): v for k, v in service_request.get_loggable_properties().items()})

        if gateway_error:
            log_data['error_name'] = gateway_error.error_name
            log_data['error_msg'] = gateway_error.message


        if self.app.config.get('SERVICE_MQ_LOGGING'):
            try:
                self.log_via_mq(service_request.service.name, log_data)
            except Exception as e:
                if self.app.debug:
                    raise

                # TODO: Ignore logging problem for now, but basically logs are essential.
                self.log.warning("Can not send log to MQ: {}".format(e))
        else:
            self.log.debug("Log data: {}".format(log_data))
