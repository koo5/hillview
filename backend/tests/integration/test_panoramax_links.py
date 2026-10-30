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

import pytest
import requests

PANORAMAX_URL = os.getenv('PANORAMAX_URL', 'http://localhost:8058')


def test_collections_listing_self_link_keeps_base_and_query():
    response = requests.get(f'{PANORAMAX_URL}/api/collections', params={'limit': 1}, timeout=10)
    assert response.status_code == 200, response.text
    links = {link['rel']: link['href'] for link in response.json()['links']}
    base = links['root'].removesuffix('/api/')
    assert links['self'] == f'{base}/api/collections?limit=1'


def test_root_without_a_served_photo_goes_to_the_viewer():
    for query in ('', '?pic=not-a-uuid', f'?pic={uuid.uuid4()}'):
        response = requests.get(f'{PANORAMAX_URL}/{query}', allow_redirects=False, timeout=10)
        assert response.status_code == 307, (query, response.text)
        assert 'photo=' not in response.headers['location']


def test_root_sends_a_served_photo_to_its_place_on_the_map():
    # The web viewer's "Origin instance" link: the via href plus the explorer's
    # own query string, which carries pic=<item id> and seq=<collection id>.
    page = requests.get(f'{PANORAMAX_URL}/api/collections', params={'limit': 1}, timeout=10).json()
    if not page['collections']:
        pytest.skip('no served collection on this stack')
    seq = page['collections'][0]['id']
    items = requests.get(f'{PANORAMAX_URL}/api/collections/{seq}/items', params={'limit': 1}, timeout=10).json()
    pic = items['features'][0]['id']
    response = requests.get(f'{PANORAMAX_URL}/', params={'focus': 'pic', 'pic': pic, 'seq': seq},
                            allow_redirects=False, timeout=10)
    assert response.status_code == 307
    location = response.headers['location']
    assert f'photo=hillview-{pic}' in location and 'lat=' in location and 'lon=' in location
