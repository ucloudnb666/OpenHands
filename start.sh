#!/bin/bash
set -e
export RUNTIME=local
export INSTALL_DOCKER=0

# Ensure /run/.containerenv doesn't exist
rm -f /run/.containerenv

# Setup nginx for websocket proxying
ln -sf /etc/nginx/sites-available/openhands /etc/nginx/sites-enabled/openhands
rm -f /etc/nginx/sites-enabled/default
nginx -s stop 2>/dev/null || true
sleep 1
nginx

exec make run
