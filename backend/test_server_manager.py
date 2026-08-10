import os
import tempfile
import unittest
from unittest.mock import patch

import server_manager


class ServerManagerTests(unittest.TestCase):
    def test_remote_server_can_be_edited_without_replacing_password(self):
        with tempfile.TemporaryDirectory() as directory:
            servers_file = os.path.join(directory, 'servers.json')
            with patch.object(server_manager, 'SERVERS_FILE', servers_file):
                server = server_manager.add_server(
                    '旧名称', '192.0.2.20', 22, 'root', 'initial-password', '/srv/qinglong'
                )
                updated = server_manager.update_server(
                    server['id'], name='新名称', path='/data/qinglong', password=''
                )
                private = server_manager.get_server(server['id'])
                public = next(item for item in server_manager.list_servers() if item['id'] == server['id'])

        self.assertEqual(updated['name'], '新名称')
        self.assertEqual(updated['path'], '/data/qinglong')
        self.assertEqual(private['password'], 'initial-password')
        self.assertNotIn('password', public)
        self.assertEqual(public['nginx_image'], 'nginx:1.29.7-alpine')


if __name__ == '__main__':
    unittest.main()
