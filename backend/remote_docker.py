import paramiko


def _ssh_exec(host, port, username, password, command, timeout=30):
    """Execute command on remote server via SSH"""
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


def check_connection(host, port=22, username='root', password=''):
    """Test SSH connection to remote server. Returns (ok, msg) tuple."""
    try:
        code, out, err = _ssh_exec(host, port, username, password, 'echo ok')
        if code == 0 and 'ok' in out:
            return True, '连接成功'
        return False, f'连接失败: exit_code={code}'
    except Exception as e:
        return False, f'连接异常: {str(e)}'


def list_instances(server):
    """List qinglong instances on remote server"""
    cmd = 'docker ps -a --filter "name=qinglong" --format "{{.Names}}\\t{{.Status}}\\t{{.Ports}}\\t{{.CreatedAt}}"'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'远程命令执行失败: {err}')

    instances = []
    for line in out.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        name = parts[0]
        if not name.startswith('qinglong') or not name[8:].isdigit():
            continue
        num = int(name[8:])
        if num < 0 or num > 100:
            continue

        status = 'running' if 'Up' in parts[1] else 'exited'
        ports = parts[2] if len(parts) > 2 else ''
        created = parts[3] if len(parts) > 3 else ''

        instances.append({
            'id': num,
            'name': name,
            'status': status,
            'port': 5700 + num,
            'ports': ports,
            'created': created,
            'image': 'whyour/qinglong:latest',
        })

    instances.sort(key=lambda x: x['id'])
    return instances


def create_instance(server, num, port=None, image=None, cpu_limit=None, mem_limit=None):
    """Create a qinglong instance on remote server"""
    if port is None:
        port = 5700 + num
    name = f'qinglong{num}'
    data_dir = f'/home/docker/qinglong/qinglong{num}'
    image = image or 'whyour/qinglong:latest'

    # 构建 docker run 命令
    opts = f'--restart always -p {port}:5700 -v {data_dir}:/ql/data'
    if cpu_limit:
        cpus = cpu_limit / 1000000000
        opts += f' --cpus={cpus}'
    if mem_limit:
        opts += f' --memory={mem_limit}'

    cmd = f'mkdir -p {data_dir} && docker run -d --name {name} {opts} {image}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'创建远程容器失败: {err}')
    return {'name': name, 'status': 'running', 'num': num}


def start_instance(server, num):
    """Start a stopped qinglong instance on remote server"""
    name = f'qinglong{num}'
    cmd = f'docker start {name}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'启动远程容器失败: {err}')
    return {'name': name, 'status': 'running', 'num': num}


def stop_instance(server, num):
    """Stop a running qinglong instance on remote server"""
    name = f'qinglong{num}'
    cmd = f'docker stop {name}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'停止远程容器失败: {err}')
    return {'name': name, 'status': 'exited', 'num': num}


def delete_instance(server, num):
    """Delete a qinglong instance on remote server (container only)"""
    name = f'qinglong{num}'
    cmd = f'docker rm -f {name}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'删除远程容器失败: {err}')
    return {'name': name, 'status': 'deleted', 'num': num}


def purge_instance(server, num):
    """Purge a qinglong instance on remote server (container + data directory)"""
    name = f'qinglong{num}'
    data_dir = f'/home/docker/qinglong/qinglong{num}'

    # 1. Delete container
    cmd = f'docker rm -f {name}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    # Allow container not found error

    # 2. Delete data directory
    cmd = f'rm -rf {data_dir}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'删除远程数据目录失败: {err}')
    return {'name': name, 'status': 'purged', 'num': num}


def reset_instance(server, num, image=None, cpu_limit=None, mem_limit=None):
    """Reset a qinglong instance on remote server"""
    name = f'qinglong{num}'
    data_dir = f'/home/docker/qinglong/qinglong{num}'
    port = 5700 + num
    image = image or 'whyour/qinglong:latest'

    # Remove and recreate with params
    opts = f'--restart always -p {port}:5700 -v {data_dir}:/ql/data'
    if cpu_limit:
        cpus = cpu_limit / 1000000000
        opts += f' --cpus={cpus}'
    if mem_limit:
        opts += f' --memory={mem_limit}'

    cmd = f'docker rm -f {name} && rm -rf {data_dir}/* && docker run -d --name {name} {opts} {image}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'重置远程容器失败: {err}')
    return {'name': name, 'status': 'running', 'num': num}


def get_logs(server, num, tail=100):
    """Get container logs from remote server"""
    name = f'qinglong{num}'
    cmd = f'docker logs --tail {tail} {name}'
    code, out, err = _ssh_exec(
        server['host'], server['port'],
        server['username'], server['password'],
        cmd
    )
    if code != 0:
        raise Exception(f'获取远程日志失败: {err}')
    return out + err
