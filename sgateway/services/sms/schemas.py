import jsl


class SenderNumber(jsl.Document):
    value = jsl.StringField(pattern='^(\+\d{1,3}[- ]?)?\d{10}$')

    class Options(object):
        definition_id = 'SenderNumber'


class SenderAlphaname(jsl.Document):
    value = jsl.StringField(pattern='^(?=.*[a-zA-Z])(?=.*[a-zA-Z0-9])([a-zA-Z0-9 ]{1,11})$')

    class Options(object):
        definition_id = 'SenderAlphaname'


class SMSMessage(jsl.Document):
    sender = jsl.OneOfField([jsl.DocumentField(SenderNumber, as_ref=True),
                             jsl.DocumentField(SenderAlphaname, as_ref=True)],
                            required=True)
    to_number = jsl.StringField(required=True)
    body = jsl.StringField(required=True, max_length=1600)

    class Options(object):
        title = 'SMS Message'
