# -*- coding: utf-8 -*-

import json
import unittest

from datetime import datetime

try:
    from io import BytesIO
except TypeError:
    from StringIO import StringIO as BytesIO  # NOQA

import requests

from mock import Mock, patch

import cosm
import cosm.api


class RequestsFixtureMixin(object):
    """Mixin to mock request.Session.request from the cosm module."""

    def setUp(self, *args, **kwargs):
        """Installs our own request handler."""
        patcher = patch('cosm.Session.request')
        self.session = patcher.start()
    setUp.__test__ = False  # Don't test this method.

    def tearDown(self, *args, **kwargs):
        """Ensures the original request object is reinstated."""
        self.session.stop()
    tearDown.__test__ = False  # Don't test this method.

    def request(self, *args, **kwargs):
        """Returns a new mock object by default. Override in implementors."""
        return Mock()


class BaseTestCase(RequestsFixtureMixin, unittest.TestCase):
    """Common base class for Cosm api tests."""

    def _create_feed(self, **data):
        feed = cosm.Feed(**data)
        feed._manager = cosm.api.FeedsManager(self.client)
        if 'id' in data and 'feed' not in data:
            feed_url = 'http://api.cosm.com/v2/feeds/{}'.format(data['id'])
            feed._data['feed'] = feed_url
        return feed

    def _create_datastream(self, **data):
        datastream = cosm.Datastream(**data)
        datastream._manager = cosm.api.DatastreamsManager(self.feed)
        return datastream

    def _create_datapoint(self, **data):
        datapoint = cosm.Datapoint(**data)
        manager = cosm.api.DatapointsManager(self.datastream)
        datapoint._manager = manager
        return datapoint


class KeyAuthTest(unittest.TestCase):
    """
    Key based authentication tests.
    """

    def test_api_key_header(self):
        """Tests the X-ApiKey header is set on requests using KeyAuth."""
        request = requests.Request()
        auth = cosm.KeyAuth("ABCDE")
        auth(request)
        self.assertEqual(request.headers['X-ApiKey'], "ABCDE")


class ClientTest(BaseTestCase):
    """
    Low level Cosm Client tests.
    """

    def setUp(self):
        super(ClientTest, self).setUp()
        self.client = cosm.Client("API_KEY")

    def test_create(self):
        """Tests that we can create a client object."""
        cosm.Client("ABCDE")

    def test_request_relative_url(self):
        """Tests relative urls are requested with absolute url."""
        client = cosm.Client("API_KEY")
        client.request('GET', "/v2/feeds")
        self.session.assert_called_with('GET', "http://api.cosm.com/v2/feeds")

    def test_request_absolute_url(self):
        """Tests absolute urls are requested for a different host."""
        client = cosm.Client("API_KEY")
        client.request('GET', "http://example.com")
        self.session.assert_called_with('GET', "http://example.com")

    def test_serialise_data(self):
        """Tests data is serialised using __getstate__ when requested."""
        class TestObject:
            def __getstate__(self):
                return self.__dict__
        obj = TestObject()
        obj.title = "This is an object"
        obj.value = 42
        client = cosm.Client("API_KEY")
        client.request('POST', "/v2/feeds", data=obj)
        self.session.assert_called_with(
            'POST', "http://api.cosm.com/v2/feeds",
            data=json.dumps({"value": 42, "title": "This is an object"}))


class FeedTest(BaseTestCase):

    def setUp(self):
        super(FeedTest, self).setUp()
        self.client = cosm.Client("API_KEY")
        self.api = cosm.api.Client("API_KEY")

    def test_create_feed(self):
        feed = cosm.Feed(title="Feed Test")
        self.client.post('/v2/feeds', data=feed)
        self.session.assert_called_with(
            'POST', 'http://api.cosm.com/v2/feeds',
            data='{"title": "Feed Test"}')

    def test_update_feed(self):
        feed = self._create_feed(id='123', title="Office")
        feed.private = True
        feed.update()
        self.assertEqual(self.session.call_args[0],
                         ('PUT', 'http://api.cosm.com/v2/feeds/123'))
        payload = json.loads(self.session.call_args[1]['data'])
        self.assertEqual(payload['private'], True)

    def test_delete_feed(self):
        feed = self._create_feed(id='456', title="Home")
        feed.delete()
        self.session.assert_called_with(
            'DELETE', 'http://api.cosm.com/v2/feeds/456')


class FeedsManagerTest(BaseTestCase):

    def setUp(self):
        super(FeedsManagerTest, self).setUp()
        self.api = cosm.api.Client("API_KEY")

    def test_create_feed(self):
        """Tests a request is sent to create a feed."""
        response = requests.Response()
        response.status_code = 201
        response.headers['location'] = "http://cosm.api.com/v2/feeds/51"
        self.session.return_value = response
        feed = self.api.feeds.create(title="Area 51")
        self.assertEqual(feed.feed, "http://cosm.api.com/v2/feeds/51")

    def test_update_feed(self):
        """Tests a request is sent to update a feed."""
        response = requests.Response()
        response.status_code = 200
        self.session.return_value = response
        self.api.feeds.update(51, private=True)
        self.session.assert_called_with(
            'PUT', 'http://api.cosm.com/v2/feeds/51',
            data='{"private": true}')

    def test_list_feeds(self):
        """Tests a request is sent to list all feeds."""
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(LIST_FEEDS_JSON)
        self.session.return_value = response
        (feed,) = self.api.feeds.list()
        self.assertEqual(self.session.call_args[0],
                         ('GET', u'http://api.cosm.com/v2/feeds'))
        self.assertEqual(feed.feed, u'http://api.cosm.com/v2/feeds/5853.json')

    def test_view_feed(self):
        """Tests a request is sent to view a feed (by id) returning json."""
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(GET_FEED_JSON)
        self.session.return_value = response
        feed = self.api.feeds.get(7021)
        self.assertEqual(self.session.call_args[0],
                         ('GET', 'http://api.cosm.com/v2/feeds/7021'))
        self.assertEqual(feed.title, "Cosm Office environment")

    def test_get_feeds_with_datastream_history(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(HISTORY_FEED_JSON)
        self.session.return_value = response
        feed = self.api.feeds.get(61916,
                                  start=datetime(2013, 1, 1, 14, 0, 0),
                                  end=datetime(2013, 1, 1, 16, 0, 0),
                                  interval=900)
        self.session.assert_called_with(
            'GET', 'http://api.cosm.com/v2/feeds/61916',
            allow_redirects=True, params={
                'start': '2013-01-01T14:00:00Z',
                'end': '2013-01-01T16:00:00Z',
                'interval': 900,
            })
        self.assertEqual(feed.id, 61916)
        self.assertEqual(feed.datastreams[0].id, "random5")
        self.assertEqual(feed.datastreams[0].datapoints[2].at,
                         datetime(2013, 1, 1, 14, 44, 55, 111267))
        self.assertEqual(feed.datastreams[0].datapoints[2].value, "0.40271227")

    def test_delete_feed(self):
        """Tests a DELETE request is sent for a feed by its id."""
        response = requests.Response()
        response.status_code = 200
        self.session.return_value = response
        self.api.feeds.delete(7021)
        self.session.assert_called_with(
            'DELETE', 'http://api.cosm.com/v2/feeds/7021')


class DatastreamTest(BaseTestCase):

    def setUp(self):
        super(DatastreamTest, self).setUp()
        self.client = cosm.Client("API_KEY")
        self.feed = self._create_feed(id=7021, title="Rother")

    def test_create_datastream(self):
        datastream = cosm.Datastream(id="energy")
        self.assertEqual(datastream.id, "energy")

    def test_update_datastream(self):
        datastream = self._create_datastream(id="energy", current_value=211)
        datastream.current_value = 294
        datastream.update()
        self.assertEqual(
            self.session.call_args[0],
            ('PUT', 'http://api.cosm.com/v2/feeds/7021/datastreams/energy'))
        payload = json.loads(self.session.call_args[1]['data'])
        self.assertEqual(payload['current_value'], 294)

    def test_delete_datastream(self):
        datastream = self._create_datastream(id="energy")
        datastream.delete()
        self.session.assert_called_with(
            'DELETE', 'http://api.cosm.com/v2/feeds/7021/datastreams/energy')


class DatastreamsManagerTest(BaseTestCase):

    def setUp(self):
        super(DatastreamsManagerTest, self).setUp()
        self.client = cosm.Client("API_KEY")
        self.feed = self._create_feed(id=7021, title="Rother")

    def test_create_datastream(self):
        datastream = self.feed.datastreams.create(
            id="flow", current_value=34000)
        self.assertEqual(
            self.session.call_args[0],
            ('POST', 'http://api.cosm.com/v2/feeds/7021/datastreams'))
        self.assertEqual(datastream.id, "flow")
        self.assertEqual(datastream.current_value, 34000)

    def test_update_datastream(self):
        self.feed.datastreams.update('energy', current_value=294)
        self.assertEqual(
            self.session.call_args[0],
            ('PUT', 'http://api.cosm.com/v2/feeds/7021/datastreams/energy'))
        payload = json.loads(self.session.call_args[1]['data'])
        self.assertEqual(payload['current_value'], 294)

    def test_list_datastreams(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(GET_FEED_JSON)
        self.session.return_value = response
        datastreams = self.feed.datastreams.list()
        self.assertEqual([d.id for d in datastreams], ["3", "4"])
        # Note that this url isnt' at .../datastreams
        self.session.assert_called_with(
            'GET', 'http://api.cosm.com/v2/feeds/7021/',
            allow_redirects=True, params={})

    def test_view_datastream(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(GET_DATASTREAM_JSON)
        self.session.return_value = response
        datastream = self.feed.datastreams.get('1')
        self.assertEqual(datastream.id, '1')
        self.session.assert_called_with(
            'GET', 'http://api.cosm.com/v2/feeds/7021/datastreams/1',
            allow_redirects=True, params={})

    def test_get_datastream_with_history(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(HISTORY_DATASTREAM_JSON)
        self.session.return_value = response
        datastream = self.feed.datastreams.get(
            'random5',
            start=datetime(2013, 1, 1, 14, 0, 0),
            end=datetime(2013, 1, 1, 16, 0, 0),
            interval=900)
        self.session.assert_called_with(
            'GET', 'http://api.cosm.com/v2/feeds/7021/datastreams/random5',
            allow_redirects=True, params={
                'start': '2013-01-01T14:00:00Z',
                'end': '2013-01-01T16:00:00Z',
                'interval': 900,
            })
        self.assertEqual(datastream.id, 'random5')
        self.assertEqual(datastream.datapoints[0].at,
                         datetime(2013, 1, 1, 14, 14, 55, 118845))
        self.assertEqual(datastream.datapoints[0].value, "0.25741970")

    def test_delete_datastream(self):
        self.feed.datastreams.delete("energy")
        self.session.assert_called_with(
            'DELETE', 'http://api.cosm.com/v2/feeds/7021/datastreams/energy')


class DatapointTest(BaseTestCase):

    def setUp(self):
        super(DatapointTest, self).setUp()
        self.client = cosm.Client("API_KEY")
        self.feed = self._create_feed(id=1977, title="Rother")
        self.datastream = self._create_datastream(id='1', current_value="100")

    def test_create_datapoint(self):
        now = datetime.now()
        datapoint = cosm.Datapoint(at=now, value=123)
        self.assertEqual(datapoint.at, now)
        self.assertEqual(datapoint.value, 123)

    def test_update_datapoint(self):
        datapoint = self._create_datapoint(
            at=datetime(2010, 7, 28, 7, 48, 22, 14326), value="296")
        datapoint.value = "297"
        datapoint.update()
        self.session.assert_called_with(
            'PUT',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints/'
            '2010-07-28T07:48:22.014326Z',
            data='{"value": "297"}')

    def test_delete_datapoint(self):
        datapoint = self._create_datapoint(
            at=datetime(2010, 7, 28, 7, 48, 22, 14326), value="297")
        datapoint.delete()
        self.session.assert_called_with(
            'DELETE',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints/'
            '2010-07-28T07:48:22.014326Z',
            params={})


class DatapointsManagerTest(BaseTestCase):

    def setUp(self):
        super(DatapointsManagerTest, self).setUp()
        self.client = cosm.Client("API_KEY")
        self.feed = self._create_feed(id=1977, title="Rother")
        self.datastream = self._create_datastream(id='1', current_value="100")

    def test_create_datapoint(self):
        datapoints = self.datastream.datapoints.create([
            {'at': datetime(2010, 5, 20, 11, 1, 43), 'value': "294"},
            {'at': datetime(2010, 5, 20, 11, 1, 44), 'value': "295"},
            {'at': datetime(2010, 5, 20, 11, 1, 45), 'value': "296"},
            {'at': datetime(2010, 5, 20, 11, 1, 46), 'value': "297"},
        ])
        self.session.assert_called_with(
            'POST',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints',
            data=json.dumps(json.loads(CREATE_DATAPOINTS_JSON.decode('utf8'))))
        self.assertEqual(datapoints[0].at, datetime(2010, 5, 20, 11, 1, 43))
        self.assertEqual(datapoints[0].value, "294")
        self.assertEqual(datapoints[1].at, datetime(2010, 5, 20, 11, 1, 44))
        self.assertEqual(datapoints[1].value, "295")
        self.assertEqual(datapoints[2].at, datetime(2010, 5, 20, 11, 1, 45))
        self.assertEqual(datapoints[2].value, "296")
        self.assertEqual(datapoints[3].at, datetime(2010, 5, 20, 11, 1, 46))
        self.assertEqual(datapoints[3].value, "297")

    def test_update_datapoint(self):
        self.datastream.datapoints.update(
            datetime(2010, 7, 28, 7, 48, 22, 14326), value="297")
        self.session.assert_called_with(
            'PUT',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints/'
            '2010-07-28T07:48:22.014326Z',
            data='{"value": "297"}')

    def test_datapoint_history(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(HISTORY_DATASTREAM_JSON)
        self.session.return_value = response
        datapoints = list(self.datastream.datapoints.history(
            start=datetime(2013, 1, 1, 14, 0, 0),
            end=datetime(2013, 1, 1, 16, 0, 0),
            interval=900))
        self.session.assert_called_with(
            'GET', 'http://api.cosm.com/v2/feeds/1977/datastreams/1',
            allow_redirects=True, params={
                'start': '2013-01-01T14:00:00Z',
                'end': '2013-01-01T16:00:00Z',
                'interval': 900,
            })
        self.assertEqual(datapoints[0].at,
                         datetime(2013, 1, 1, 14, 14, 55, 118845))
        self.assertEqual(datapoints[0].value, "0.25741970")

    def test_view_datapoint(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(GET_DATAPOINT_JSON)
        self.session.return_value = response
        at = datetime(2010, 7, 28, 7, 48, 22, 14326)
        datapoint = self.datastream.datapoints.get(at)
        self.assertEqual(datapoint.at, at)
        self.assertEqual(datapoint.value, "297")
        self.session.assert_called_with(
            'GET',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints/'
            '2010-07-28T07:48:22.014326Z',
            allow_redirects=True)

    def test_delete_datapoint(self):
        at = datetime(2010, 7, 28, 7, 48, 22, 14326)
        self.datastream.datapoints.delete(at)
        self.session.assert_called_with(
            'DELETE',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints/'
            '2010-07-28T07:48:22.014326Z',
            params={})

    def test_delete_multiple_datapoints(self):
        self.datastream.datapoints.delete(
            start=datetime(2010, 7, 28, 7, 48, 22, 14326))
        self.session.assert_called_with(
            'DELETE',
            'http://api.cosm.com/v2/feeds/1977/datastreams/1/datapoints',
            params={'start': '2010-07-28T07:48:22.014326Z'})


class TriggerTest(BaseTestCase):

    def setUp(self):
        super(TriggerTest, self).setUp()
        self.client = cosm.Client("API_KEY")
        self.api = cosm.api.Client("API_KEY")
        self.feed = self._create_feed(id=8470, title="Dave")
        self.datastream = self._create_datastream(id="0")

    def test_create_trigger(self):
        trigger = cosm.Trigger(
            self.feed.id, self.datastream.id,
            url="http://www.postbin.org/1ijyltn",
            trigger_type="lt",
            threshold_value="15.0")
        self.client.post('/v2/triggers', data=trigger)
        self.session.assert_called_with(
            'POST', 'http://api.cosm.com/v2/triggers',
            data=json.dumps({
                'environment_id': 8470,
                'stream_id': "0",
                'url': "http://www.postbin.org/1ijyltn",
                'trigger_type': 'lt',
                'threshold_value': "15.0",
            }))


class TriggerManagerTest(BaseTestCase):

    def setUp(self):
        super(TriggerManagerTest, self).setUp()
        self.api = cosm.api.Client("API_KEY")

    def test_create_trigger(self):
        response = requests.Response()
        response.status_code = 201
        response.headers['location'] = "http://cosm.api.com/v2/triggers/14"
        self.session.return_value = response
        trigger = self.api.triggers.create(
            8470, "0", url="http://www.postbin.org/1ijyltn",
            trigger_type='lt', threshold_value="15.0")
        self.session.assert_called_with(
            'POST', 'http://api.cosm.com/v2/triggers',
            data=json.dumps({
                'environment_id': 8470,
                'stream_id': "0",
                'url': "http://www.postbin.org/1ijyltn",
                'trigger_type': 'lt',
                'threshold_value': "15.0",
            }))
        self.assertEqual(trigger.id, 14)

    def test_view_trigger(self):
        response = requests.Response()
        response.status_code = 200
        response.raw = BytesIO(GET_TRIGGER_JSON)
        self.session.return_value = response
        trigger = self.api.triggers.get(14)
        self.session.assert_called_with(
            'GET', 'http://api.cosm.com/v2/triggers/14', allow_redirects=True)
        self.assertEqual(trigger._data, {
            'id': 14,
            'environment_id': 8470,
            'stream_id': "0",
            'user': 'cosm',
            'url': "http://www.postbin.org/1ijyltn",
            'trigger_type': "lt",
            'threshold_value': "15.0",
        })


# Data used to return in the responses.

GET_FEED_JSON = b'''
{
"description" : "test of manual feed snapshotting",
"feed" : "http://api.cosm.com/v2/feeds/504.json",
"id" : 7021,
"status" : "frozen",
"title" : "Cosm Office environment",
"website":"http://www.haque.co.uk/",
"updated" : "2010-06-25T11:54:17.463771Z",
"created" : "2010-05-03T23:43:01.238734Z",
"version" : "1.0.0",
"creator" : "https://cosm.com/users/hdr",
"tags":[
    "Tag1",
    "Tag2"
],
"location":
{
  "disposition":"fixed",
  "ele":"23.0",
  "name":"office",
  "lat":51.5235375648154,
  "exposure":"indoor",
  "lon":-0.0807666778564453,
  "domain":"physical"
},
"datastreams" : [ {
  "at" : "2010-06-25T11:54:17.454020Z",
  "current_value" : "999",
  "id" : "3",
  "max_value" : "999.0",
  "min_value" : "7.0"
  },
  {
  "at" : "2010-06-24T10:05:49.000000Z",
  "current_value" : "0000017",
  "id" : "4",
  "max_value" : "19.0",
  "min_value" : "7.0"
  } ]
}
'''

LIST_FEEDS_JSON = b'''
{
  "totalResults":4299,
  "results":[
    {
      "feed":"http://api.cosm.com/v2/feeds/5853.json",
      "title":"bridge19",
      "status":"live",
      "version":"1.0.0",
      "creator":"me",
      "url":"https://cosm.com/users/hdr",
      "updated":"2010-06-08T09:30:21.472927Z",
      "created":"2010-05-03T23:43:01.238734Z",
      "location":{"domain":"physical"},
      "tags":[
          "Tag1",
          "Tag2"
      ],
      "datastreams":[
        {
          "max_value":"10000.0",
          "tags":["humidity"],
          "current_value":"435",
          "min_value":"-10.0",
          "at":"2010-07-02T10:21:57.101496Z",
          "id":"0"
        },
        {
          "max_value":"10000.0",
          "tags":["humidity"],
          "current_value":"herz",
          "min_value":"-10.0",
          "at":"2010-07-02T10:21:57.176209Z",
          "id":"1"
        }
      ]
    }
  ]
}
'''

GET_DATASTREAM_JSON = b'''
{
  "current_value":"100",
  "max_value":"10000.0",
  "at":"2010-07-02T10:16:19.270708Z",
  "min_value":"-10.0",
  "tags":[
    "humidity"
  ],
  "id":"1"
}
'''

CREATE_DATAPOINTS_JSON = b'''
{
  "datapoints":[
    {"at":"2010-05-20T11:01:43Z","value":"294"},
    {"at":"2010-05-20T11:01:44Z","value":"295"},
    {"at":"2010-05-20T11:01:45Z","value":"296"},
    {"at":"2010-05-20T11:01:46Z","value":"297"}
  ]
}
'''

GET_DATAPOINT_JSON = b'''
{
  "value":"297",
  "at":"2010-07-28T07:48:22.014326Z"
}
'''

HISTORY_DATASTREAM_JSON = b'''
{
  "max_value": "1.0",
  "current_value": "0.00334173",
  "min_value": "0.0",
  "at": "2013-01-04T10:30:00.119435Z",
  "version": "1.0.0",
  "datapoints": [
    {
      "value": "0.25741970",
      "at": "2013-01-01T14:14:55.118845Z"
    },
    {
      "value": "0.86826886",
      "at": "2013-01-01T14:29:55.123420Z"
    },
    {
      "value": "0.28586252",
      "at": "2013-01-01T14:44:55.111267Z"
    },
    {
      "value": "0.48122377",
      "at": "2013-01-01T14:59:55.126180Z"
    },
    {
      "value": "0.60897230",
      "at": "2013-01-01T15:14:55.121795Z"
    },
    {
      "value": "0.52898451",
      "at": "2013-01-01T15:29:55.105327Z"
    },
    {
      "value": "0.36369879",
      "at": "2013-01-01T15:44:55.115502Z"
    },
    {
      "value": "0.54204623",
      "at": "2013-01-01T15:59:55.111692Z"
    }
  ],
  "id": "random5"
}
'''

HISTORY_FEED_JSON = b'''
{
  "status": "live",
  "tags": [
    "data",
    "generated",
    "generator",
    "random",
    "sawtooth",
    "sine",
    "square",
    "test",
    "toggle",
    "triangle",
    "wave"
  ],
  "datastreams": [
    {
      "current_value": "-0.52858234",
      "datapoints": [
        {
          "value": "-0.36438789",
          "at": "2013-01-01T14:14:55.118845Z"
        },
        {
          "value": "-0.92348577",
          "at": "2013-01-01T14:29:55.123420Z"
        },
        {
          "value": "0.40271227",
          "at": "2013-01-01T14:44:55.111267Z"
        },
        {
          "value": "0.90677334",
          "at": "2013-01-01T14:59:55.126180Z"
        },
        {
          "value": "-0.44034308",
          "at": "2013-01-01T15:14:55.121795Z"
        },
        {
          "value": "-0.88850004",
          "at": "2013-01-01T15:29:55.105327Z"
        }
      ],
      "at": "2013-01-04T10:22:40.111636Z",
      "max_value": "1.0",
      "min_value": "-1.0",
      "id": "random5"
    },
    {
      "current_value": "0.90935832",
      "datapoints": [
        {
          "value": "-0.37776079",
          "at": "2013-01-01T14:14:55.118845Z"
        },
        {
          "value": "-0.99809959",
          "at": "2013-01-01T14:29:55.123420Z"
        },
        {
          "value": "-0.26099779",
          "at": "2013-01-01T14:44:55.111267Z"
        },
        {
          "value": "0.83106759",
          "at": "2013-01-01T14:59:55.126180Z"
        },
        {
          "value": "0.79286010",
          "at": "2013-01-01T15:14:55.121795Z"
        },
        {
          "value": "-0.32355670",
          "at": "2013-01-01T15:29:55.105327Z"
        }
      ],
      "at": "2013-01-04T10:22:40.111636Z",
      "max_value": "1.0",
      "min_value": "-1.0",
      "id": "random60"
    },
    {
      "current_value": "0.79187545",
      "datapoints": [
        {
          "value": "0.99688943",
          "at": "2013-01-01T14:14:55.118845Z"
        },
        {
          "value": "0.99999155",
          "at": "2013-01-01T14:29:55.123420Z"
        },
        {
          "value": "0.99620780",
          "at": "2013-01-01T14:44:55.111267Z"
        },
        {
          "value": "0.98556422",
          "at": "2013-01-01T14:59:55.126180Z"
        },
        {
          "value": "0.96813412",
          "at": "2013-01-01T15:14:55.121795Z"
        },
        {
          "value": "0.94403985",
          "at": "2013-01-01T15:29:55.105327Z"
        },
        {
          "value": "0.91341442",
          "at": "2013-01-01T15:44:55.115502Z"
        }
      ],
      "at": "2013-01-04T10:22:40.111636Z",
      "max_value": "1.0",
      "min_value": "-1.0",
      "id": "random900"
    }
  ],
  "description": "A test feed full of data for testing devices against.",
  "created": "2012-06-01T14:18:51.736718Z",
  "feed": "https://api.cosm.com/v2/feeds/61916.json",
  "title": "Test Data Generator",
  "location": {
    "domain": "physical"
  },
  "version": "1.0.0",
  "private": "false",
  "creator": "https://cosm.com/users/paul",
  "updated": "2013-01-04T10:22:40.342290Z",
  "id": 61916
}
'''

GET_TRIGGER_JSON = b'''
{
  "threshold_value":"15.0",
  "user":"cosm",
  "notified_at":"",
  "url":"http:\/\/www.postbin.org\/1ijyltn",
  "trigger_type":"lt",
  "id":14,
  "environment_id":8470,
  "stream_id":"0"
}
'''
