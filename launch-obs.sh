#!/usr/bin/env bash
# Launch OBS. Bridge (zmk-bridge.service) runs permanently — do not start duplicates.

# Ensure the bridge is running (starts it if stopped, no-op if already running)
systemctl --user start zmk-bridge.service

__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia obs "$@"
