from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_socketio import SocketIO, emit
from config import Config
from docker_manager import list_instances, create_instance, start_instance, stop_instance, reset_instance, delete_instance, purge_instance, get_logs, get_nginx_status, create_nginx_container, start_nginx_container, stop_nginx_container, restart_nginx_container
from server_manager import list_servers, add_server, update_server, delete_server, get_server
from remote_docker import check_connection as remote_check
import remote_docker
from auth import login, check_rate_limit
import json
import os


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/socket.io/*": {"origins": "*"}})

    # JWT
    JWTManager(app)

    # SocketIO
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

    # Instance metadata
    METADATA_FILE = os.path.join(Config.PANEL_DATA_DIR, 'instance_metadata.json')

    def load_metadata():
        if not os.path.exists(METADATA_FILE):
            return {}
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def save_metadata(metadata):
        os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def metadata_key(server_id, num):
        return f"{server_id}:{num}"

    def _get_client_ip():
        """获取客户端真实 IP"""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or 'unknown'

    def _get_remote_server(server_id):
        """获取远程服务器配置，本机返回 None"""
        if server_id == 'local':
            return None
        server = get_server(server_id)
        if not server:
            raise ValueError("服务器不存在")
        if server['type'] != 'remote':
            raise ValueError("非远程服务器")
        return server

    # ========== 引导页（无需认证） ==========
    @app.route('/api/nav')
    def api_nav():
        """动态生成 nginx 引导页，列出所有运行中的青龙实例"""
        try:
            instances = list_instances()
            # 只显示运行中的实例（ql0 不走 nginx 代理，也列出）
            running = [i for i in instances if i['status'] == 'running']
            running.sort(key=lambda x: x['id'])

            # 获取当前请求的 hostname
            host = request.host

            # 生成实例链接 HTML
            links_html = ''
            for inst in running:
                # 所有实例都通过 nginx 代理访问（QlBaseUrl 模式）
                links_html += f'<a href="/ql{inst["id"]}/" class="instance-link"><span class="instance-name">Qinglong {inst["id"]}</span><span class="instance-port">/ql{inst["id"]}/</span></a>\n'

            if not running:
                links_html = '<div class="empty-msg">暂无运行中的实例</div>'

            html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qinglong Panels</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    text-align: center;
    background: #f0f2f5;
    min-height: 100vh;
    padding: 40px 20px;
}}
h1 {{
    font-size: 28px;
    color: #1a1a1a;
    margin-bottom: 8px;
    font-weight: 600;
}}
.subtitle {{
    color: #999;
    font-size: 14px;
    margin-bottom: 30px;
}}
.instance-list {{
    max-width: 500px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
}}
.instance-link {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 20px;
    background: #fff;
    border-radius: 8px;
    text-decoration: none;
    color: #333;
    font-size: 16px;
    border: 1px solid #e8e8e8;
    transition: all 0.2s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}}
.instance-link:hover {{
    border-color: #1890ff;
    box-shadow: 0 2px 8px rgba(24,144,255,0.15);
    transform: translateY(-1px);
}}
.instance-name {{
    font-weight: 500;
}}
.instance-port {{
    font-size: 13px;
    color: #999;
}}
.empty-msg {{
    color: #999;
    font-size: 15px;
    padding: 30px;
}}
.footer {{
    margin-top: 40px;
    color: #ccc;
    font-size: 12px;
}}
</style>
</head>
<body>
<h1>Qinglong Panels</h1>
<p class="subtitle">共 {len(running)} 个实例运行中</p>
<div class="instance-list">
{links_html}
</div>
<p class="footer">自动检测运行中的实例 · 实时更新</p>
</body>
</html>'''

            return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
        except Exception as e:
            return f'<html><body><h2>加载失败: {str(e)}</h2></body></html>', 500, {'Content-Type': 'text/html; charset=utf-8'}

    # ========== 健康检查 ==========
    @app.route('/api/health')
    def health():
        return jsonify({"status": "ok"})

    # ========== 登录 ==========
    @app.route('/api/login', methods=['POST'])
    def api_login():
        ip = _get_client_ip()
        data = request.get_json(silent=True) or {}
        username = data.get('username', '')
        password = data.get('password', '')

        try:
            token, attempts_left = login(username, password, ip)
        except PermissionError as e:
            return jsonify({"error": str(e)}), 429

        if token:
            return jsonify({"token": token})

        # 计算剩余尝试次数
        return jsonify({
            "error": "用户名或密码错误",
            "attempts_left": max(0, attempts_left if attempts_left is not None else 0)
        }), 401

    # ========== 服务器管理 ==========
    @app.route('/api/servers')
    @jwt_required()
    def api_list_servers():
        try:
            return jsonify(list_servers())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers', methods=['POST'])
    @jwt_required()
    def api_add_server():
        data = request.get_json(silent=True) or {}
        name = data.get('name', '').strip()
        host = data.get('host', '').strip()
        port = data.get('port', 22)
        username = data.get('username', 'root').strip()
        password = data.get('password', '')
        path = data.get('path', '/home/docker/qinglong').strip()

        if not name or not host:
            return jsonify({"error": "服务器名称和地址不能为空"}), 400

        # 先测试连接
        ok, msg = remote_check(host, port, username, password)
        if not ok:
            return jsonify({"error": f"连接测试失败: {msg}"}), 400

        try:
            result = add_server(name, host, port, username, password, path)
            return jsonify(result), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>', methods=['PUT'])
    @jwt_required()
    def api_update_server(server_id):
        data = request.get_json(silent=True) or {}
        try:
            update_server(server_id, **data)
            return jsonify({"msg": "更新成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>', methods=['DELETE'])
    @jwt_required()
    def api_delete_server(server_id):
        try:
            delete_server(server_id)
            return jsonify({"msg": "删除成功"})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/test', methods=['POST'])
    @jwt_required()
    def api_test_server(server_id):
        server = get_server(server_id)
        if not server:
            return jsonify({"error": "服务器不存在"}), 404
        if server['type'] == 'local':
            return jsonify({"ok": True, "msg": "本机服务器"})
        ok, msg = remote_check(server['host'], server.get('port', 22), server.get('username', 'root'), server.get('password', ''))
        return jsonify({"ok": ok, "msg": msg})

    # ========== 实例管理（按服务器） ==========
    @app.route('/api/servers/<server_id>/instances')
    @jwt_required()
    def api_instances(server_id):
        try:
            remote = _get_remote_server(server_id)
            if remote:
                instances = remote_docker.list_instances(remote)
            else:
                instances = list_instances()

            # Enrich with metadata
            metadata = load_metadata()
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            for inst in instances:
                key = metadata_key(server_id, inst['id'])
                meta = metadata.get(key, {})
                inst['start_date'] = meta.get('start_date', '')
                inst['end_date'] = meta.get('end_date', '')
                inst['notes'] = meta.get('notes', '')
                # use_nginx: 默认 True（兼容历史数据），仅本地服务器有效
                inst['use_nginx'] = meta.get('use_nginx', True)
                # Auto-detect expired
                if inst['end_date'] and inst['end_date'] < today and inst['status'] == 'running':
                    inst['expired'] = True
                else:
                    inst['expired'] = False

            return jsonify(instances)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/instances/<int:num>/metadata', methods=['PUT'])
    @jwt_required()
    def api_update_metadata(server_id, num):
        """Update instance metadata (start_date, end_date, notes, use_nginx)"""
        data = request.get_json(silent=True) or {}
        metadata = load_metadata()
        key = metadata_key(server_id, num)

        if key not in metadata:
            metadata[key] = {}

        if 'start_date' in data:
            metadata[key]['start_date'] = data['start_date']
        if 'end_date' in data:
            metadata[key]['end_date'] = data['end_date']
        if 'notes' in data:
            metadata[key]['notes'] = data['notes']
        if 'use_nginx' in data:
            metadata[key]['use_nginx'] = bool(data['use_nginx'])
            # use_nginx 变更后需要更新 nginx 配置
            if server_id == 'local':
                from docker_manager import _update_nginx_config
                _update_nginx_config()

        save_metadata(metadata)
        return jsonify({"message": "更新成功", "metadata": metadata[key]})

    @app.route('/api/servers/<server_id>/create/<int:num>', methods=['POST'])
    @jwt_required()
    def api_create(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            data = request.get_json(silent=True) or {}
            use_nginx = data.get('use_nginx', True)

            if remote:
                remote_docker.create_instance(remote, num)
            else:
                create_instance(num, use_nginx=use_nginx)

            # Save metadata if provided
            if data.get('start_date') or data.get('end_date') or data.get('notes') or 'use_nginx' in data:
                metadata = load_metadata()
                key = metadata_key(server_id, num)
                if key not in metadata:
                    metadata[key] = {}
                if data.get('start_date'):
                    metadata[key]['start_date'] = data.get('start_date', '')
                if data.get('end_date'):
                    metadata[key]['end_date'] = data.get('end_date', '')
                if data.get('notes') is not None:
                    metadata[key]['notes'] = data.get('notes', '')
                metadata[key]['use_nginx'] = use_nginx
                save_metadata(metadata)

            return jsonify({"msg": "创建成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/start/<int:num>', methods=['POST'])
    @jwt_required()
    def api_start(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            if remote:
                remote_docker.start_instance(remote, num)
            else:
                start_instance(num)
            return jsonify({"msg": "启动成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/stop/<int:num>', methods=['POST'])
    @jwt_required()
    def api_stop(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            if remote:
                remote_docker.stop_instance(remote, num)
            else:
                stop_instance(num)
            return jsonify({"msg": "停止成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/reset/<int:num>', methods=['POST'])
    @jwt_required()
    def api_reset(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            data = request.get_json(silent=True) or {}
            use_nginx = data.get('use_nginx', True)

            if remote:
                remote_docker.reset_instance(remote, num)
            else:
                reset_instance(num, use_nginx=use_nginx)

            # 更新元数据中的 use_nginx
            metadata = load_metadata()
            key = metadata_key(server_id, num)
            if key not in metadata:
                metadata[key] = {}
            metadata[key]['use_nginx'] = use_nginx
            save_metadata(metadata)

            return jsonify({"msg": "重置成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/delete/<int:num>', methods=['DELETE'])
    @jwt_required()
    def api_delete(server_id, num):
        """删除实例（仅删除容器，保留数据）"""
        try:
            remote = _get_remote_server(server_id)
            if remote:
                remote_docker.delete_instance(remote, num)
            else:
                delete_instance(num)

            # Clean metadata
            metadata = load_metadata()
            key = metadata_key(server_id, num)
            if key in metadata:
                del metadata[key]
                save_metadata(metadata)

            return jsonify({"msg": "删除成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/purge/<int:num>', methods=['DELETE'])
    @jwt_required()
    def api_purge(server_id, num):
        """彻底删除实例（删除容器 + 数据目录）"""
        try:
            remote = _get_remote_server(server_id)
            if remote:
                remote_docker.purge_instance(remote, num)
            else:
                purge_instance(num)

            # Clean metadata
            metadata = load_metadata()
            key = metadata_key(server_id, num)
            if key in metadata:
                del metadata[key]
                save_metadata(metadata)

            return jsonify({"msg": "彻底删除成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/logs/<int:num>')
    @jwt_required()
    def api_logs(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            if remote:
                logs = remote_docker.get_logs(remote, num)
            else:
                logs = get_logs(num)
            return jsonify({"logs": logs})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ========== 批量操作 ==========
    @app.route('/api/servers/<server_id>/batch/<action>', methods=['POST'])
    @jwt_required()
    def api_batch_action(server_id, action):
        """批量操作: start, stop, reset, delete, purge"""
        if action not in ('start', 'stop', 'reset', 'delete', 'purge'):
            return jsonify({"error": "不支持的操作"}), 400

        data = request.get_json(silent=True) or {}
        nums = data.get('nums', [])
        use_nginx = data.get('use_nginx', True)
        if not nums:
            return jsonify({"error": "请选择至少一个实例"}), 400

        remote = _get_remote_server(server_id)
        results = {"success": [], "failed": []}

        for num in nums:
            try:
                if action == 'start':
                    if remote:
                        remote_docker.start_instance(remote, num)
                    else:
                        start_instance(num)
                elif action == 'stop':
                    if remote:
                        remote_docker.stop_instance(remote, num)
                    else:
                        stop_instance(num)
                elif action == 'reset':
                    if remote:
                        remote_docker.reset_instance(remote, num)
                    else:
                        reset_instance(num, use_nginx=use_nginx)
                    # 更新元数据中的 use_nginx
                    metadata = load_metadata()
                    key = metadata_key(server_id, num)
                    if key not in metadata:
                        metadata[key] = {}
                    metadata[key]['use_nginx'] = use_nginx
                    save_metadata(metadata)
                elif action == 'delete':
                    if remote:
                        remote_docker.delete_instance(remote, num)
                    else:
                        delete_instance(num)
                    # Clean metadata for deleted
                    metadata = load_metadata()
                    key = metadata_key(server_id, num)
                    if key in metadata:
                        del metadata[key]
                        save_metadata(metadata)
                elif action == 'purge':
                    if remote:
                        remote_docker.purge_instance(remote, num)
                    else:
                        purge_instance(num)
                    # Clean metadata for purged
                    metadata = load_metadata()
                    key = metadata_key(server_id, num)
                    if key in metadata:
                        del metadata[key]
                        save_metadata(metadata)
                results["success"].append(num)
            except Exception as e:
                results["failed"].append({"num": num, "error": str(e)})

        action_names = {"start": "启动", "stop": "停止", "reset": "重置", "delete": "删除", "purge": "彻底删除"}
        msg = f"批量{action_names[action]}完成: 成功{len(results['success'])}个"
        if results["failed"]:
            msg += f", 失败{len(results['failed'])}个"
        return jsonify({"msg": msg, "results": results})

    # ========== Nginx 容器管理 ==========
    @app.route('/api/servers/<server_id>/nginx')
    @jwt_required()
    def api_nginx_status(server_id):
        """获取 nginx 容器状态"""
        try:
            if server_id != 'local':
                return jsonify({"error": "暂不支持远程服务器nginx管理"}), 400
            status = get_nginx_status()
            return jsonify(status)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/nginx/<action>', methods=['POST'])
    @jwt_required()
    def api_nginx_action(server_id, action):
        """nginx 容器操作: start, stop, restart, create"""
        if server_id != 'local':
            return jsonify({"error": "暂不支持远程服务器nginx管理"}), 400

        try:
            if action == 'start':
                result = start_nginx_container()
            elif action == 'stop':
                result = stop_nginx_container()
            elif action == 'restart':
                result = restart_nginx_container()
            elif action == 'create':
                result = create_nginx_container()
            else:
                return jsonify({"error": "不支持的操作"}), 400
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ========== SocketIO ==========
    @socketio.on('connect')
    def on_connect():
        emit('connected', {'data': 'Connected'})

    @socketio.on('disconnect')
    def on_disconnect():
        print('Client disconnected')

    @socketio.on('request_logs')
    def handle_log_request(data):
        num = data.get('id')
        server_id = data.get('server_id', 'local')
        if num is not None:
            try:
                remote = _get_remote_server(server_id)
                if remote:
                    logs = remote_docker.get_logs(remote, num, tail=100)
                else:
                    logs = get_logs(num, tail=100)
                emit('log_update', {'id': num, 'logs': logs})
            except Exception as e:
                emit('log_update', {'id': num, 'logs': f'错误: {str(e)}'})

    return app, socketio


app, socketio = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
