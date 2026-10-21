"""Settings and secrets stored locally (nothing leaves your computer except the login to the VW portal)."""
import json
import os
import sys
from pathlib import Path

APP = "raval-trips"


def data_dir() -> Path:
    override = os.environ.get("RAVAL_TRIPS_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP
    base.mkdir(parents=True, exist_ok=True)
    return base


DEFAULTS = {
    "brand": "CUPRA",
    "country": "pt",
    "language": "pt",
    "email": "",
    "vin": "",
    "battery_kwh": 52.0,        # battery capacity (kWh)
    "price_kwh": 0.23,          # cost per kWh
    "currency": "€",
    "gap_minutes": 30,          # readings more than X minutes apart start a new trip
    "port": 8765,
    "sync_minutes": 15,
}


def _settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(_settings_path().read_text()))
    except (OSError, ValueError):
        pass
    return s


def save_settings(new: dict) -> dict:
    s = load_settings()
    for k, v in new.items():
        if k in DEFAULTS:
            s[k] = type(DEFAULTS[k])(v) if DEFAULTS[k] != "" and not isinstance(DEFAULTS[k], str) else v
    _settings_path().write_text(json.dumps(s, indent=2))
    try:
        os.chmod(_settings_path(), 0o600)
    except OSError:
        pass
    return s


# ---- password: system vault (Keychain / Credential Locker) or a file with restricted permissions
def _secret_file() -> Path:
    return data_dir() / "secret.json"


def set_password(email: str, password: str) -> None:
    try:
        import keyring
        keyring.set_password(APP, email, password)
        return
    except Exception:  # no vault available (e.g. Linux without a keyring service)
        pass
    p = _secret_file()
    p.write_text(json.dumps({email: password}))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def get_password(email: str):
    try:
        import keyring
        pw = keyring.get_password(APP, email)
        if pw:
            return pw
    except Exception:
        pass
    try:
        return json.loads(_secret_file().read_text()).get(email)
    except (OSError, ValueError):
        return None
