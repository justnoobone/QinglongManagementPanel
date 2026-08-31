import os
import tempfile
import unittest
from unittest.mock import patch

import app as app_module
import metadata_store
from flask_jwt_extended import decode_token


class ExpiryApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.metadata_patch = patch.object(
            metadata_store, 'METADATA_FILE', os.path.join(self.directory.name, 'metadata.json')
        )
        self.lock_patch = patch.object(
            metadata_store, 'LOCK_FILE', os.path.join(self.directory.name, 'metadata.lock')
        )
        self.metadata_patch.start()
        self.lock_patch.start()
        self.client = app_module.app.test_client()
        response = self.client.post('/api/login', json={'username': 'admin', 'password': 'change-me'})
        self.assertEqual(response.status_code, 200)
        self.headers = {'Authorization': f"Bearer {response.get_json()['token']}"}

    def tearDown(self):
        self.lock_patch.stop()
        self.metadata_patch.stop()
        self.directory.cleanup()

    def test_end_date_can_be_saved_and_read_back(self):
        response = self.client.put(
            '/api/servers/local/instances/0/metadata',
            json={'end_date': '2099-09-02'},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['metadata']['end_date'], '2099-09-02')
        self.assertEqual(metadata_store.load_metadata()['local:0']['end_date'], '2099-09-02')

    def test_login_token_is_valid_for_30_days(self):
        token = self.headers['Authorization'].removeprefix('Bearer ')
        with app_module.app.app_context():
            claims = decode_token(token)

        self.assertEqual(claims['exp'] - claims['iat'], 30 * 24 * 60 * 60)

    def test_invalid_date_is_rejected_without_overwriting_saved_value(self):
        metadata_store.save_metadata({'local:0': {'end_date': '2099-09-02'}})
        response = self.client.put(
            '/api/servers/local/instances/0/metadata',
            json={'end_date': '2099/09/03'},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(metadata_store.load_metadata()['local:0']['end_date'], '2099-09-02')

    def test_expired_instance_cannot_start_or_reset(self):
        metadata_store.save_metadata({'local:0': {'end_date': '2000-01-01'}})
        with patch.object(app_module, 'start_instance') as start, patch.object(app_module, 'reset_instance') as reset:
            start_response = self.client.post('/api/servers/local/start/0', json={}, headers=self.headers)
            reset_response = self.client.post('/api/servers/local/reset/0', json={}, headers=self.headers)

        self.assertEqual(start_response.status_code, 409)
        self.assertEqual(reset_response.status_code, 409)
        start.assert_not_called()
        reset.assert_not_called()

    def test_expired_date_cannot_be_cleared_and_requires_future_renewal(self):
        metadata_store.save_metadata({'local:0': {'end_date': '2000-01-01'}})
        clear_response = self.client.put(
            '/api/servers/local/instances/0/metadata',
            json={'end_date': ''},
            headers=self.headers,
        )
        renew_response = self.client.put(
            '/api/servers/local/instances/0/metadata',
            json={'end_date': '2099-09-02'},
            headers=self.headers,
        )

        self.assertEqual(clear_response.status_code, 409)
        self.assertEqual(renew_response.status_code, 200)
        self.assertEqual(metadata_store.load_metadata()['local:0']['end_date'], '2099-09-02')


if __name__ == '__main__':
    unittest.main()
