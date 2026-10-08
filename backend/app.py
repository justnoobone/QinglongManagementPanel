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
import html as html_lib
from metadata_store import load_metadata, metadata_transaction
from expiry_scheduler import start_expiry_scheduler
from expiry_rules import blocks_start, local_today, parse_date


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

    def metadata_key(server_id, num):
        return f"{server_id}:{num}"

    def update_instance_metadata(server_id, num, values):
        with metadata_transaction() as metadata:
            item = metadata.setdefault(metadata_key(server_id, num), {})
            item.update(values)
            return dict(item)

    def remove_instance_metadata(server_id, num):
        with metadata_transaction() as metadata:
            metadata.pop(metadata_key(server_id, num), None)

    def disabled_nginx_ids(server_id):
        prefix = f"{server_id}:"
        disabled = []
        for key, value in load_metadata().items():
            if key.startswith(prefix) and value.get('use_nginx', True) is False:
                try:
                    disabled.append(int(key.split(':', 1)[1]))
                except (TypeError, ValueError):
                    continue
        return disabled

    def sync_remote_nginx(server_id, remote):
        """Refresh a running remote Nginx after instance/metadata changes.

        Nginx may have been deployed before the first Qinglong instance was
        created. In that case its old config legitimately contains no routes;
        lifecycle operations must regenerate it after the container exists.
        """
        if not remote:
            return {}
        status = remote_docker.get_nginx_status(remote)
        if not status.get('exists') or status.get('status') != 'running':
            return {}
        try:
            return {
                'nginx_sync': remote_docker.sync_nginx_config(
                    remote,
                    disabled_ids=disabled_nginx_ids(server_id),
                )
            }
        except Exception as exc:
            app.logger.exception('Remote Nginx sync failed for %s', server_id)
            return {
                'warning': f'实例操作已完成，但代理配置同步失败：{exc}。请重新执行 Nginx 部署。'
            }

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
            metadata = load_metadata()
            running = [
                instance for instance in instances
                if instance['status'] == 'running'
                and metadata.get(metadata_key('local', instance['id']), {}).get('use_nginx', True)
            ]
            running.sort(key=lambda x: x['id'])

            links_html = ''
            for inst in running:
                name = html_lib.escape(inst['name'])
                links_html += f'''<a href="/ql{inst["id"]}/" class="instance-link">
<span class="instance-main"><span class="status-dot"></span><span><strong>{name}</strong><small>Qinglong instance {inst["id"]}</small></span></span>
<span class="instance-path">/ql{inst["id"]}/ <span aria-hidden="true">&#8599;</span></span>
</a>\n'''

            if not running:
                links_html = '<div class="empty-msg"><strong>暂无在线实例</strong><span>请打开管理控制台检查 Docker 连接与容器状态。</span></div>'

            hostname = request.host.split(':', 1)[0]
            panel_url = f'http://{hostname}/'

            html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>青龙实例入口</title>
<style>
* {{ box-sizing: border-box; letter-spacing: 0; }}
body {{
    margin: 0;
    min-height: 100vh;
    color: #1d1d1f;
    background: #f5f5f7;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
}}
.topbar {{
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 max(20px, calc((100vw - 760px) / 2));
    background: rgba(250,250,252,.88);
    border-bottom: 1px solid rgba(0,0,0,.08);
    backdrop-filter: saturate(180%) blur(18px);
}}
.brand {{ display: flex; align-items: center; gap: 10px; font-weight: 650; }}
.brand-mark {{
    width: 36px; height: 36px; display: grid; place-items: center;
    color: #fff; background: #3a3a3c; border-radius: 8px; font-size: 14px;
}}
.console-link {{
    padding: 8px 12px; color: #0071e3; background: #fff; border: 1px solid #dedee3;
    border-radius: 7px; font-size: 12px; font-weight: 600; text-decoration: none;
}}
main {{ width: min(720px, calc(100% - 32px)); margin: 0 auto; padding: 56px 0; }}
.eyebrow {{ margin: 0 0 8px; color: #98989d; font-size: 10px; font-weight: 700; }}
h1 {{ margin: 0; font-size: 30px; font-weight: 650; }}
.subtitle {{ margin: 8px 0 26px; color: #6e6e73; font-size: 14px; }}
.instance-list {{ display: grid; gap: 10px; }}
.instance-link {{
    min-height: 74px; display: flex; align-items: center; justify-content: space-between;
    gap: 16px; padding: 14px 16px; color: #1d1d1f; background: #fff;
    border: 1px solid #e5e5e8; border-radius: 8px; text-decoration: none;
    box-shadow: 0 1px 2px rgba(0,0,0,.03); transition: border-color .16s, transform .16s;
}}
.instance-link:hover {{ border-color: #8fc4f5; transform: translateY(-1px); }}
.instance-main {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
.instance-main strong, .instance-main small {{ display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.instance-main strong {{ font-size: 14px; }}
.instance-main small {{ margin-top: 4px; color: #98989d; font-size: 11px; }}
.status-dot {{ width: 8px; height: 8px; flex: 0 0 auto; border-radius: 50%; background: #30a14e; box-shadow: 0 0 0 4px rgba(48,161,78,.12); }}
.instance-path {{ color: #0071e3; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; white-space: nowrap; }}
.empty-msg {{
    min-height: 180px; display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 30px; color: #6e6e73; background: #fff;
    border: 1px solid #e5e5e8; border-radius: 8px; text-align: center;
}}
.empty-msg strong {{ color: #1d1d1f; font-size: 15px; }}
.empty-msg span {{ margin-top: 7px; font-size: 12px; }}
.footer {{ margin: 24px 0 0; color: #98989d; font-size: 11px; text-align: center; }}
@media (max-width: 560px) {{
    .topbar {{ padding: 0 16px; }}
    main {{ padding: 34px 0; }}
    h1 {{ font-size: 25px; }}
    .instance-path {{ font-size: 10px; }}
}}
</style>
</head>
<body>
<header class="topbar"><div class="brand"><span class="brand-mark">QL</span><span>青龙实例</span></div><a class="console-link" href="{panel_url}">管理控制台</a></header>
<main>
<p class="eyebrow">QINGLONG PANELS</p>
<h1>选择一个运行实例</h1>
<p class="subtitle">当前共有 {len(running)} 个实例在线</p>
<div class="instance-list">
{links_html}
</div>
<p class="footer">状态来自本机 Docker 服务</p>
</main>
</body>
</html>'''

            return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
        except Exception as e:
            error = html_lib.escape(str(e))
            return f'<html><body><h2>加载失败: {error}</h2></body></html>', 500, {'Content-Type': 'text/html; charset=utf-8'}

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
        try:
            port = int(data.get('port', 22))
        except (TypeError, ValueError):
            return jsonify({"error": "SSH 端口格式不正确"}), 400
        username = data.get('username', 'root').strip()
        password = data.get('password', '')
        path = data.get('path', '/home/docker/qinglong').strip()

        if not name or not host:
            return jsonify({"error": "服务器名称和地址不能为空"}), 400
        if port < 1 or port > 65535:
            return jsonify({"error": "SSH 端口必须在 1 到 65535 之间"}), 400

        # 先测试连接
        ok, msg = remote_check(host, port, username, password)
        if not ok:
            return jsonify({"error": f"连接测试失败: {msg}"}), 400

        try:
            result = add_server(name, host, port, username, password, path)
            public_result = next((item for item in list_servers() if item['id'] == result['id']), None)
            return jsonify(public_result or {'id': result['id'], 'name': result['name']}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>', methods=['PUT'])
    @jwt_required()
    def api_update_server(server_id):
        data = request.get_json(silent=True) or {}
        try:
            result = update_server(server_id, **data)
            if not result:
                return jsonify({"error": "服务器不存在"}), 404
            public_result = next((item for item in list_servers() if item['id'] == server_id), None)
            return jsonify({"msg": "更新成功", "server": public_result})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
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
            today = local_today().isoformat()
            for inst in instances:
                key = metadata_key(server_id, inst['id'])
                meta = metadata.get(key, {})
                inst['start_date'] = meta.get('start_date', '')
                inst['end_date'] = meta.get('end_date', '')
                inst['notes'] = meta.get('notes', '')
                inst['expiry_state'] = meta.get('expiry_state', '')
                inst['stopped_by_expiry'] = meta.get('stopped_by_expiry', False)
                inst['last_expiry_error'] = meta.get('last_expiry_error', '')
                # use_nginx 默认 True，远程 Nginx 部署时也使用此开关。
                inst['use_nginx'] = meta.get('use_nginx', True)
                inst['expired'] = bool(inst['end_date'] and inst['end_date'] <= today)
                inst['start_blocked'] = blocks_start(meta) if server_id == 'local' else False

            return jsonify(instances)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/instances/<int:num>/metadata', methods=['PUT'])
    @jwt_required()
    def api_update_metadata(server_id, num):
        """Update instance metadata (start_date, end_date, notes, use_nginx)"""
        data = request.get_json(silent=True) or {}
        if 'end_date' in data:
            try:
                parsed_end = parse_date(data.get('end_date'))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            normalized_end = parsed_end.isoformat() if parsed_end else ''
        else:
            normalized_end = None

        key = metadata_key(server_id, num)
        with metadata_transaction() as metadata:
            item = metadata.setdefault(key, {})
            if server_id == 'local' and normalized_end is not None and blocks_start(item):
                if not normalized_end or normalized_end <= local_today().isoformat():
                    return jsonify({
                        "error": "实例已过期，只能设置晚于今天的新到期日期",
                        "code": "INSTANCE_EXPIRED",
                    }), 409
            if 'start_date' in data:
                item['start_date'] = data['start_date']
            if normalized_end is not None:
                item['end_date'] = normalized_end
                item['expiry_state'] = 'scheduled' if normalized_end else 'cleared'
                if normalized_end and normalized_end > local_today().isoformat():
                    item['stopped_by_expiry'] = False
                    item['last_expiry_error'] = ''
            if 'notes' in data:
                item['notes'] = data['notes']
            if 'use_nginx' in data:
                item['use_nginx'] = bool(data['use_nginx'])

            saved_metadata = dict(item)

        nginx_result = {}
        if 'use_nginx' in data:
            # use_nginx 变更后需要更新 nginx 配置
            if server_id == 'local':
                from docker_manager import _update_nginx_config
                _update_nginx_config()
            else:
                nginx_result = sync_remote_nginx(server_id, _get_remote_server(server_id))

        if server_id == 'local' and normalized_end and normalized_end <= local_today().isoformat():
            from expiry_scheduler import run_expiry_check
            run_expiry_check()
            saved_metadata = load_metadata().get(key, saved_metadata)

        return jsonify({"message": "更新成功", "metadata": saved_metadata, **nginx_result})

    @app.route('/api/servers/<server_id>/create/<int:num>', methods=['POST'])
    @jwt_required()
    def api_create(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            data = request.get_json(silent=True) or {}
            if data.get('end_date'):
                data['end_date'] = parse_date(data['end_date']).isoformat()
            use_nginx = data.get('use_nginx', True)
            image = data.get('image') or None
            cpu_limit = data.get('cpu_limit') or None
            mem_limit = data.get('mem_limit') or None

            if remote:
                remote_docker.create_instance(
                    remote,
                    num,
                    image=image,
                    cpu_limit=cpu_limit,
                    mem_limit=mem_limit,
                    use_nginx=use_nginx,
                )
            else:
                create_instance(num, use_nginx=use_nginx, image=image, cpu_limit=cpu_limit, mem_limit=mem_limit)

            # Persist the proxy switch before regenerating remote routes.
            values = {'use_nginx': use_nginx}
            if data.get('start_date'):
                values['start_date'] = data.get('start_date', '')
            if data.get('end_date'):
                values['end_date'] = data.get('end_date', '')
                values['expiry_state'] = 'scheduled'
            if data.get('notes') is not None:
                values['notes'] = data.get('notes', '')
            update_instance_metadata(server_id, num, values)

            if server_id == 'local' and data.get('end_date') and data['end_date'] <= local_today().isoformat():
                from expiry_scheduler import run_expiry_check
                run_expiry_check()

            return jsonify({"msg": "创建成功", **sync_remote_nginx(server_id, remote)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/start/<int:num>', methods=['POST'])
    @jwt_required()
    def api_start(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            if not remote:
                metadata = load_metadata().get(metadata_key(server_id, num), {})
                if blocks_start(metadata):
                    return jsonify({
                        "error": "实例已过期，请先设置晚于今天的到期日期后再启动",
                        "code": "INSTANCE_EXPIRED",
                    }), 409
            if remote:
                remote_docker.start_instance(remote, num)
            else:
                start_instance(num)
            return jsonify({"msg": "启动成功", **sync_remote_nginx(server_id, remote)})
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
            return jsonify({"msg": "停止成功", **sync_remote_nginx(server_id, remote)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/reset/<int:num>', methods=['POST'])
    @jwt_required()
    def api_reset(server_id, num):
        try:
            remote = _get_remote_server(server_id)
            if not remote:
                metadata = load_metadata().get(metadata_key(server_id, num), {})
                if blocks_start(metadata):
                    return jsonify({
                        "error": "实例已过期，请先设置晚于今天的到期日期后再重置",
                        "code": "INSTANCE_EXPIRED",
                    }), 409
            data = request.get_json(silent=True) or {}
            use_nginx = data.get('use_nginx', True)
            image = data.get('image') or None
            cpu_limit = data.get('cpu_limit') or None
            mem_limit = data.get('mem_limit') or None

            if remote:
                remote_docker.reset_instance(
                    remote,
                    num,
                    image=image,
                    cpu_limit=cpu_limit,
                    mem_limit=mem_limit,
                    use_nginx=use_nginx,
                )
            else:
                reset_instance(num, use_nginx=use_nginx, image=image, cpu_limit=cpu_limit, mem_limit=mem_limit)

            # 更新元数据中的 use_nginx
            update_instance_metadata(server_id, num, {'use_nginx': use_nginx})

            return jsonify({"msg": "重置成功", **sync_remote_nginx(server_id, remote)})
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
            remove_instance_metadata(server_id, num)

            return jsonify({"msg": "删除成功", **sync_remote_nginx(server_id, remote)})
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
            remove_instance_metadata(server_id, num)

            return jsonify({"msg": "彻底删除成功", **sync_remote_nginx(server_id, remote)})
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
        image = data.get('image') or None
        cpu_limit = data.get('cpu_limit') or None
        mem_limit = data.get('mem_limit') or None
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
                        item = load_metadata().get(metadata_key(server_id, num), {})
                        if blocks_start(item):
                            raise ValueError('实例已过期，请先设置晚于今天的到期日期后再启动')
                        start_instance(num)
                elif action == 'stop':
                    if remote:
                        remote_docker.stop_instance(remote, num)
                    else:
                        stop_instance(num)
                elif action == 'reset':
                    if remote:
                        remote_docker.reset_instance(
                            remote,
                            num,
                            image=image,
                            cpu_limit=cpu_limit,
                            mem_limit=mem_limit,
                            use_nginx=use_nginx,
                        )
                    else:
                        item = load_metadata().get(metadata_key(server_id, num), {})
                        if blocks_start(item):
                            raise ValueError('实例已过期，请先设置晚于今天的到期日期后再重置')
                        reset_instance(num, use_nginx=use_nginx, image=image, cpu_limit=cpu_limit, mem_limit=mem_limit)
                    # 更新元数据中的 use_nginx
                    update_instance_metadata(server_id, num, {'use_nginx': use_nginx})
                elif action == 'delete':
                    if remote:
                        remote_docker.delete_instance(remote, num)
                    else:
                        delete_instance(num)
                    # Clean metadata for deleted
                    remove_instance_metadata(server_id, num)
                elif action == 'purge':
                    if remote:
                        remote_docker.purge_instance(remote, num)
                    else:
                        purge_instance(num)
                    # Clean metadata for purged
                    remove_instance_metadata(server_id, num)
                results["success"].append(num)
            except Exception as e:
                results["failed"].append({"num": num, "error": str(e)})

        action_names = {"start": "启动", "stop": "停止", "reset": "重置", "delete": "删除", "purge": "彻底删除"}
        msg = f"批量{action_names[action]}完成: 成功{len(results['success'])}个"
        if results["failed"]:
            msg += f", 失败{len(results['failed'])}个"
        nginx_result = {}
        if remote and results['success']:
            nginx_result = sync_remote_nginx(server_id, remote)
        return jsonify({"msg": msg, "results": results, **nginx_result})

    # ========== Nginx 容器管理 ==========
    @app.route('/api/servers/<server_id>/nginx')
    @jwt_required()
    def api_nginx_status(server_id):
        """获取 nginx 容器状态"""
        try:
            remote = _get_remote_server(server_id)
            status = remote_docker.get_nginx_status(remote) if remote else get_nginx_status()
            return jsonify(status)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/nginx/preview')
    @jwt_required()
    def api_nginx_preview(server_id):
        """Preview generated remote Nginx config without changing the server."""
        try:
            remote = _get_remote_server(server_id)
            if not remote:
                from docker_manager import _generate_nginx_config
                return jsonify({"config": _generate_nginx_config(), "mode": "local"})
            config, instances = remote_docker.preview_nginx_config(
                remote,
                disabled_ids=disabled_nginx_ids(server_id),
            )
            return jsonify({
                "config": config,
                "mode": "remote",
                "instances": len(instances),
                "settings": remote_docker.nginx_settings(remote),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/servers/<server_id>/nginx/<action>', methods=['POST'])
    @jwt_required()
    def api_nginx_action(server_id, action):
        """Nginx container actions for local and remote servers."""
        try:
            remote = _get_remote_server(server_id)
            data = request.get_json(silent=True) or {}
            if remote:
                if action == 'start':
                    result = remote_docker.start_nginx(remote)
                    result.update(sync_remote_nginx(server_id, remote))
                elif action == 'stop':
                    result = remote_docker.stop_nginx(remote)
                elif action == 'restart':
                    result = remote_docker.restart_nginx(remote)
                    result.update(sync_remote_nginx(server_id, remote))
                elif action in ('create', 'deploy'):
                    overrides = {
                        'image': data.get('image'),
                        'port': data.get('port'),
                        'path': data.get('path'),
                    }
                    settings = remote_docker.nginx_settings(remote, overrides)
                    result = remote_docker.deploy_nginx(
                        remote,
                        disabled_ids=disabled_nginx_ids(server_id),
                        overrides=overrides,
                    )
                    update_server(
                        server_id,
                        nginx_image=settings['image'],
                        nginx_port=settings['port'],
                        nginx_path=settings['path'],
                    )
                else:
                    return jsonify({"error": "不支持的操作"}), 400
            else:
                if action == 'start':
                    result = start_nginx_container()
                elif action == 'stop':
                    result = stop_nginx_container()
                elif action == 'restart':
                    result = restart_nginx_container()
                elif action in ('create', 'deploy'):
                    result = create_nginx_container()
                else:
                    return jsonify({"error": "不支持的操作"}), 400
            return jsonify(result)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
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
    start_expiry_scheduler()
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
