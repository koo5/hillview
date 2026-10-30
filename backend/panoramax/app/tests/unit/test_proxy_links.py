"""The proxy strips /geovisio; public links must keep it and the query string."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import httpx
import pytest

import main

BASE = 'https://hillview.example/geovisio'


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['', '?limit=1&filter=status%3D%27ready%27'])
async def test_collections_links_use_canonical_proxy_url(monkeypatch, query):
	monkeypatch.setenv('PANORAMAX_BASE_URL', BASE)
	page = [{'id': 'last-sequence'}] if query else []
	monkeypatch.setattr(main, '_fetch_collections_page', AsyncMock(return_value=page))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://internal:8058') as client:
		response = await client.get('/api/collections' + query)
	assert response.status_code == 200
	links = {link['rel']: link['href'] for link in response.json()['links']}
	assert links['self'] == BASE + '/api/collections' + query
	assert links['root'] == BASE + '/api/'
	if query:
		next_url = httpx.URL(links['next'])
		assert str(next_url).startswith(BASE + '/api/collections?')
		assert next_url.params['filter'] == "status='ready'"
		assert next_url.params['limit'] == '1'
		assert next_url.params['page_after'] == 'last-sequence'


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['', '?limit=2&page_after_rank=3'])
async def test_item_page_self_link_keeps_proxy_prefix_and_query(monkeypatch, query):
	monkeypatch.setenv('PANORAMAX_BASE_URL', BASE)
	seq_id = uuid.UUID('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
	monkeypatch.setattr(main, '_load_sequence', AsyncMock(return_value=(seq_id, 'ready')))
	conn = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
	connection = MagicMock()
	connection.__aenter__ = AsyncMock(return_value=conn)
	monkeypatch.setattr(main, 'get_engine', lambda: SimpleNamespace(connect=lambda: connection))
	path = f'/api/collections/{seq_id}/items'
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://internal:8058') as client:
		response = await client.get(path + query)
	assert response.status_code == 200
	links = {link['rel']: link['href'] for link in response.json()['links']}
	assert links['self'] == BASE + path + query
	assert links['collection'] == BASE + f'/api/collections/{seq_id}'
