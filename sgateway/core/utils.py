import python_jsonschema_objects as pjo
from jsl import Document


def get_schema_models(schema):
    """
    :param schema: dict or jsl class
    :return: models namespace
    """

    if type(schema) is dict:
        pass
    elif issubclass(schema, Document):
        schema = schema.get_schema()
    else:
        raise TypeError("%s is not valid type" % type(schema))

    return pjo.ObjectBuilder(schema).build_classes()


def get_domain_zone(domain):
    return domain.split('.')[-1]
