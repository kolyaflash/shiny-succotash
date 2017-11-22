import jsl


class SaleLine(jsl.Document):
    line_number = jsl.NumberField(minimum=1, required=True)
    quantity = jsl.NumberField(minimum=1, required=True)
    amount_total = jsl.NumberField(required=True)
    item_code = jsl.StringField(max_length=50)  #: SKU e.g. Y0001
    tax_code = jsl.StringField(max_length=25)  #: e.g. PS081282
    description = jsl.StringField(max_length=256)  #: Item name/description

    class Options(object):
        definition_id = 'SaleLine'


class Address(jsl.Document):
    street_line1 = jsl.StringField(max_length=100)
    street_line2 = jsl.StringField(max_length=100)
    city = jsl.StringField(max_length=50)
    region_code = jsl.StringField(max_length=3)
    country_code = jsl.StringField(min_length=2, max_length=2, format='iso-country-code')
    postal_code = jsl.StringField(max_length=11)

    class Options(object):
        definition_id = 'Address'


class SaleTaxQuery(jsl.Document):
    sale_id = jsl.StringField(max_length=50)  #: aka transaction code
    customer_id = jsl.StringField(max_length=50, required=True)
    salesperson_id = jsl.StringField(max_length=25)
    lines = jsl.ArrayField(jsl.DocumentField(SaleLine, as_ref=True), required=True)
    date = jsl.StringField(format='date', required=True)
    amount = jsl.NumberField()
    currency = jsl.StringField(min_length=3, max_length=3, format='iso-currency-code', required=True)
    ship_from_address = jsl.DocumentField(Address, as_ref=True, required=True)
    ship_to_address = jsl.DocumentField(Address, as_ref=True, required=True)
    ordered_at_address = jsl.DocumentField(Address, as_ref=True)
    acceptence_at_address = jsl.DocumentField(Address, as_ref=True)

    class Options(object):
        title = 'Sale Tax Query'


class SaleLineTaxes(jsl.Document):
    rate = jsl.NumberField()
    tax_name = jsl.StringField()
    country = jsl.StringField()
    region = jsl.StringField()
    tax_code_id = jsl.StringField()
    tax_type = jsl.StringField()
    tax_jurisdiction = jsl.StringField()

    class Options(object):
        definition_id = 'SaleLineTaxes'


class SaleLineTaxResult(jsl.Document):
    line_number = jsl.NumberField(minimum=1, required=True)
    taxes = jsl.ArrayField(jsl.DocumentField(SaleLineTaxes, as_ref=True, required=True))

    class Options(object):
        definition_id = 'SaleLineTaxResult'


class SaleTaxResponse(jsl.Document):
    total_tax = jsl.NumberField()
    lines = jsl.ArrayField(jsl.DocumentField(SaleLineTaxResult, as_ref=True, required=True))

    class Options(object):
        title = 'Sale Tax Response'
