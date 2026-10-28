"""Only moderators can change contribution eligibility, with a durable audit."""
import json
import os
import subprocess

import requests

from utils.base_test import BaseAuthTest
from utils.test_utils import API_URL


class TestPanoramaxContributor(BaseAuthTest):
    def test_moderator_toggle_records_old_and_new_values(self):
        owner = requests.get(f'{API_URL}/auth/me', headers=self.test_headers).json()
        user_id = owner['id']
        url = f'{API_URL}/admin/users/{user_id}/panoramax-contributor'
        moderator = self.get_auth_headers(self.get_test_token('moderator'))
        payload = {'panoramax_contributor': False, 'reason': 'contribution test'}
        denied = requests.put(url, json=payload, headers=self.test_headers)
        self.assert_forbidden(denied)
        try:
            changed = requests.put(url, json=payload, headers=moderator)
            self.assert_success(changed)
            assert changed.json()['panoramax_contributor'] is False
            repeated = requests.put(url, json=payload, headers=moderator)
            self.assert_success(repeated)
            # Inspect the durable audit rather than relying on the activity feed's summary.
            query = """
                SELECT json_build_object('old', old_panoramax_contributor,
                    'new', new_panoramax_contributor, 'actor', actor_role, 'reason', reason)
                FROM user_moderation WHERE target_user_id = :'target'
                    AND action = 'panoramax_contributor' ORDER BY created_at DESC LIMIT 1;
            """
            result = subprocess.run(['docker', 'exec', '-i', 'hillview_postgres', 'psql',
                '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview'),
                '-tA', '-v', 'ON_ERROR_STOP=1', '-v', f'target={user_id}'],
                input=query, text=True, capture_output=True)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == {
                'old': True, 'new': False, 'actor': 'moderator', 'reason': 'contribution test',
            }
        finally:
            restored = requests.put(url, json={'panoramax_contributor': True}, headers=moderator)
            self.assert_success(restored)
