"""The Panoramax API's links all hang off its advertised base URL.

Behind a vhost that serves the API under a stripped prefix (the dev boxes'
https://<host>/geovisio), a link built from the incoming request instead loses
the prefix. The harvester follows `next`; `self` is what a client re-fetches.
The request here goes straight to the container, so on a box whose
PANORAMAX_BASE_URL is not PANORAMAX_URL this also catches a link built from
request.url.
"""
import os
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

PANORAMAX_URL = os.getenv('PANORAMAX_URL', 'http://localhost:8058')


def test_collections_listing_self_link_keeps_base_and_query():
    response = requests.get(f'{PANORAMAX_URL}/api/collections', params={'limit': 1}, timeout=10)
    assert response.status_code == 200, response.text
    links = {link['rel']: link['href'] for link in response.json()['links']}
    base = links['root'].removesuffix('/api/')
    assert links['self'] == f'{base}/api/collections?limit=1'


def root_redirect(**params):
    """Where `/` sends the web viewer's "Origin instance" link: (path, query)."""
    response = requests.get(f'{PANORAMAX_URL}/', params=params, allow_redirects=False, timeout=10)
    assert response.status_code == 307, response.text
    location = urlsplit(response.headers['location'])
    return location.path, {k: v[0] for k, v in parse_qs(location.query).items()}


def test_root_without_a_usable_pic():
    assert root_redirect()[1] == {}
    assert root_redirect(pic='not-a-uuid')[1] == {}
    # The explorer's own map position still lands on the same place (MapLibre
    # zoom 17 is Leaflet zoom 18).
    assert root_redirect(pic='not-a-uuid', map='17/50.08/14.42')[1] == {'lat': '50.08', 'lon': '14.42', 'zoom': '18'}


def test_root_passes_an_unserved_photo_to_the_frontend():
    # Positioned only by the explorer's own map parameter: the frontend checks
    # the photo against Hillview's API with the visitor's own access.
    pic = str(uuid.uuid4())
    assert root_redirect(pic=pic)[1] == {'photo': f'hillview-{pic}'}
    assert root_redirect(pic=pic, map='17/50.08/14.42')[1] == \
        {'lat': '50.08', 'lon': '14.42', 'zoom': '18', 'photo': f'hillview-{pic}'}


def test_root_sends_a_served_photo_to_its_place_on_the_map():
    page = requests.get(f'{PANORAMAX_URL}/api/collections', params={'limit': 1}, timeout=10).json()
    if not page['collections']:
        pytest.skip('no served collection on this stack')
    seq = page['collections'][0]['id']
    items = requests.get(f'{PANORAMAX_URL}/api/collections/{seq}/items', params={'limit': 1}, timeout=10).json()
    pic = items['features'][0]['id']

    # The map at the photo's own position, the photo selected, whatever the
    # explorer's focus (the link always says focus=pic).
    path, query = root_redirect(focus='pic', pic=pic, seq=seq, map='3/0/0')
    assert query['photo'] == f'hillview-{pic}' and query['zoom'] == '18'
    assert 'lat' in query and 'lon' in query
    assert query['lat'] != '0'  # the photo's position, not the explorer's map
