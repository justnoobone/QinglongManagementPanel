"""Shared Nginx configuration generation for local and remote Qinglong hosts."""

import html
import re


CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def normalize_base_url(value):
    """Return a canonical Qinglong base URL such as ``/ql1/`` or ``/``."""
    value = (value or "/").strip()
    if not value.startswith("/"):
        value = f"/{value}"
    if not value.endswith("/"):
        value = f"{value}/"
    return value


def uses_prefixed_base_url(instance):
    """Whether the instance itself understands its expected ``/qlN/`` prefix."""
    expected = f"/ql{int(instance['id'])}/"
    return normalize_base_url(instance.get("ql_base_url")) == expected


def _location_block(instance):
    num = int(instance["id"])
    container_name = str(instance["name"])
    if not CONTAINER_NAME_RE.fullmatch(container_name):
        raise ValueError(f"非法容器名称: {container_name}")

    prefix = f"/ql{num}"
    preserves_prefix = uses_prefixed_base_url(instance)
    upstream_variable = f"$ql{num}_upstream"

    compatibility = ""
    runtime_environment = ""
    rewrite = ""
    mode_comment = "QlBaseUrl prefix mode"
    if not preserves_prefix:
        mode_comment = "root direct mode: inject /qlN/ in the proxied runtime environment"
        runtime_environment = f"""
    location = {prefix}/api/env.js {{
        default_type application/javascript;
        add_header Cache-Control "no-store" always;
        return 200 'window.__ENV__QlBaseUrl="{prefix}/";window.__ENV__QL_DIR="/ql";';
    }}
"""
        rewrite = f"\n        rewrite ^{prefix}/(.*)$ /$1 break;"
        compatibility = f"""
        proxy_set_header X-Forwarded-Prefix {prefix};
        proxy_redirect ~^(/.*)$ {prefix}$1;
        proxy_redirect ~^https?://[^/]+(/.*)$ {prefix}$1;
        proxy_cookie_path / {prefix}/;"""

    return f"""    # {mode_comment}
    location = {prefix} {{
        return 308 {prefix}/;
    }}

{runtime_environment}
    location {prefix}/ {{
        set {upstream_variable} http://{container_name}:5700;{rewrite}
        proxy_pass {upstream_variable};
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;{compatibility}

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_buffering off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }}"""


def _remote_landing_page(instances):
    links = []
    for instance in instances:
        num = int(instance["id"])
        name = html.escape(str(instance["name"]), quote=True)
        links.append(f'<li><a href="/ql{num}/">{name} <small>/ql{num}/</small></a></li>')
    items = "".join(links) or "<li>暂无已启用的青龙实例</li>"
    page = (
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>青龙反向代理</title><style>"
        "body{margin:0;padding:48px;font:16px -apple-system,BlinkMacSystemFont,sans-serif;"
        "color:#1d1d1f;background:#f5f5f7}main{max-width:680px;margin:auto}"
        "h1{font-size:28px}ul{padding:0;list-style:none}li{margin:10px 0}"
        "a{display:flex;justify-content:space-between;padding:16px 18px;color:#1d1d1f;"
        "background:#fff;border:1px solid #dedee3;border-radius:12px;text-decoration:none}"
        "small{color:#0071e3}</style><main><h1>青龙实例入口</h1><ul>"
        f"{items}</ul></main></html>"
    )
    return page.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")


def generate_nginx_config(instances, enabled_ids=None, nav_upstream=None):
    """Generate a complete server block for Qinglong proxy routes.

    Instances with a correct ``QlBaseUrl=/qlN/`` keep the request prefix. Older
    instances automatically use a compatibility route that strips the prefix.
    """
    allowed_ids = None if enabled_ids is None else {int(num) for num in enabled_ids}
    enabled_instances = [
        instance for instance in instances
        if allowed_ids is None or int(instance["id"]) in allowed_ids
    ]
    enabled_instances.sort(key=lambda item: int(item["id"]))
    locations = "\n\n".join(_location_block(instance) for instance in enabled_instances)

    if nav_upstream:
        root_location = f"""    location = / {{
        proxy_pass http://{nav_upstream};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}"""
    else:
        landing_page = _remote_landing_page(enabled_instances)
        root_location = f"""    location = / {{
        default_type text/html;
        return 200 '{landing_page}';
    }}"""

    return f"""# Managed by Qinglong Control. Manual changes may be overwritten.
# Prefixed instances preserve /qlN/. Root-direct instances receive an injected
# browser base URL while Nginx strips /qlN/ before proxying upstream.
server {{
    listen 80;
    server_name _;
    absolute_redirect off;

    resolver 127.0.0.11 valid=10s;
    resolver_timeout 5s;

{root_location}

{locations}
}}
"""
