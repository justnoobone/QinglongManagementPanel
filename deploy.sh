#!/bin/bash
# 部署脚本 - 在服务器上执行
# 用法: 将整个 qinglong-panel 目录上传到服务器后执行

set -e

cd /home/docker/test/qinglong-panel

echo "=== 确保 ql_net 网络存在 ==="
docker network inspect ql_net >/dev/null 2>&1 || docker network create ql_net
echo "ql_net 网络就绪"

echo "=== 停止旧容器 ==="
docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true

echo "=== 重新构建并启动 ==="
docker compose up -d --build

echo "=== 等待服务启动 ==="
sleep 5

echo "=== 测试前端代理登录 ==="
set -a
source ./.env
set +a
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost/api/login -H "Content-Type: application/json" -d "{\"username\":\"${PANEL_USERNAME}\",\"password\":\"${PANEL_PASSWORD}\"}")
echo "前端代理登录测试 HTTP 状态: $HTTP_CODE"

echo "=== 测试引导页API ==="
NAV_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/api/nav)
echo "引导页 API HTTP 状态: $NAV_CODE"

echo "=== 部署完成 ==="
