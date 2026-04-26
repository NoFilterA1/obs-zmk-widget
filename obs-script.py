"""
ZMK Bridge — OBS Script
=======================
Manages the ZMK keyboard bridge service alongside OBS.

Add via OBS: Tools → Scripts → [+] → select this file.

The bridge service starts when OBS loads the script and stops when OBS exits.
Mode (BLE / any keyboard) is selectable in the script settings panel.
"""

import subprocess
import obspython as obs  # provided by OBS at runtime

# ── State ──────────────────────────────────────────────────────────────────
# zmk-bridge.service is started by launch-obs.sh before OBS loads.
# This script only ensures it's running (no-op if already up) and
# selects BLE vs any-keyboard mode.
_SERVICE_BLE = "zmk-bridge.service"
_SERVICE_ANY = "zmk-bridge-any.service"
_service = _SERVICE_BLE

def _systemctl(action):
    subprocess.Popen(
        ["systemctl", "--user", action, _service],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

# ── OBS script hooks ───────────────────────────────────────────────────────
def script_description():
    return (
        "<b>ZMK Keyboard Widget Bridge</b><br><br>"
        "Ensures the key-bridge service is running with OBS.<br>"
        "Select mode below, then reload the script to apply."
    )

def script_properties():
    props = obs.obs_properties_create()
    mode = obs.obs_properties_add_list(
        props, "mode", "Keyboard mode",
        obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING,
    )
    obs.obs_property_list_add_string(mode, "ZMK BLE (Corne, VTwin…)", _SERVICE_BLE)
    obs.obs_property_list_add_string(mode, "Any keyboard (wired fallback)", _SERVICE_ANY)
    return props

def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "mode", _SERVICE_BLE)

def script_update(settings):
    global _service
    _service = obs.obs_data_get_string(settings, "mode")

def script_load(settings):
    global _service
    _service = obs.obs_data_get_string(settings, "mode")
    obs.script_log(obs.LOG_INFO, f"[zmk] ensuring {_service} is running")
    _systemctl("start")

def script_unload():
    obs.script_log(obs.LOG_INFO, f"[zmk] stopping {_service}")
    _systemctl("stop")
