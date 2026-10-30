"""The Panoramax API's links all hang off its advertised base URL.

Behind a vhost that serves the API under a stripped prefix (the dev boxes'
https://<host>/geovisio), a link built from the incoming request instead loses
the prefix. The harvester follows `next`; `self` is what a client re-fetches.
The request here goes straight to the container, so on a box whose
PANORAMAX_BASE_URL is not PANORAMAX_URL this also catches a link built from
request.url.
"""
import os

import requests

PANORAMAX_URL = os.getenv('PANORAMAX_URL', 'http://localhost:8058')


def test_collections_listing_self_link_keeps_base_and_query():
    response = requests.get(f'{PANORAMAX_URL}/api/collections', params={'limit': 1}, timeout=10)
    assert response.status_code == 200, response.text
    links = {link['rel']: link['href'] for link in response.json()['links']}
    base = links['root'].removesuffix('/api/')
    assert links['self'] == f'{base}/api/collections?limit=1'
