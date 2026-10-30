"""/dev/suspicious renders against the live Panoramax service when DEV_MODE is on."""
import os

import pytest
import requests

PANORAMAX_URL = os.getenv('PANORAMAX_URL', 'http://localhost:8058')


def test_dev_report_renders():
    response = requests.get(f'{PANORAMAX_URL}/dev/suspicious', timeout=60)
    if response.status_code == 404:
        pytest.skip('DEV_MODE is off on this stack')
    assert response.status_code == 200, response.text
    assert 'data-testid="suspicious-photos"' in response.text
    assert 'data-testid="suspicious-sequences"' in response.text
