import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_manager


class FakeImage:
    tags = ["whyour/qinglong:test"]
    short_id = "sha256:test"


class FakeContainer:
    def __init__(self, name, status, host_port, env=None):
        self.name = name
        self.status = status
        self.image = FakeImage()
        self.attrs = {
            "NetworkSettings": {
                "Ports": {"5700/tcp": [{"HostPort": str(host_port)}]},
            },
            "State": {"Health": {"Status": "healthy"}},
            "Config": {"Env": env or ["QlBaseUrl=/ql1/"]},
        }


class FakeContainers:
    def __init__(self, containers):
        self._containers = containers

    def list(self, all=False):
        return self._containers


class FakeClient:
    def __init__(self, containers):
        self.containers = FakeContainers(containers)


class DockerManagerTests(unittest.TestCase):
    def test_zero_instance_uses_current_canonical_name_and_path(self):
        self.assertEqual(docker_manager.get_container_name(0), "qinglong0")
        self.assertTrue(docker_manager.get_data_dir(0).endswith("/qinglong0"))

    def test_list_instances_supports_both_historical_names(self):
        client = FakeClient([
            FakeContainer("qinglong0", "running", 5700),
            FakeContainer("qinglong1", "running", 5701),
            FakeContainer("ql_manager", "running", 8080),
        ])

        with patch.object(docker_manager, "get_client", return_value=client):
            instances = docker_manager.list_instances()

        self.assertEqual([item["id"] for item in instances], [0, 1])
        self.assertEqual(instances[0]["name"], "qinglong0")
        self.assertEqual(instances[1]["port"], 5701)

    def test_wrong_legacy_environment_name_is_not_treated_as_ql_base_url(self):
        client = FakeClient([
            FakeContainer("qinglong0", "running", 5700, env=["QL_BASE_PATH=/ql0/"]),
        ])

        with patch.object(docker_manager, "get_client", return_value=client):
            instances = docker_manager.list_instances()

        self.assertEqual(instances[0]["ql_base_url"], "/")

    def test_nginx_config_uses_relative_trailing_slash_redirect(self):
        instances = [{"id": 1, "name": "qinglong1", "status": "running", "port": 5701, "ql_base_url": "/ql1/"}]

        with patch.object(docker_manager, "list_instances", return_value=instances), patch.object(
            docker_manager,
            "_get_nginx_enabled_instances",
            return_value={1: True},
        ):
            config = docker_manager._generate_nginx_config()

        self.assertIn("location = /ql1", config)
        self.assertIn("return 308 /ql1/;", config)
        self.assertIn("set $ql1_upstream http://qinglong1:5700;", config)
        self.assertIn("proxy_pass $ql1_upstream;", config)
        self.assertNotIn("rewrite ^/ql1/", config)
        self.assertIn("absolute_redirect off;", config)

    def test_legacy_instance_uses_strip_prefix_compatibility_route(self):
        instances = [{"id": 0, "name": "qinglong0", "status": "running", "port": 5700, "ql_base_url": "/"}]

        with patch.object(docker_manager, "list_instances", return_value=instances), patch.object(
            docker_manager,
            "_get_nginx_enabled_instances",
            return_value={0: True},
        ):
            config = docker_manager._generate_nginx_config()

        self.assertIn("location = /ql0/api/env.js", config)
        self.assertIn('window.__ENV__QlBaseUrl="/ql0/"', config)
        self.assertIn("set $ql0_upstream http://qinglong0:5700;", config)
        self.assertIn("rewrite ^/ql0/(.*)$ /$1 break;", config)
        self.assertIn("proxy_pass $ql0_upstream;", config)
        self.assertIn("proxy_cookie_path / /ql0/;", config)


if __name__ == "__main__":
    unittest.main()
