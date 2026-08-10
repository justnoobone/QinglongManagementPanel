import unittest

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


if __name__ == '__main__':
    unittest.main()
