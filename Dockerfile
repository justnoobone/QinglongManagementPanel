FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --registry=https://registry.npmmirror.com

COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PANEL_DATA_DIR=/qlpanel/data

WORKDIR /qlpanel

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist/ /usr/share/nginx/html/
COPY nginx.single.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /usr/local/bin/ql-panel-entrypoint

RUN chmod +x /usr/local/bin/ql-panel-entrypoint \
    && mkdir -p /qlpanel/data /run/nginx

EXPOSE 80

CMD ["/usr/local/bin/ql-panel-entrypoint"]
