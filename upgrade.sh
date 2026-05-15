#!/bin/bash
set -e

BASE_DIR="/var/tmp/vibe-kanban/worktrees/23a1-prompt-woow-webs/Woow_odoo_website_auth/podman_docker_app/odoo-websiteauth"
SRC_DIR="/var/tmp/vibe-kanban/worktrees/23a1-prompt-woow-webs/Woow_odoo_website_auth/woow_website_auth"

podman stop odoo-websiteauth-web 2>/dev/null || true

podman run --rm \
  --name odoo-websiteauth-upgrade \
  --network odoo-websiteauth-network \
  -e HOST=db \
  -e PORT=5432 \
  -e USER=odoowebsiteauth \
  -e PASSWORD=odoowebsiteauth \
  -v "${BASE_DIR}/config/odoo.conf:/etc/odoo/odoo.conf:rw" \
  -v "${BASE_DIR}/data/odoo:/var/lib/odoo:rw" \
  -v "${SRC_DIR}:/mnt/extra-addons/woow_website_auth:rw" \
  docker.io/library/odoo:18.0 \
  odoo -d odoowebsiteauth -u woow_website_auth --stop-after-init 2>&1

podman start odoo-websiteauth-web
