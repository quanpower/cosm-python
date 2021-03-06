# -*- coding: utf-8 -*-

__title__ = 'cosm-python'
__version__ = '0.1.0'

import json

from datetime import datetime

try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin  # NOQA

from requests.sessions import Session

from requests.auth import AuthBase


class KeyAuth(AuthBase):
    """Attaches HTTP API Key Authentication to the given Request object."""
    def __init__(self, key):
        self.key = key

    def __call__(self, r):
        # modify and return the request
        r.headers['X-ApiKey'] = self.key
        return r


class Client(Session):
    """A Cosm API Client object.

    This is instantiated with an API key which is used for all requests to the
    Cosm API.  It also defines a BASE_URL so that we can specify relative urls
    when using the client (all requests via this client are going to Cosm).

    """
    BASE_URL = "http://api.cosm.com"

    def __init__(self, key):
        super(Client, self).__init__()
        self.auth = KeyAuth(key)
        self.base_url = self.BASE_URL
        self.headers['Content-Type'] = 'application/json'
        self.headers['User-Agent'] = 'cosm-python/{} {}'.format(
            __version__, self.headers['User-Agent'])

    def request(self, method, url, *args, **kwargs):
        """Constructs and sends a Request to the Cosm API.

        Objects that implement __getstate__  will be serialised.

        """
        full_url = urljoin(self.base_url, url)
        if 'data' in kwargs:
            kwargs['data'] = self._encode_data(kwargs['data'])
        return super(Client, self).request(method, full_url, *args, **kwargs)

    def _encode_data(self, data, **kwargs):
        """Returns data encoded as JSON using a custom encoder.

        >>> client = Client("XXXXXX")
        >>> client._encode_data({'foo': datetime(2013, 2, 22, 12, 14, 40)})
        '{"foo": "2013-02-22T12:14:40Z"}'
        >>> feed = Feed(id=42, title="The Answer")
        >>> client._encode_data({'feed': feed}, sort_keys=True)
        '{"feed": {"id": 42, "title": "The Answer"}}'
        >>> datastreams = [Datastream(id="1"), Datastream(id="2")]
        >>> client._encode_data({'datastreams': datastreams})
        '{"datastreams": [{"id": "1"}, {"id": "2"}]}'
        """
        return json.dumps(data, cls=JSONEncoder, **kwargs)


class Base(object):
    """Abstract base class to store API data and allow (de)serialisation."""

    def __init__(self):
        self._data = {}

    def __getstate__(self):
        return dict(**self._data)

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            class_name = self.__class__.__name__
            raise AttributeError(
                "'{}' object has no attribute '{}'".format(class_name, name))

    def __setattr__(self, name, value):
        if not name.startswith('_') and name not in dir(self.__class__):
            self._data[name] = value
        else:
            super(Base, self).__setattr__(name, value)


class Feed(Base):
    """Cosm Feed, which can contain a number of Datastreams."""

    _datastreams = None

    def __init__(self, title, **kwargs):
        super(Feed, self).__init__()
        self._data['title'] = title
        if 'datastreams' in kwargs:
            self.datastreams = kwargs.pop('datastreams')
        self._data.update(kwargs)

    @property
    def datastreams(self):
        if self._datastreams is None:
            import cosm.api
            self._datastreams = cosm.api.DatastreamsManager(self)
        return self._datastreams

    @datastreams.setter  # NOQA
    def datastreams(self, datastreams):
        manager = getattr(self, '_manager', None)
        if manager:
            manager._coerce_datastreams(self, datastreams)
        self._data['datastreams'] = datastreams

    def update(self):
        self._manager.update(self.feed, **self.__getstate__())

    def delete(self):
        self._manager.delete(self.feed)


class Datastream(Base):
    """Cosm Datastream containing current and historical values."""

    _datapoints = None

    def __init__(self, id, **kwargs):
        super(Datastream, self).__init__()
        self._data['id'] = id
        if 'datapoints' in kwargs:
            self.datapoints = kwargs.pop('datapoints')
        self._data.update(**kwargs)

    @property
    def datapoints(self):
        if self._datapoints is None:
            import cosm.api
            self._datapoints = cosm.api.DatapointsManager(self)
        return self._datapoints

    @datapoints.setter  # NOQA
    def datapoints(self, datapoints):
        self._data['datapoints'] = datapoints

    def update(self):
        state = self.__getstate__()
        self._manager.update(self.id, **state)

    def delete(self):
        self._manager.delete(self.id)


class Datapoint(Base):
    """A Datapoint represents a value at a certain point in time."""

    def __init__(self, at, value):
        super(Datapoint, self).__init__()
        self._data['at'] = at
        self._data['value'] = value

    def update(self):
        state = self.__getstate__()
        self._manager.update(state.pop('at'), **state)

    def delete(self):
        self._manager.delete(self.at)


class Trigger(Base):
    """Triggers provide 'push' capabilities (aka notifications)."""

    def __init__(self, environment_id, stream_id, url, trigger_type,
                 threshold_value=None):
        self._data = {
            'environment_id': environment_id,
            'stream_id': stream_id,
            'url': url,
            'trigger_type': trigger_type,
        }
        if threshold_value is not None:
            self._data['threshold_value'] = threshold_value


class JSONEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z'
        elif hasattr(obj, '__getstate__'):
            return obj.__getstate__()
        else:
            return json.JSONEncoder.default(self, obj)
