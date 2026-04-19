#!/bin/sh
set -e

# Sustituir ${PORT} en la plantilla de nginx
sed "s/\${PORT}/${PORT:-8080}/g" /etc/nginx/nginx.conf.template > /tmp/nginx.conf

# Directorios que nginx necesita en escritura
mkdir -p /tmp/nginx/client_body /tmp/nginx/proxy /tmp/nginx/fastcgi /tmp/nginx/uwsgi /tmp/nginx/scgi
mkdir -p /var/log/nginx

exec supervisord -n -c /etc/supervisor/conf.d/apps.conf
