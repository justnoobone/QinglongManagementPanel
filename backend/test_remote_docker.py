import unittest
from unittest.mock import patch

import remote_docker


class RemoteDockerTests(unittest.TestCase):
    def setUp(self):
        self.server = {
            'host': 'example.test',
            'port': 22,
            'username': 'root',
            'password': 'secret',
            'path': '/srv/qinglong',
        }

    def test_nginx_settings_are_pinned_and_validated(self):
        settings = remote_docker.nginx_settings(self.server)
        self.assertEqual(settings['image'], 'nginx:1.29.7-alpine')
        self.assertEqual(settings['port'], 91)
        self.assertEqual(settings['path'], '/home/docker/nginx')

        with self.assertRaises(ValueError):
            remote_docker.nginx_settings(self.server, {'image': 'nginx;rm -rf /'})

    def test_deploy_script_validates_before_switching_container(self):
        settings = remote_docker.nginx_settings(self.server, {'image': 'nginx:1.29.7-alpine'})
        instances = [
            {'id': 0, 'name': 'qinglong0', 'ql_base_url': '/'},
            {'id': 1, 'name': 'qinglong1', 'ql_base_url': '/ql1/'},
        ]
        config = 'server { listen 80; }'
        script = remote_docker._build_nginx_deploy_script(settings, instances, config)
        self.assertIn('nginx -t', script)
        self.assertIn('docker network connect ql_net qinglong0', script)
        self.assertIn('docker rename nginx nginx_ql_rollback', script)
        self.assertLess(script.index('nginx -t'), script.index('docker stop nginx'))

    def test_created_instance_keeps_direct_access_at_root(self):
        with patch.object(remote_docker, '_run', return_value=(0, 'container-id', '')) as remote_run:
            remote_docker.create_instance(self.server, 1, use_nginx=True)

        command = remote_run.call_args.args[1]
        self.assertIn('QlBaseUrl=/', command)
        self.assertNotIn('QlBaseUrl=/ql1/', command)


if __name__ == '__main__':
    unittest.main()
