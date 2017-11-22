import asyncio
import collections
from inspect import isawaitable, isfunction

from threading import local


class _Local(local):
    def __init__(self):
        # Singleton instances stack
        self.instances = []


class Singleton(type):
    """
    Until called with `_as_context`, it's behave like a normal singleton.

    Calling with `_as_context` allows to maintain instances stack with help of context manager. This is used mostly
    for testing.
    """
    _local = _Local()

    class CTXMG(object):

        def __init__(self, cls, instance):
            self.instance = instance
            self.singleton_cls = cls

        def __enter__(self):
            return self.instance

        def __exit__(self, *args):
            instance = self.singleton_cls._local.instances.pop()
            assert instance is self.instance, self.singleton_cls._local.instances

    def __init__(cls, name, bases, attrs, **kwargs):
        super().__init__(name, bases, attrs)
        cls._instance = None

    def __call__(cls, *args, **kwargs):
        as_context = kwargs.pop('_as_context', False)
        if as_context or not cls._local.instances:
            _instance = super().__call__(*args, **kwargs)
            cls._local.instances.append(_instance)
        else:
            _instance = cls._local.instances[-1]

        if as_context:
            return cls.CTXMG(cls, _instance)
        return _instance


class ImmutableDict(collections.Mapping):
    def __init__(self, somedict):
        self._dict = dict(somedict)  # make a copy
        self._hash = None

    def __getitem__(self, key):
        return self._dict[key]

    def __len__(self):
        return len(self._dict)

    def __iter__(self):
        return iter(self._dict)

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(frozenset(self._dict.items()))
        return self._hash

    def __eq__(self, other):
        return self._dict == other._dict


class LazyProperty(object):
    __slots__ = ['value', 'var_or_callable', 'value_lock']

    def __init__(self, loop, var_or_callable):
        self.var_or_callable = var_or_callable
        self.value_lock = asyncio.Lock(loop=loop)

    async def __call__(self, *args, **kwargs):
        await self.value_lock.acquire()
        try:
            if hasattr(self, 'value'):
                return self.value

            if isfunction(self.var_or_callable):
                self.value = self.var_or_callable()
            else:
                self.value = self.var_or_callable

            if isawaitable(self.value):
                self.value = await self.value
        finally:
            self.value_lock.release()

        return self.value
