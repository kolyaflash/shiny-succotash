import jsl


class RateSchema(jsl.Document):
    currency = jsl.StringField()
    value = jsl.NumberField()

    class Options(object):
        definition_id = 'Rate'


class RatesSchema(jsl.Document):
    base = jsl.StringField(required=True)
    rates = jsl.ArrayField(jsl.DocumentField(RateSchema, as_ref=True))
    datetime = jsl.DateTimeField(required=True)

    class Options(object):
        definition_id = 'Rates'
        title = 'Rates'


class ConvertQuerySchema(jsl.Document):
    # TODO: do all currencies are 3 letters?
    from_currency = jsl.StringField(max_length=3, min_length=3, required=True)
    to_currency = jsl.ArrayField(jsl.StringField(max_length=3, min_length=3, required=True))
    amount = jsl.NumberField(required=True, minimum=0)

    class Options(object):
        definition_id = 'ConvertQuery'
        title = 'Convert Query'
