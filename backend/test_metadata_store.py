import json
import os
import tempfile
import unittest
from unittest.mock import patch

import metadata_store


class MetadataStoreTests(unittest.TestCase):
    def test_transaction_atomically_updates_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            metadata_store, 'METADATA_FILE', os.path.join(directory, 'metadata.json')
        ), patch.object(metadata_store, 'LOCK_FILE', os.path.join(directory, 'metadata.lock')):
            with metadata_store.metadata_transaction() as metadata:
                metadata['local:0'] = {'end_date': '2026-09-01'}
            with open(metadata_store.METADATA_FILE, encoding='utf-8') as handle:
                saved = json.load(handle)

        self.assertEqual(saved['local:0']['end_date'], '2026-09-01')

    def test_failed_transaction_does_not_persist_partial_update(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            metadata_store, 'METADATA_FILE', os.path.join(directory, 'metadata.json')
        ), patch.object(metadata_store, 'LOCK_FILE', os.path.join(directory, 'metadata.lock')):
            metadata_store.save_metadata({'local:0': {'end_date': '2026-09-01'}})
            with self.assertRaises(RuntimeError):
                with metadata_store.metadata_transaction() as metadata:
                    metadata['local:0']['end_date'] = '2026-09-02'
                    raise RuntimeError('cancel update')
            saved = metadata_store.load_metadata()

        self.assertEqual(saved['local:0']['end_date'], '2026-09-01')


if __name__ == '__main__':
    unittest.main()
