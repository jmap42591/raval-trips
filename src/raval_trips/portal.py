"""Connection to the VW EU Data Act portal (via the community connector) and parsing of the data files."""
import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from . import db
from .config import get_password

LOG = logging.getLogger("raval_trips.portal")

SOC_FIELDS = ("battery_state_report.soc", "battery_level_HV.value")
ODO_FIELD = "mileage.value"


def charge_state_label(raw):
    """Map the car charge state to: charging / ready_for_charging / conservation / off."""
    if not raw:
        return None
    r = str(raw).upper()
    if "NOT_READY" in r or "OFF" in r or "NO_CHARG" in r:
        return "off"
    if "READY" in r:
        return "ready_for_charging"
    if "CONSERV" in r:
        return "conservation"
    if "CHARG" in r:
        return "charging"
    return "off"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_payload(payload: dict, fallback_ts=None):
    """Extract one reading from a data file. Returns a dict, or None if there is nothing useful."""
    from carconnectivity_connectors.vw_eu_data_act.dataset import Dataset

    ds = Dataset.from_json(payload)
    ts = ds.captured_at.timestamp() if ds.captured_at else fallback_ts
    if ts is None:
        return None
    soc = None
    for f in SOC_FIELDS:
        soc = _num(ds.value_of(f))
        if soc is not None and 0 <= soc <= 100:
            break
        soc = None
    # the odometer only goes up: if a file carries several values, the largest wins
    odos = [_num(p.value) for p in ds.points.values() if p.field_name == ODO_FIELD]
    odos = [o for o in odos if o is not None and o >= 0]
    odo = max(odos) if odos else None
    locked = ds.value_of("locked")
    reading = dict(
        ts=ts, soc=soc, odo=odo,
        charge_state=charge_state_label(ds.value_of("charging_state_report.current_charge_state")),
        charge_power=_num(ds.value_of("battery_state_report.charge_power")),
        locked=None if locked is None else int(bool(locked)),
        outdoor=_num(ds.value_of("outdoor_temperature.outdoor_temperature")),
        cabin=_num(ds.value_of("in_cabin_temperature.temperature")))
    if all(reading[k] is None for k in ("soc", "odo", "charge_state")):
        return None
    return reading


def import_zip_bytes(con, raw: bytes, name: str, source="zip"):
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".json")]
        if not members:
            raise ValueError(f"No JSON inside {name}")
        payload = json.loads(zf.read(members[0]).decode("utf-8"))
    # file time (YYYYMMDDhhmmss_VIN.zip, UTC) as a fallback
    fallback = None
    stem = name.rsplit("/", 1)[-1]
    if stem[:14].isdigit():
        fallback = datetime.strptime(stem[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    reading = parse_payload(payload, fallback)
    if reading is None:
        return None
    db.add_reading(con, source=source, **reading)
    return reading


class PortalSession:
    """Portal session; uses the e-mail from the settings and the password from the vault."""

    def __init__(self, settings, email=None, password=None):
        from carconnectivity_connectors.vw_eu_data_act.client import EudaApiClient
        self.settings = settings
        email = email or settings["email"]
        password = password or get_password(email)
        if not email or not password:
            raise RuntimeError("Not signed in yet (VW ID e-mail and password).")
        self.client = EudaApiClient(email, password, country=settings["country"],
                                    language=settings["language"], brand=settings["brand"],
                                    accept_terms_on_login=False)

    def login(self):
        self.client.login()
        return self.client.list_vehicles()

    def sync(self, con, vin, log=LOG.info, max_downloads=400):
        """Download the new files from the portal list and store the readings. Returns a summary."""
        from carconnectivity_connectors.vw_eu_data_act.client import ApiError, NO_CONTENT_SUFFIX
        meta = self.client.get_metadata(vin)
        identifier = meta.get("Identifier") or meta.get("identifier")
        if not identifier:
            raise RuntimeError("The portal has no active data request for this car. "
                               "Create the continuous 15-minute request on the portal (see the guide).")
        files = self.client.list_datasets(vin, identifier)
        new = [f for f in files if not db.delivery_known(con, f.get("name"))]
        new.sort(key=lambda f: f.get("createdOn") or f.get("name"))
        stats = dict(listed=len(files), new=len(new), stored=0, empty=0, errors=0)
        for f in new[:max_downloads]:
            name = f.get("name")
            if not name:
                continue
            if name.endswith(NO_CONTENT_SUFFIX):
                db.mark_delivery(con, name, f.get("createdOn"), f.get("size"), "empty")
                stats["empty"] += 1
                continue
            try:
                payload = self.client.download_dataset(vin, identifier, name)
                fallback = None
                if f.get("createdOn"):
                    try:
                        fallback = datetime.fromisoformat(str(f["createdOn"]).replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        pass
                reading = parse_payload(payload, fallback)
                if reading:
                    db.add_reading(con, source="portal", **reading)
                    stats["stored"] += 1
                db.mark_delivery(con, name, f.get("createdOn"), f.get("size"), "ok")
            except (ApiError, ValueError, KeyError) as err:
                log(f"Error in {name}: {err}")
                db.mark_delivery(con, name, f.get("createdOn"), f.get("size"), "error")
                stats["errors"] += 1
            con.commit()
        con.commit()
        return stats
