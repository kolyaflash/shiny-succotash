from python_jsonschema_objects.validators import ValidationError

__all__ = ['ValidationError', 'ImproperlyConfigured']


class ImproperlyConfigured(Exception):
    pass
