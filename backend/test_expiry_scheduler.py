import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import expiry_scheduler
import metadata_store


class ExpirySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 1, 0, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        self.instances = [
            {'id': 0, 'name': 'qinglong0', 'status': 'running'},
            {'id': 1, 'name': 'qinglong1', 'status': 'running'},
            {'id': 2, 'name': 'qinglong2', 'status': 'exited'},
        ]

    def test_today_and_past_dates_are_due_but_future_is_not(self):
        metadata = {
            'local:0': {'end_date': '2026-09-01'},
            'local:1': {'end_date': '2026-09-02'},
            'local:2': {'end_date': '2026-08-31'},
        }
        with patch.object(expiry_scheduler, 'load_metadata', return_value=metadata), patch.object(
            expiry_scheduler, 'list_instances', return_value=self.instances
        ):
            results = expiry_scheduler.run_expiry_check(now=self.now, dry_run=True)

        self.assertEqual([item['instance_id'] for item in results], [0])

    def test_scheduler_never_selects_remote_metadata(self):
        metadata = {'remote_111-230-107-206-22:0': {'end_date': '2026-08-01'}}
        with patch.object(expiry_scheduler, 'load_metadata', return_value=metadata), patch.object(
            expiry_scheduler, 'list_instances', return_value=self.instances
        ):
            results = expiry_scheduler.run_expiry_check(now=self.now, dry_run=True)

        self.assertEqual(results, [])

    def test_instance_without_expiry_date_is_skipped(self):
        metadata = {'local:0': {'end_date': ''}}
        with patch.object(expiry_scheduler, 'load_metadata', return_value=metadata), patch.object(
            expiry_scheduler, 'list_instances', return_value=self.instances
        ):
            results = expiry_scheduler.run_expiry_check(now=self.now, dry_run=True)

        self.assertEqual(results, [])

    def test_due_instance_is_stopped_and_marked_in_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            metadata_store, 'METADATA_FILE', os.path.join(directory, 'metadata.json')
        ), patch.object(metadata_store, 'LOCK_FILE', os.path.join(directory, 'metadata.lock')):
            metadata_store.save_metadata({'local:0': {'end_date': '2026-09-01'}})
            with patch.object(expiry_scheduler, 'list_instances', return_value=self.instances), patch.object(
                expiry_scheduler, 'stop_instance'
            ) as stop:
                results = expiry_scheduler.run_expiry_check(now=self.now)
            saved = metadata_store.load_metadata()['local:0']

        stop.assert_called_once_with(0)
        self.assertEqual(results[0]['status'], 'stopped')
        self.assertTrue(saved['stopped_by_expiry'])
        self.assertEqual(saved['expiry_state'], 'stopped')


if __name__ == '__main__':
    unittest.main()
