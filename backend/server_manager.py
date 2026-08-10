import json
import os
import base64
import hashlib
from cryptography.fernet import Fernet
from config import JWT_SECRET_KEY, PANEL_DATA_DIR

SERVERS_FILE = os.path.join(PANEL_DATA_DIR, 'servers.json')

DEFAULT_REMOTE_NGINX = {
    'nginx_image': 'nginx:1.29.7-alpine',
    'nginx_port': 91,
    'nginx_path': '/home/docker/nginx',
    'nginx_container': 'nginx',
    'nginx_network': 'ql_net',
}


def base64_urlsafe_encode(data):
    return base64.urlsafe_b64encode(data)


def _get_fernet():
    key = hashlib.sha256(JWT_SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _default_servers():
    return [
        {"id": "local", "name": "本机", "type": "local"}
    ]


def load_servers():
    """Load servers from file"""
    if not os.path.exists(SERVERS_FILE):
        os.makedirs(os.path.dirname(SERVERS_FILE), exist_ok=True)
        save_servers(_default_servers())
        return _default_servers()

    try:
        with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Handle both {"servers": [...]} and [...] formats
            if isinstance(data, dict) and 'servers' in data:
                return data['servers']
            if isinstance(data, list):
                return data
            return _default_servers()
    except (json.JSONDecodeError, IOError):
        return _default_servers()


def save_servers(servers):
    """Save servers to file"""
    os.makedirs(os.path.dirname(SERVERS_FILE), exist_ok=True)
    with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(servers, f, ensure_ascii=False, indent=2)


def list_servers():
    """List all servers (passwords masked)"""
    servers = load_servers()
    result = []
    for s in servers:
        item = {k: v for k, v in s.items() if k != 'password'}
        if s.get('type') == 'remote':
            for key, value in DEFAULT_REMOTE_NGINX.items():
                item.setdefault(key, value)
        if 'password' in s:
            item['has_password'] = bool(s['password'])
        result.append(item)
    return result


def add_server(name, host, port=22, username='root', password='', path='/home/docker/qinglong'):
    """Add a new server"""
    servers = load_servers()

    # Generate ID
    server_id = f"remote_{host}-{port}".replace('.', '-')
    if any(item.get('id') == server_id for item in servers):
        raise ValueError('该服务器已经存在')

    server = {
        "id": server_id,
        "name": name or server_id,
        "type": "remote",
        "host": host,
        "port": port,
        "username": username,
        "path": path,
        **DEFAULT_REMOTE_NGINX,
    }

    # Encrypt password
    if password:
        f = _get_fernet()
        server['password'] = f.encrypt(password.encode()).decode()

    servers.append(server)
    save_servers(servers)
    return server


def update_server(server_id, **kwargs):
    """Update a server"""
    servers = load_servers()

    for i, s in enumerate(servers):
        if s['id'] == server_id:
            if s.get('type') == 'local':
                if kwargs.get('name'):
                    s['name'] = str(kwargs['name']).strip()
                servers[i] = s
                save_servers(servers)
                return s

            text_fields = (
                'name', 'host', 'username', 'path', 'nginx_image',
                'nginx_path', 'nginx_container', 'nginx_network',
            )
            for field in text_fields:
                if field in kwargs and str(kwargs[field]).strip():
                    s[field] = str(kwargs[field]).strip()
            if 'port' in kwargs and kwargs['port'] not in (None, ''):
                port = int(kwargs['port'])
                if port < 1 or port > 65535:
                    raise ValueError('SSH 端口必须在 1 到 65535 之间')
                s['port'] = port
            if 'nginx_port' in kwargs and kwargs['nginx_port'] not in (None, ''):
                nginx_port = int(kwargs['nginx_port'])
                if nginx_port < 1 or nginx_port > 65535:
                    raise ValueError('Nginx 端口必须在 1 到 65535 之间')
                s['nginx_port'] = nginx_port
            if kwargs.get('password'):
                f = _get_fernet()
                s['password'] = f.encrypt(kwargs['password'].encode()).decode()

            servers[i] = s
            save_servers(servers)
            return s

    return None


def delete_server(server_id):
    """Delete a server (cannot delete local)"""
    if server_id == 'local':
        raise Exception('不能删除本机服务器')

    servers = load_servers()
    servers = [s for s in servers if s['id'] != server_id]
    save_servers(servers)
    return True


def get_server(server_id):
    """Get server details (with decrypted password)"""
    servers = load_servers()

    for s in servers:
        if s['id'] == server_id:
            s = dict(s)
            if s.get('type') == 'local':
                return s
            for key, value in DEFAULT_REMOTE_NGINX.items():
                s.setdefault(key, value)
            # Decrypt password
            if s.get('password'):
                try:
                    f = _get_fernet()
                    s['password'] = f.decrypt(s['password'].encode()).decode()
                except Exception:
                    s['password'] = ''
            return s

    return None
