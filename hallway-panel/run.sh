#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

CONFIG_DIR=/config
PANEL_CONFIG="${CONFIG_DIR}/panel.yaml"

# The bundled panel.yaml is only ever a seed. Copying it out to the mapped
# config directory means edits survive rebuilding the add-on, and the File
# editor add-on can reach it at /addon_configs/hallway_panel/panel.yaml.
if ! bashio::fs.file_exists "${PANEL_CONFIG}"; then
    bashio::log.info "First start: installing the default panel.yaml"
    mkdir -p "${CONFIG_DIR}"
    cp /app/panel.yaml "${PANEL_CONFIG}"
    bashio::log.notice "Edit /addon_configs/hallway_panel/panel.yaml, then restart"
fi

export PANEL_CONFIG

# Supplied because homeassistant_api is on in config.yaml. No long-lived token
# needs creating, and none is stored anywhere.
export HA_BASE_URL="http://supervisor/core"
export HA_TOKEN="${SUPERVISOR_TOKEN}"

export PANEL_HOST="0.0.0.0"
export PANEL_PORT="8099"

# bashio::config reads through the Supervisor API rather than straight off
# /data/options.json, so it can fail transiently. Falling back to the manifest
# defaults keeps a blip from taking the panel down over a log level -- under
# `set -e` an unguarded read would kill the container before the server starts.
export PANEL_LOG="$(bashio::config 'log_level' || echo info)"
export PANEL_CACHE_SECONDS="$(bashio::config 'cache_seconds' || echo 45)"

# Deliberately not bashio::network.ipv4_address here: that calls the Supervisor
# API, which this add-on does not ask for, and under `set -e` a failure would
# take the container down over a log line.
bashio::log.info "Config:  ${PANEL_CONFIG}"
bashio::log.info "Serving on port 8099 -- open /preview in a browser"

cd /app
exec python3 serve.py
