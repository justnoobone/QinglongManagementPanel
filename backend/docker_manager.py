import docker
import os
import shutil
import json

# Docker 客户端 - 延迟初始化
_client = None


def get_client():
    """获取 Docker 客户端（延迟初始化）"""
    global _client
    if _client is None:
        try:
            _client = docker.from_env()
        except Exception as e:
            raise RuntimeError(f"无法连接 Docker: {str(e)}")
    return _client


def get_container_name(num):
    """生成容器名称
    - 实例 0: ql0（匹配原始 docker-compose 设计）
    - 实例 1+: qinglong{N}
    """
    if num == 0:
        return "ql0"
    return f"qinglong{num}"


def get_data_dir(num):
    """获取数据目录
    - 实例 0: /home/docker/qinglong/ql0（匹配原始 docker-compose 设计）
    - 实例 1+: /home/docker/qinglong/qinglong{N}
    """
    base = os.environ.get('QL_DATA_PATH', '/home/docker/qinglong')
    if num == 0:
        return f"{base}/ql0"
    return f"{base}/qinglong{num}"


def get_port(num):
    """获取映射端口"""
    return 5700 + num


def get_image(num):
    """获取镜像
    - 实例 0: debian-python3.10（与原始 docker-compose 一致）
    - 实例 1+: latest
    """
    if num == 0:
        return os.environ.get('QL0_IMAGE', 'whyour/qinglong:debian-python3.10')
    return os.environ.get('QL_IMAGE', 'whyour/qinglong:latest')


def list_instances():
    """列出所有青龙实例"""
    client = get_client()
    result = []

    for i in range(0, 101):
        name = get_container_name(i)
        try:
            container = client.containers.get(name)
            result.append({
                "id": i,
                "name": name,
                "status": container.status,
                "port": get_port(i)
            })
        except docker.errors.NotFound:
            pass
        except Exception as e:
            print(f"Error getting container {name}: {e}")

    return result


def create_instance(num, use_nginx=True):
    """创建青龙实例
    use_nginx: 是否启用 nginx 反向代理
    - 启用时设置 QlBaseUrl=/ql{N}/，使青龙面板支持子路径访问
    - 禁用时设置 QlBaseUrl=/，仅支持直连访问
    """
    client = get_client()
    name = get_container_name(num)
    data_dir = get_data_dir(num)
    port = get_port(num)
    image = get_image(num)

    # 检查并创建数据目录
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        print(f"已创建数据目录: {data_dir}")

    # 设置 QlBaseUrl 环境变量
    # QlBaseUrl 让青龙面板知道自己在子路径下运行
    # 这样前端 JS 的 API 调用和静态资源路径都会自动加上子路径前缀
    if use_nginx:
        ql_base_url = f"/ql{num}/"
    else:
        ql_base_url = "/"

    client.containers.run(
        image,
        name=name,
        hostname=name,
        detach=True,
        restart_policy={"Name": "unless-stopped"},
        ports={"5700/tcp": port},
        volumes={data_dir: {'bind': '/ql/data', 'mode': 'rw'}},
        network="ql_net",
        environment=[f"QlBaseUrl={ql_base_url}"],
        mem_limit="1g",
        nano_cpus=1000000000
    )

    # 更新 nginx 配置
    _update_nginx_config()


def start_instance(num):
    """启动青龙实例"""
    client = get_client()
    name = get_container_name(num)
    try:
        container = client.containers.get(name)
        container.start()
    except docker.errors.NotFound:
        raise RuntimeError(f"容器 {name} 不存在")
    except Exception as e:
        raise RuntimeError(f"启动实例失败: {str(e)}")


def stop_instance(num):
    """停止青龙实例"""
    client = get_client()
    name = get_container_name(num)
    try:
        container = client.containers.get(name)
        container.stop(timeout=10)
    except docker.errors.NotFound:
        raise RuntimeError(f"容器 {name} 不存在")
    except Exception as e:
        raise RuntimeError(f"停止实例失败: {str(e)}")


def delete_instance(num):
    """删除青龙实例（仅删除容器，保留数据）"""
    client = get_client()
    name = get_container_name(num)
    try:
        container = client.containers.get(name)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass
    except Exception as e:
        print(f"Error deleting container {name}: {e}")

    # 更新 nginx 配置
    _update_nginx_config()


def purge_instance(num):
    """彻底删除青龙实例（删除容器 + 数据目录）"""
    client = get_client()
    name = get_container_name(num)
    data_dir = get_data_dir(num)

    # 1. 删除容器
    try:
        container = client.containers.get(name)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass
    except Exception as e:
        print(f"Error deleting container {name}: {e}")

    # 2. 删除数据目录
    if os.path.exists(data_dir):
        try:
            shutil.rmtree(data_dir)
            print(f"已删除数据目录: {data_dir}")
        except Exception as e:
            print(f"Error deleting data dir {data_dir}: {e}")
            raise RuntimeError(f"删除数据目录失败: {str(e)}")

    # 更新 nginx 配置
    _update_nginx_config()


def reset_instance(num, use_nginx=True):
    """重置青龙实例（删除并重新创建）
    use_nginx: 是否在 nginx 代理中注册该实例
    """
    delete_instance(num)
    data_dir = get_data_dir(num)

    # 删除数据目录
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)

    # 重新创建
    os.makedirs(data_dir)
    create_instance(num, use_nginx=use_nginx)


def get_logs(num, tail=200):
    """获取容器日志"""
    client = get_client()
    name = get_container_name(num)
    try:
        container = client.containers.get(name)
        return container.logs(tail=tail, timestamps=True).decode("utf-8")
    except docker.errors.NotFound:
        return "容器不存在"
    except Exception as e:
        return f"获取日志失败: {str(e)}"


# ========== Nginx 容器管理 ==========

NGINX_CONTAINER_NAME = "nginx"
NGINX_IMAGE = "nginx:alpine"
NGINX_PORT = 91
NGINX_CONF_DIR = "/home/docker/nginx/conf.d"
NGINX_LOG_DIR = "/home/docker/nginx/logs"
NGINX_NETWORK = "ql_net"

# 元数据文件路径
METADATA_FILE = os.path.join(os.environ.get('PANEL_DATA_DIR', '/qlpanel/data'), 'instance_metadata.json')


def _load_metadata():
    """加载实例元数据"""
    if not os.path.exists(METADATA_FILE):
        return {}
    try:
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _get_nginx_enabled_instances():
    """获取每个实例的 nginx 代理启用状态（仅限本机 local 服务器）
    返回 dict: {instance_num: bool}，未在元数据中的实例默认 True
    """
    metadata = _load_metadata()
    result = {}
    for key, meta in metadata.items():
        if key.startswith('local:'):
            try:
                num = int(key.split(':')[1])
                result[num] = meta.get('use_nginx', True)
            except (IndexError, ValueError):
                pass
    return result


def get_nginx_status():
    """获取 nginx 容器状态"""
    client = get_client()
    try:
        container = client.containers.get(NGINX_CONTAINER_NAME)
        ports = []
        if container.attrs.get('NetworkSettings', {}).get('Ports'):
            for port_key, port_vals in container.attrs['NetworkSettings']['Ports'].items():
                if port_vals:
                    for pv in port_vals:
                        ports.append(f"{pv['HostPort']}:{port_key.split('/')[0]}")

        return {
            "exists": True,
            "status": container.status,
            "image": str(container.image.tags[0]) if container.image.tags else str(container.image.id[:12]),
            "ports": ports,
            "container_name": container.name,
        }
    except docker.errors.NotFound:
        return {
            "exists": False,
            "status": "not_found",
            "image": "",
            "ports": [],
            "container_name": NGINX_CONTAINER_NAME,
        }


def _ensure_ql_net(client):
    """确保 ql_net 网络存在"""
    try:
        client.networks.get(NGINX_NETWORK)
    except docker.errors.NotFound:
        client.networks.create(NGINX_NETWORK, driver="bridge")
        print(f"已创建网络: {NGINX_NETWORK}")


def _generate_nginx_config():
    """生成 nginx 配置内容

    关键设计：
    1. 使用 QlBaseUrl 模式：每个青龙实例设置 QlBaseUrl=/ql{N}/
    2. proxy_pass 不剥离子路径前缀（因为 QlBaseUrl 需要它）
    3. 不使用 sub_filter（QlBaseUrl 已处理前端路径问题）
    4. 静态生成每个实例的 location 块（而非正则，更可靠）
    """
    try:
        instances = list_instances()
    except Exception:
        instances = []

    # 获取每个实例的 nginx 代理启用状态
    nginx_status = _get_nginx_enabled_instances()

    # 为每个实例生成 location 块
    location_blocks = []
    for inst in instances:
        num = inst['id']

        # 检查该实例是否启用了 nginx 代理
        if num in nginx_status:
            if not nginx_status[num]:
                continue  # 明确禁用了 nginx 代理

        # 获取容器名称（作为 Docker 网络中的主机名）
        container_name = get_container_name(num)

        # 关键：proxy_pass 不带尾部斜杠，保留完整的请求 URI
        # 这样 /ql1/api/login 会被转发为 http://qinglong1:5700/ql1/api/login
        # 而 QlBaseUrl=/ql1/ 让青龙面板知道处理 /ql1/ 前缀下的请求
        block = f"""    location /ql{num}/ {{
        proxy_pass http://{container_name}:5700;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_buffering off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }}"""
        location_blocks.append(block)

    locations = '\n\n'.join(location_blocks)

    nav_comment = """# Reverse proxy for Qinglong panels
# QlBaseUrl mode: each instance knows its subpath via QlBaseUrl=/ql{N}/
# No sub_filter needed - QlBaseUrl handles all frontend path rewriting
# Direct access: http://host:PORT/  (redirects to /ql{N}/ if QlBaseUrl set)
# Proxy access: http://host:91/ql{N}/
"""

    return f"""{nav_comment}
server {{
    listen 80;
    server_name _;

    # Docker embedded DNS resolver
    resolver 127.0.0.11 valid=10s;
    resolver_timeout 5s;

    # Dynamic nav page
    location = / {{
        proxy_pass http://ql-panel-backend:5000/api/nav;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}

{locations}
}}
"""


def _ensure_nginx_config():
    """确保 nginx 配置文件存在且为最新版本"""
    _update_nginx_config()


def _update_nginx_config():
    """更新 nginx 配置文件（根据当前实例列表生成），并在容器运行时自动 reload"""
    os.makedirs(NGINX_CONF_DIR, exist_ok=True)
    os.makedirs(NGINX_LOG_DIR, exist_ok=True)

    conf_file = os.path.join(NGINX_CONF_DIR, "ql_panels.conf")
    config_content = _generate_nginx_config()

    with open(conf_file, 'w') as f:
        f.write(config_content)
    print(f"已更新 nginx 配置: {conf_file}")

    # 如果 nginx 容器正在运行，自动 reload
    try:
        client = get_client()
        container = client.containers.get(NGINX_CONTAINER_NAME)
        if container.status == 'running':
            exit_code, output = container.exec_run("nginx -s reload")
            if exit_code == 0:
                print("nginx 配置已 reload")
            else:
                print(f"nginx reload 失败: {output.decode('utf-8', errors='replace')}")
    except docker.errors.NotFound:
        pass
    except Exception as e:
        print(f"nginx reload 出错: {e}")


def create_nginx_container():
    """创建 nginx 反向代理容器"""
    client = get_client()

    _ensure_ql_net(client)
    _ensure_nginx_config()

    # 检查是否已存在
    try:
        container = client.containers.get(NGINX_CONTAINER_NAME)
        try:
            container.reload()
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            if NGINX_NETWORK not in networks:
                net = client.networks.get(NGINX_NETWORK)
                net.connect(container)
                print(f"已将 nginx 容器连接到 {NGINX_NETWORK} 网络")
        except Exception as e:
            print(f"连接网络时出错: {e}")
        container.restart(timeout=5)
        return {"msg": f"nginx 配置已更新并重启", "status": container.status}
    except docker.errors.NotFound:
        pass

    container = client.containers.run(
        NGINX_IMAGE,
        name=NGINX_CONTAINER_NAME,
        detach=True,
        restart_policy={"Name": "unless-stopped"},
        ports={"80/tcp": NGINX_PORT},
        volumes={
            NGINX_CONF_DIR: {'bind': '/etc/nginx/conf.d', 'mode': 'ro'},
            NGINX_LOG_DIR: {'bind': '/var/log/nginx', 'mode': 'rw'},
        },
        network=NGINX_NETWORK,
    )
    return {"msg": "nginx 容器创建成功", "status": container.status}


def start_nginx_container():
    """启动 nginx 容器"""
    client = get_client()
    try:
        container = client.containers.get(NGINX_CONTAINER_NAME)
        container.start()
        return {"msg": "nginx 启动成功", "status": "running"}
    except docker.errors.NotFound:
        return create_nginx_container()


def stop_nginx_container():
    """停止 nginx 容器"""
    client = get_client()
    try:
        container = client.containers.get(NGINX_CONTAINER_NAME)
        container.stop(timeout=5)
        return {"msg": "nginx 停止成功", "status": "exited"}
    except docker.errors.NotFound:
        return {"msg": "nginx 容器不存在", "status": "not_found"}


def restart_nginx_container():
    """重启 nginx 容器"""
    client = get_client()
    _ensure_nginx_config()
    try:
        container = client.containers.get(NGINX_CONTAINER_NAME)
        container.restart(timeout=5)
        return {"msg": "nginx 重启成功", "status": "running"}
    except docker.errors.NotFound:
        return create_nginx_container()
