import jsl


class RegistrantAddressSchema(jsl.Document):
    address1 = jsl.StringField(required=True, format='street-address', max_length=41)
    address2 = jsl.StringField(format='street-address2', max_length=41)
    city = jsl.StringField(required=True, format='city-name', max_length=30)
    state = jsl.StringField(required=True, format='state-province-territory',
                            description='State or province or territory',
                            min_length=2, max_length=30)
    postal_code = jsl.StringField(required=True, format='postal-code', description='Postal or zip code',
                                  min_length=2, max_length=10)
    country = jsl.StringField(required=True, format='iso-country-code', min_length=2, max_length=2)


class RegistrantPhoneSchema(jsl.Document):
    country_code = jsl.StringField(required=True, pattern=r'^\+\d{1,3}$')
    global_number = jsl.StringField(required=True, pattern=r'^\d{6,14}$')


class RegistrantContactSchema(jsl.Document):
    first_name = jsl.StringField(required=True, format='person-name', max_length=30)
    last_name = jsl.StringField(required=True, format='person-name', max_length=30)
    middle_name = jsl.StringField(required=True, format='person-name', max_length=30)
    organization = jsl.StringField(required=True, format='organization-name', max_length=100)
    email = jsl.StringField(required=True, format='email', max_length=80)
    phone = jsl.DocumentField(RegistrantPhoneSchema, as_ref=True,
                              required=True)  # jsl.StringField(required=True, format='phone', max_length=17)
    fax = jsl.DocumentField(RegistrantPhoneSchema, as_ref=True, required=False)
    mailing_address = jsl.DocumentField(RegistrantAddressSchema, as_ref=True, required=True)

    class Options(object):
        title = 'Domain Registrant Contact'


class DomainRegistrationClientFormSchema(jsl.Document):
    registrant_contact = jsl.DocumentField(RegistrantContactSchema, as_ref=True, required=True)

    # There could be other contacts, but now we'll fill them with our own data.

    class Options(object):
        title = 'Domain Registration Form'


class DNSRecord(jsl.Document):
    type = jsl.StringField(enum=['A', 'AAAA', 'CNAME', 'MX', 'NS', 'SOA', 'SRV', 'TXT'], required=True)
    name = jsl.StringField(min_length=1, max_length=255, required=True)
    data = jsl.StringField(min_length=1, max_length=255, required=True)
    priority = jsl.NumberField(minimum=1)  # Record priority (MX and SRV only)
    ttl = jsl.NumberField(minimum=1)
    service = jsl.StringField()  # Service type (SRV only)
    protocol = jsl.StringField()  # Service protocol (SRV only)
    port = jsl.NumberField(minimum=1, maximum=65535)  # Service port (SRV only)
    weight = jsl.NumberField(minimum=1)  # Record weight (SRV only)

    class Options(object):
        title = 'DNS Record'
        definition_id = 'DNSRecord'

class DNSRecordsSchema(jsl.Document):
    records = jsl.ArrayField(jsl.DocumentField(DNSRecord, as_ref=True), min_items=1, required=True)

    class Options(object):
        title = 'Domain DNS Records'
