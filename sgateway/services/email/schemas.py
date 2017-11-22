import jsl


class Person(jsl.Document):
    email = jsl.EmailField(required=True)
    name = jsl.StringField()

    class Options(object):
        definition_id = 'Person'


class EmailMessage(jsl.Document):
    from_email = jsl.DocumentField(Person, as_ref=True, required=True)
    reply_to = jsl.DocumentField(Person, as_ref=True)
    to = jsl.ArrayField(jsl.DocumentField(Person, as_ref=True), min_items=1, required=True)
    cc = jsl.ArrayField(jsl.DocumentField(Person, as_ref=True), min_items=1)
    bcc = jsl.ArrayField(jsl.DocumentField(Person, as_ref=True), min_items=1)
    subject = jsl.StringField(required=True)
    body_plain_text = jsl.StringField(required=True)
    body_html = jsl.StringField(required=False)
    # Use premailer to turns CSS blocks into style attributes
    transform_css = jsl.BooleanField(default=False)

    class Options(object):
        definition_id = 'EmailMessage'
        title = 'Email Message'


def person_format(d):
    if not d:
        return
    if type(d) is list:
        return ', '.join([person_format(x) for x in d])
    if d.get('name'):
        return u"{} <{}>".format(d['name'], d['email'])
    return d['email']
