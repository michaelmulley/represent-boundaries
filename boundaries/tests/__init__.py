# coding: utf-8
from __future__ import unicode_literals

import json
import re
from copy import deepcopy

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase
from django.utils.six import assertRegex, text_type
from django.utils.six.moves.urllib.parse import parse_qsl, unquote_plus, urlparse

from boundaries.models import app_settings, Boundary

jsonp_re = re.compile(r'\AabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890_\((.+)\);\Z', re.DOTALL)
pretty_re = re.compile(r'\n    ')


class ViewTestCase(TestCase):
    non_integers = ('', '1.0', '0b1', '0o1', '0x1')  # '01' is okay

    def assertResponse(self, response, content_type='application/json; charset=utf-8'):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], content_type)
        if app_settings.ALLOW_ORIGIN and 'application/json' in response['Content-Type']:
            self.assertEqual(response['Access-Control-Allow-Origin'], '*')
        else:
            self.assertNotIn('Access-Control-Allow-Origin', response)

    def assertNotFound(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertIn(response['Content-Type'], ('text/html', 'text/html; charset=utf-8'))  # different versions of Django
        self.assertNotIn('Access-Control-Allow-Origin', response)

    def assertError(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertNotIn('Access-Control-Allow-Origin', response)

    def assertForbidden(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertNotIn('Access-Control-Allow-Origin', response)

    def assertJSONEqual(self, actual, expected):
        if isinstance(actual, text_type):
            actual = json.loads(actual)
        else:  # It's a response.
            actual = json.loads(actual.content.decode('utf-8'))
        if isinstance(expected, text_type):
            expected = json.loads(expected)
        self.assertEqual(comparable(actual), comparable(expected))


class URL(object):

    """
    http://stackoverflow.com/questions/5371992/comparing-two-urls-in-python
    """

    def __init__(self, url):
        if isinstance(url, text_type):
            parsed = urlparse(url)
            self.parsed = parsed._replace(query=frozenset(parse_qsl(parsed.query)), path=unquote_plus(parsed.path))
        else:  # It's already a URL.
            self.parsed = url.parsed

    def __eq__(self, other):
        return self.parsed == other.parsed

    def __hash__(self):
        return hash(self.parsed)


def comparable(o):
    """
    The order of URL query parameters may differ, so make URLs into URL objects,
    which ignore query parameter ordering.
    """

    if isinstance(o, dict):
        for k, v in o.items():
            if k.endswith('url'):
                o[k] = URL(v)
            else:
                o[k] = comparable(v)
    elif isinstance(o, list):
        o = [comparable(v) for v in o]
    return o


class ViewsTests(object):

    def test_get(self):
        response = self.client.get(self.url)
        self.assertResponse(response)
        self.assertJSONEqual(response, self.json)

    def test_allow_origin(self):
        app_settings.ALLOW_ORIGIN, _ = None, app_settings.ALLOW_ORIGIN

        response = self.client.get(self.url)
        self.assertResponse(response)
        self.assertJSONEqual(response, self.json)

        app_settings.ALLOW_ORIGIN = _

    def test_jsonp(self):
        response = self.client.get(self.url, {'callback': 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890`~!@#$%^&*()-_=+[{]}\\|;:\'",<.>/?'})
        self.assertResponse(response)
        content = response.content.decode('utf-8')
        self.assertJSONEqual(content[64:-2], self.json)
        assertRegex(self, content, jsonp_re)

    def test_apibrowser(self):
        response = self.client.get(self.url, {'format': 'apibrowser'})
        self.assertResponse(response, content_type='text/html; charset=utf-8')


class PrettyTests(object):

    def test_pretty(self):
        response = self.client.get(self.url, {'pretty': 1})
        self.assertResponse(response)
        self.assertJSONEqual(response, self.json)
        assertRegex(self, response.content.decode('utf-8'), pretty_re)

    def test_jsonp_and_pretty(self):
        response = self.client.get(self.url, {'callback': 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890`~!@#$%^&*()-_=+[{]}\\|;:\'",<.>/?', 'pretty': 1})
        self.assertResponse(response)
        content = response.content.decode('utf-8')
        self.assertJSONEqual(content[64:-2], self.json)
        assertRegex(self, content, jsonp_re)
        assertRegex(self, response.content.decode('utf-8'), pretty_re)


class PaginationTests(object):

    def test_limit_is_set(self):
        response = self.client.get(self.url, {'limit': 10})
        self.assertResponse(response)
        data = deepcopy(self.json)
        data['meta']['limit'] = 10
        self.assertJSONEqual(response, data)

    def test_offset_is_set(self):
        response = self.client.get(self.url, {'offset': 10})
        self.assertResponse(response)
        data = deepcopy(self.json)
        data['meta']['offset'] = 10
        self.assertJSONEqual(response, data)

    def test_limit_is_set_to_maximum_if_zero(self):
        response = self.client.get(self.url, {'limit': 0})
        self.assertResponse(response)
        data = deepcopy(self.json)
        data['meta']['limit'] = 1000
        self.assertJSONEqual(response, data)

    def test_limit_is_set_to_maximum_if_greater_than_maximum(self):
        response = self.client.get(self.url, {'limit': 2000})
        self.assertResponse(response)
        data = deepcopy(self.json)
        data['meta']['limit'] = 1000
        self.assertJSONEqual(response, data)

    def test_api_limit_per_page(self):
        settings.API_LIMIT_PER_PAGE, _ = 1, getattr(settings, 'API_LIMIT_PER_PAGE', 20)

        response = self.client.get(self.url)
        self.assertResponse(response)
        data = deepcopy(self.json)
        data['meta']['limit'] = 1
        self.assertJSONEqual(response, data)

        settings.API_LIMIT_PER_PAGE = _

    def test_limit_must_be_an_integer(self):
        for value in self.non_integers:
            response = self.client.get(self.url, {'limit': value})
            self.assertError(response)
            self.assertEqual(response.content, ("Invalid limit '%s' provided. Please provide a positive integer." % value).encode('ascii'))

    def test_offset_must_be_an_integer(self):
        for value in self.non_integers:
            response = self.client.get(self.url, {'offset': value})
            self.assertError(response)
            self.assertEqual(response.content, ("Invalid offset '%s' provided. Please provide a positive integer." % value).encode('ascii'))

    def test_limit_must_be_non_negative(self):
        response = self.client.get(self.url, {'limit': -1})
        self.assertError(response)
        self.assertEqual(response.content, b"Invalid limit '-1' provided. Please provide a positive integer >= 0.")

    def test_offset_must_be_non_negative(self):
        response = self.client.get(self.url, {'offset': -1})
        self.assertError(response)
        self.assertEqual(response.content, b"Invalid offset '-1' provided. Please provide a positive integer >= 0.")


class BoundaryListTests(object):

    def test_omits_meta_if_too_many_items_match(self):
        app_settings.MAX_GEO_LIST_RESULTS, _ = 0, app_settings.MAX_GEO_LIST_RESULTS

        Boundary.objects.create(slug='foo', set_id='inc', shape=MultiPolygon(()), simple_shape=MultiPolygon(()))

        response = self.client.get(self.url)
        self.assertResponse(response)
        self.assertJSONEqual(response, '{"objects": [{"url": "/boundaries/inc/foo/", "boundary_set_name": "", "external_id": "", "name": "", "related": {"boundary_set_url": "/boundary-sets/inc/"}}], "meta": {"next": null, "total_count": 1, "previous": null, "limit": 20, "offset": 0}}')

        app_settings.MAX_GEO_LIST_RESULTS = _


class GeoListTests(object):

    def test_must_not_match_too_many_items(self):
        app_settings.MAX_GEO_LIST_RESULTS, _ = 0, app_settings.MAX_GEO_LIST_RESULTS

        response = self.client.get(self.url)
        self.assertForbidden(response)
        self.assertEqual(response.content, b'Spatial-list queries cannot return more than 0 resources; this query would return 1. Please filter your query.')

        app_settings.MAX_GEO_LIST_RESULTS = _


class GeoTests(object):

    def test_wkt(self):
        response = self.client.get(self.url, {'format': 'wkt'})
        self.assertResponse(response, content_type='text/plain')
        self.assertEqual(response.content, b'MULTIPOLYGON (((0.0000000000000000 0.0000000000000000, 0.0000000000000000 5.0000000000000000, 5.0000000000000000 5.0000000000000000, 0.0000000000000000 0.0000000000000000)))')

    def test_kml(self):
        response = self.client.get(self.url, {'format': 'kml'})
        self.assertResponse(response, content_type='application/vnd.google-earth.kml+xml')
        self.assertEqual(response.content, b'<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n<Placemark><name></name><MultiGeometry><Polygon><outerBoundaryIs><LinearRing><coordinates>0.0,0.0,0 0.0,5.0,0 5.0,5.0,0 0.0,0.0,0</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>\n</Document>\n</kml>')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="shape.kml"')

# For Django < 1.6
from boundaries.tests.test import *
from boundaries.tests.test_boundary import *
from boundaries.tests.test_boundary_detail import *
from boundaries.tests.test_boundary_geo_detail import *
from boundaries.tests.test_boundary_list import *
from boundaries.tests.test_boundary_list_filter import *
from boundaries.tests.test_boundary_list_geo import *
from boundaries.tests.test_boundary_list_geo_filter import *
from boundaries.tests.test_boundary_list_set import *
from boundaries.tests.test_boundary_list_set_filter import *
from boundaries.tests.test_boundary_list_set_geo import *
from boundaries.tests.test_boundary_list_set_geo_filter import *
from boundaries.tests.test_boundary_set import *
from boundaries.tests.test_boundary_set_detail import *
from boundaries.tests.test_boundary_set_list import *
from boundaries.tests.test_boundary_set_list_filter import *
from boundaries.tests.test_compute_intersections import *
from boundaries.tests.test_definition import *
from boundaries.tests.test_feature import *
from boundaries.tests.test_geometry import *
from boundaries.tests.test_loadshapefiles import *
