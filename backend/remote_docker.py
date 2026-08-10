import base64
import json
import posixpath
import re
import shlex

import paramiko

from nginx_config import generate_nginx_config, uses_prefixed_base_url


INSTANCE_NAME_RE = re.compile(r"^(?:qinglong|ql)(\d+)$")
DOCKER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,254}$")
MEMORY_RE = re.compile(r"^[1-9][0-9]*(?:[kKmMgG])?[bB]?$")

DEFAULT_NGINX_IMAGE = "nginx:1.29.7-alpine"
DEFAULT_NGINX_PORT = 91
DEFAULT_NGINX_PATH = "/home/docker/nginx"
DEFAULT_NGINX_CONTAINER = "nginx"
DEFAULT_NGINX_NETWORK = "ql_net"


def _ssh_exec(host, port, username, password, command, timeout=30):
    """Execute command on remote server via SSH."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=username, password=password, timeout=timeout)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8', errors='replace')
        error = stderr.read().decode('utf-8', errors='replace')
        return exit_code, output, error
    finally:
        client.close()


def _run(server, command, timeout=30):
    return _ssh_exec(
        server['host'],
        int(server.get('port', 22)),
        server.get('username', 'root'),
        server.get('password', ''),
        command,
        timeout=timeout,
    )


def _instance_num(num):
    value = int(num)
    if value < 0 or value > 100:
        raise ValueError('实例编号必须在 0 到 100 之间')
    return value


def _container_name(num):
    return f"qinglong{_instance_num(num)}"


def _safe_docker_name(value, default):
    value = str(value or default).strip()
    if not DOCKER_NAME_RE.fullmatch(value):
        raise ValueError(f'非法 Docker 名称: {value}')
    return value


def _safe_image(value, default):
    value = str(value or default).strip()
    if not IMAGE_RE.fullmatch(value):
        raise ValueError('镜像名称格式不正确')
    return value


def _safe_absolute_path(value, default):
    value = str(value or default).strip()
    normalized = posixpath.normpath(value)
    if not normalized.startswith('/') or normalized in ('/', '/home', '/opt', '/var'):
        raise ValueError('目录必须是具体的绝对路径')
    if len(normalized) > 240:
        raise ValueError('目录路径过长')
    return normalized


def _safe_port(value, default):
    port = int(value or default)
    if port < 1 or port > 65535:
        raise ValueError('端口必须在 1 到 65535 之间')
    return port


def _resource_options(cpu_limit=None, mem_limit=None):
    options = []
    if cpu_limit:
        cpus = float(cpu_limit) / 1000000000
        if cpus <= 0 or cpus > 256:
            raise ValueError('CPU 限制不合法')
        options.append(f'--cpus={cpus:g}')
    if mem_limit:
        memory = str(mem_limit).strip()
        if not MEMORY_RE.fullmatch(memory):
            raise ValueError('内存限制格式不正确，例如 512m 或 1g')
        options.append(f'--memory={shlex.quote(memory)}')
    return options


def _raise_remote_error(prefix, code, error, output=''):
    detail = (error or output or f'exit_code={code}').strip()
    raise RuntimeError(f'{prefix}: {detail}')


def check_connection(host, port=22, username='root', password=''):
    """Test SSH connection to remote server. Returns (ok, msg) tuple."""
    try:
        code, out, err = _ssh_exec(host, port, username, password, 'echo ok')
        if code == 0 and 'ok' in out:
            return True, '连接成功'
        return False, f'连接失败: exit_code={code}'
    except Exception as exc:
        return False, f'连接异常: {str(exc)}'


def list_instances(server):
    """List Qinglong instances and inspect their real image, port and base URL."""
    code, out, err = _run(server, "docker ps -a --format '{{.Names}}'")
    if code != 0:
        _raise_remote_error('读取远程容器失败', code, err, out)

    names = []
    for raw_name in out.splitlines():
        name = raw_name.strip()
        match = INSTANCE_NAME_RE.fullmatch(name)
        if match and 0 <= int(match.group(1)) <= 100:
            names.append(name)
    if not names:
        return []

    inspect_command = 'docker inspect ' + ' '.join(shlex.quote(name) for name in names)
    code, out, err = _run(server, inspect_command)
    if code != 0:
        _raise_remote_error('读取远程实例详情失败', code, err, out)

    try:
        inspected = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'远程 Docker 返回了无效数据: {str(exc)}') from exc

    instances = []
    for container in inspected:
        name = str(container.get('Name', '')).lstrip('/')
        match = INSTANCE_NAME_RE.fullmatch(name)
        if not match:
            continue
        num = int(match.group(1))
        config = container.get('Config') or {}
        state = container.get('State') or {}
        network = container.get('NetworkSettings') or {}
        bindings = (network.get('Ports') or {}).get('5700/tcp') or []
        host_port = 5700 + num
        if bindings and bindings[0].get('HostPort'):
            try:
                host_port = int(bindings[0]['HostPort'])
            except (TypeError, ValueError):
                pass
        environment = config.get('Env') or []
        env_map = dict(item.split('=', 1) for item in environment if '=' in item)
        instances.append({
            'id': num,
            'name': name,
            'status': state.get('Status', 'unknown'),
            'health': (state.get('Health') or {}).get('Status', ''),
            'port': host_port,
            'created': container.get('Created', ''),
            'image': config.get('Image', ''),
            'ql_base_url': env_map.get('QlBaseUrl', '/'),
        })

    instances.sort(key=lambda item: item['id'])
    return instances


def create_instance(server, num, port=None, image=None, cpu_limit=None, mem_limit=None, use_nginx=True):
    """Create a Qinglong instance on a remote server."""
    num = _instance_num(num)
    port = _safe_port(port, 5700 + num)
    name = _container_name(num)
    base_path = _safe_absolute_path(server.get('path'), '/home/docker/qinglong')
    data_dir = posixpath.join(base_path, name)
    image = _safe_image(image, 'whyour/qinglong:latest')
    base_url = f'/ql{num}/' if use_nginx else '/'

    options = [
        '--restart unless-stopped',
        f'--hostname {shlex.quote(name)}',
        f'-p {port}:5700',
        f'-v {shlex.quote(data_dir)}:/ql/data',
        f'--network {DEFAULT_NGINX_NETWORK}',
        f'-e {shlex.quote(f"QlBaseUrl={base_url}")}',
        *_resource_options(cpu_limit, mem_limit),
    ]
    command = '\n'.join([
        'set -eu',
        f'docker network inspect {DEFAULT_NGINX_NETWORK} >/dev/null 2>&1 || docker network create {DEFAULT_NGINX_NETWORK} >/dev/null',
        f'mkdir -p {shlex.quote(data_dir)}',
        f'docker run -d --name {shlex.quote(name)} {" ".join(options)} {shlex.quote(image)}',
    ])
    code, out, err = _run(server, command, timeout=120)
    if code != 0:
        _raise_remote_error('创建远程容器失败', code, err, out)
    return {'name': name, 'status': 'running', 'num': num}


def start_instance(server, num):
    name = _container_name(num)
    code, out, err = _run(server, f'docker start {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('启动远程容器失败', code, err, out)
    return {'name': name, 'status': 'running', 'num': int(num)}


def stop_instance(server, num):
    name = _container_name(num)
    code, out, err = _run(server, f'docker stop {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('停止远程容器失败', code, err, out)
    return {'name': name, 'status': 'exited', 'num': int(num)}


def delete_instance(server, num):
    name = _container_name(num)
    code, out, err = _run(server, f'docker rm -f {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('删除远程容器失败', code, err, out)
    return {'name': name, 'status': 'deleted', 'num': int(num)}


def purge_instance(server, num):
    name = _container_name(num)
    base_path = _safe_absolute_path(server.get('path'), '/home/docker/qinglong')
    data_dir = posixpath.join(base_path, name)
    command = '\n'.join([
        f'docker rm -f {shlex.quote(name)} >/dev/null 2>&1 || true',
        f'find {shlex.quote(data_dir)} -mindepth 1 -delete',
        f'rmdir {shlex.quote(data_dir)} 2>/dev/null || true',
    ])
    code, out, err = _run(server, command, timeout=120)
    if code != 0:
        _raise_remote_error('删除远程实例数据失败', code, err, out)
    return {'name': name, 'status': 'purged', 'num': int(num)}


def reset_instance(server, num, image=None, cpu_limit=None, mem_limit=None, use_nginx=True):
    num = _instance_num(num)
    name = _container_name(num)
    base_path = _safe_absolute_path(server.get('path'), '/home/docker/qinglong')
    data_dir = posixpath.join(base_path, name)
    port = 5700 + num
    image = _safe_image(image, 'whyour/qinglong:latest')
    base_url = f'/ql{num}/' if use_nginx else '/'
    options = [
        '--restart unless-stopped',
        f'--hostname {shlex.quote(name)}',
        f'-p {port}:5700',
        f'-v {shlex.quote(data_dir)}:/ql/data',
        f'--network {DEFAULT_NGINX_NETWORK}',
        f'-e {shlex.quote(f"QlBaseUrl={base_url}")}',
        *_resource_options(cpu_limit, mem_limit),
    ]
    command = '\n'.join([
        'set -eu',
        f'docker network inspect {DEFAULT_NGINX_NETWORK} >/dev/null 2>&1 || docker network create {DEFAULT_NGINX_NETWORK} >/dev/null',
        f'docker rm -f {shlex.quote(name)} >/dev/null 2>&1 || true',
        f'mkdir -p {shlex.quote(data_dir)}',
        f'find {shlex.quote(data_dir)} -mindepth 1 -delete',
        f'docker run -d --name {shlex.quote(name)} {" ".join(options)} {shlex.quote(image)}',
    ])
    code, out, err = _run(server, command, timeout=180)
    if code != 0:
        _raise_remote_error('重置远程容器失败', code, err, out)
    return {'name': name, 'status': 'running', 'num': num}


def get_logs(server, num, tail=100):
    name = _container_name(num)
    tail = max(1, min(int(tail), 5000))
    code, out, err = _run(server, f'docker logs --tail {tail} {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('获取远程日志失败', code, err, out)
    return out + err


def nginx_settings(server, overrides=None):
    overrides = overrides or {}
    return {
        'image': _safe_image(overrides.get('image') or server.get('nginx_image'), DEFAULT_NGINX_IMAGE),
        'port': _safe_port(overrides.get('port') or server.get('nginx_port'), DEFAULT_NGINX_PORT),
        'path': _safe_absolute_path(overrides.get('path') or server.get('nginx_path'), DEFAULT_NGINX_PATH),
        'container_name': _safe_docker_name(server.get('nginx_container'), DEFAULT_NGINX_CONTAINER),
        'network': _safe_docker_name(server.get('nginx_network'), DEFAULT_NGINX_NETWORK),
    }


def get_nginx_status(server):
    settings = nginx_settings(server)
    name = settings['container_name']
    code, out, err = _run(server, f'docker inspect {shlex.quote(name)}')
    if code != 0:
        detail = f'{err}\n{out}'.lower()
        if 'no such object' not in detail and 'no such container' not in detail:
            _raise_remote_error('读取远程 Nginx 状态失败', code, err, out)
        return {
            'exists': False,
            'status': 'not_found',
            'image': settings['image'],
            'ports': [],
            'container_name': name,
            'configured_port': settings['port'],
            'configured_path': settings['path'],
        }
    try:
        container = json.loads(out)[0]
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f'远程 Nginx 状态数据无效: {str(exc)}') from exc
    config = container.get('Config') or {}
    state = container.get('State') or {}
    port_map = (container.get('NetworkSettings') or {}).get('Ports') or {}
    ports = []
    for container_port, bindings in port_map.items():
        for binding in bindings or []:
            if binding.get('HostPort'):
                ports.append(f"{binding['HostPort']}:{container_port.split('/')[0]}")
    return {
        'exists': True,
        'status': state.get('Status', 'unknown'),
        'image': config.get('Image', settings['image']),
        'ports': ports,
        'container_name': name,
        'configured_port': settings['port'],
        'configured_path': settings['path'],
    }


def _build_nginx_deploy_script(settings, instances, config_content):
    """Build the reviewed deployment script; execution happens only on API action."""
    image = settings['image']
    host_port = settings['port']
    base_path = settings['path']
    name = settings['container_name']
    network = settings['network']
    conf_dir = posixpath.join(base_path, 'conf.d')
    log_dir = posixpath.join(base_path, 'logs')
    candidate_file = posixpath.join(conf_dir, '.ql_panels.conf.candidate')
    final_file = posixpath.join(conf_dir, 'ql_panels.conf')
    check_name = f'{name}_config_check'
    backup_name = f'{name}_ql_rollback'
    encoded = base64.b64encode(config_content.encode('utf-8')).decode('ascii')

    lines = [
        'set -eu',
        f'mkdir -p {shlex.quote(conf_dir)} {shlex.quote(log_dir)}',
        f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(candidate_file)}",
        f'docker pull {shlex.quote(image)}',
        f'docker network inspect {shlex.quote(network)} >/dev/null 2>&1 || docker network create {shlex.quote(network)} >/dev/null',
    ]
    for instance in instances:
        container_name = _safe_docker_name(instance.get('name'), '')
        lines.append(
            f'docker network connect {shlex.quote(network)} {shlex.quote(container_name)} >/dev/null 2>&1 || true'
        )
    lines.extend([
        f'docker rm -f {shlex.quote(check_name)} >/dev/null 2>&1 || true',
        (
            f'docker run --rm --name {shlex.quote(check_name)} '
            f'-v {shlex.quote(candidate_file)}:/etc/nginx/conf.d/ql_panels.conf:ro '
            f'{shlex.quote(image)} nginx -t'
        ),
        f'mv {shlex.quote(candidate_file)} {shlex.quote(final_file)}',
        f'if docker inspect {shlex.quote(backup_name)} >/dev/null 2>&1; then',
        f'  if docker inspect {shlex.quote(name)} >/dev/null 2>&1; then',
        f'    docker rm -f {shlex.quote(backup_name)} >/dev/null',
        '  else',
        f'    docker rename {shlex.quote(backup_name)} {shlex.quote(name)}',
        f'    docker start {shlex.quote(name)} >/dev/null',
        '  fi',
        'fi',
        'had_previous=0',
        f'if docker inspect {shlex.quote(name)} >/dev/null 2>&1; then',
        f'  docker stop {shlex.quote(name)} >/dev/null',
        f'  if ! docker rename {shlex.quote(name)} {shlex.quote(backup_name)}; then',
        f'    docker start {shlex.quote(name)} >/dev/null 2>&1 || true',
        '    exit 1',
        '  fi',
        '  had_previous=1',
        'fi',
        (
            f'if docker run -d --name {shlex.quote(name)} --restart unless-stopped '
            f'-p {host_port}:80 -v {shlex.quote(conf_dir)}:/etc/nginx/conf.d:ro '
            f'-v {shlex.quote(log_dir)}:/var/log/nginx --network {shlex.quote(network)} '
            f'{shlex.quote(image)} >/dev/null; then'
        ),
        '  sleep 1',
        f'  if docker exec {shlex.quote(name)} nginx -t >/dev/null 2>&1; then',
        '    deployment_ok=1',
        '  else',
        '    deployment_ok=0',
        '  fi',
        'else',
        '  deployment_ok=0',
        'fi',
        'if [ "$deployment_ok" -eq 1 ]; then',
        '  if [ "$had_previous" -eq 1 ]; then',
        f'    docker rm -f {shlex.quote(backup_name)} >/dev/null',
        '  fi',
        'else',
        f'  docker rm -f {shlex.quote(name)} >/dev/null 2>&1 || true',
        '  if [ "$had_previous" -eq 1 ]; then',
        f'    docker rename {shlex.quote(backup_name)} {shlex.quote(name)}',
        f'    docker start {shlex.quote(name)} >/dev/null',
        '  fi',
        '  exit 1',
        'fi',
    ])
    return '\n'.join(lines)


def preview_nginx_config(server, enabled_ids=None, disabled_ids=None):
    instances = list_instances(server)
    if enabled_ids is None and disabled_ids:
        disabled = {int(num) for num in disabled_ids}
        enabled_ids = [instance['id'] for instance in instances if instance['id'] not in disabled]
    return generate_nginx_config(instances, enabled_ids=enabled_ids), instances


def deploy_nginx(server, enabled_ids=None, disabled_ids=None, overrides=None):
    settings = nginx_settings(server, overrides)
    config_content, instances = preview_nginx_config(
        server,
        enabled_ids=enabled_ids,
        disabled_ids=disabled_ids,
    )
    script = _build_nginx_deploy_script(settings, instances, config_content)
    code, out, err = _run(server, script, timeout=300)
    if code != 0:
        _raise_remote_error('远程 Nginx 部署失败，已尝试恢复原容器', code, err, out)
    legacy_count = sum(1 for instance in instances if not uses_prefixed_base_url(instance))
    return {
        'msg': '远程 Nginx 已部署并应用配置',
        'status': 'running',
        'settings': settings,
        'instances': len(instances),
        'legacy_compatible_instances': legacy_count,
    }


def start_nginx(server):
    name = nginx_settings(server)['container_name']
    code, out, err = _run(server, f'docker start {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('启动远程 Nginx 失败', code, err, out)
    return {'msg': '远程 Nginx 已启动', 'status': 'running'}


def stop_nginx(server):
    name = nginx_settings(server)['container_name']
    code, out, err = _run(server, f'docker stop {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('停止远程 Nginx 失败', code, err, out)
    return {'msg': '远程 Nginx 已停止', 'status': 'exited'}


def restart_nginx(server):
    name = nginx_settings(server)['container_name']
    code, out, err = _run(server, f'docker restart {shlex.quote(name)}')
    if code != 0:
        _raise_remote_error('重启远程 Nginx 失败', code, err, out)
    return {'msg': '远程 Nginx 已重启', 'status': 'running'}
