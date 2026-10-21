"""Local web server: dashboard + JSON API. Listens on 127.0.0.1 only."""
import csv
import io
import json
import logging
import mimetypes
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, db
from .config import load_settings, save_settings, set_password
from .engine import Engine

LOG = logging.getLogger("raval_trips.server")
STATIC = Path(__file__).parent / "static"


class State:
    """Shared state: background sync status."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.last_run = None
        self.last_ok = None
        self.last_error = None
        self.last_stats = None
        self.log = []

    def snapshot(self):
        with self.lock:
            return dict(running=self.running, last_run=self.last_run, last_ok=self.last_ok,
                        last_error=self.last_error, last_stats=self.last_stats, log=self.log[-20:])


STATE = State()


def _log(msg):
    with STATE.lock:
        STATE.log.append(f"{datetime.now():%H:%M:%S} {msg}")
        STATE.log = STATE.log[-100:]
    LOG.info(msg)


def run_sync():
    """Download new files from the portal (blocking). Safe to call from a thread."""
    from .portal import PortalSession
    with STATE.lock:
        if STATE.running:
            return
        STATE.running = True
    con = None
    try:
        s = load_settings()
        if not s["email"] or not s["vin"]:
            raise RuntimeError("Connect your car first (Settings).")
        con = db.connect()
        _log("Syncing with the portal…")
        session = PortalSession(s)
        session.login()
        stats = session.sync(con, s["vin"], log=_log)
        with STATE.lock:
            STATE.last_ok = time.time()
            STATE.last_error = None
            STATE.last_stats = stats
        _log(f"Sync done: {stats['stored']} new readings from {stats['new']} new files.")
    except Exception as err:  # noqa: BLE001 - shown to the user
        with STATE.lock:
            STATE.last_error = str(err)
        _log(f"Sync failed: {err}")
    finally:
        if con is not None:
            con.close()
        with STATE.lock:
            STATE.running = False
            STATE.last_run = time.time()


def sync_loop():
    while True:
        s = load_settings()
        if s["email"] and s["vin"]:
            run_sync()
        time.sleep(max(5, int(s["sync_minutes"])) * 60)


def build_report():
    s = load_settings()
    con = db.connect()
    try:
        odo, soc, chg = db.series(con)
        counts = db.counts(con)
    finally:
        con.close()
    eng = Engine(odo, soc, chg, battery_kwh=s["battery_kwh"], price=s["price_kwh"], gap_minutes=s["gap_minutes"])
    rep = eng.report()
    public = {k: v for k, v in s.items()}
    rep.update(settings=public, status=STATE.snapshot(), data=counts, version=__version__,
               connected=bool(s["email"] and s["vin"]))
    return rep


def csv_trips():
    rep = build_report()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["start", "end", "duration_min", "km", "soc_start_pct", "soc_end_pct", "battery_used_pct",
                "kwh", "cost", "kwh_per_100km"])
    fmt = lambda ts: datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    r = lambda x, n=1: "" if x is None else round(x, n)
    for m in sorted(rep["months"], key=lambda m: m["key"]):
        for t in m["trips"]:
            w.writerow([fmt(t["start"]), fmt(t["end"]), round(t["duration"] / 60), r(t["km"]), r(t["soc_start"], 0),
                        r(t["soc_end"], 0), r(t["used_pct"], 0), r(t["kwh"]), r(t["cost"], 2), r(t["kwh_100"])])
    return out.getvalue()


def csv_charges():
    rep = build_report()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["start", "end", "soc_start_pct", "soc_end_pct", "kwh_into_battery", "cost"])
    fmt = lambda ts: datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    for m in sorted(rep["months"], key=lambda m: m["key"]):
        for c in m["charges"]:
            w.writerow([fmt(c["start"]), fmt(c["end"]), round(c["soc_start"]), round(c["soc_end"]),
                        round(c["kwh"], 1), round(c["cost"], 2)])
    return out.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "RavalTrips/" + __version__

    def log_message(self, fmt, *args):  # quiet
        return

    # --- safety: only accept requests addressed to localhost (blocks DNS rebinding) ---
    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "Forbidden", "text/plain")
        path = self.path.split("?")[0]
        try:
            if path == "/api/report":
                return self._json(build_report())
            if path == "/api/status":
                return self._json(STATE.snapshot())
            if path == "/api/export/trips.csv":
                return self._send(200, csv_trips(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="raval-trips.csv"'})
            if path == "/api/export/charges.csv":
                return self._send(200, csv_charges(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="raval-charges.csv"'})
            name = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/").lstrip("/")
            f = (STATIC / name).resolve()
            if STATIC.resolve() in f.parents and f.is_file():
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") or "javascript" in ctype else ""))
            return self._send(404, "Not found", "text/plain")
        except Exception as err:  # noqa: BLE001
            LOG.exception("GET %s failed", path)
            return self._json({"error": str(err)}, 500)

    def do_POST(self):
        # a custom header forces a CORS preflight, so other web pages cannot call this API
        if not self._host_ok() or self.headers.get("X-Raval-Trips") != "1":
            return self._send(403, "Forbidden", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        if self.path.split("?")[0] == "/api/import":
            return self._import(self.rfile.read(length), self.headers.get("X-Filename") or "upload.zip")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "Invalid JSON"}, 400)
        path = self.path.split("?")[0]
        try:
            if path == "/api/settings":
                return self._json({"settings": save_settings(body)})
            if path == "/api/sync":
                threading.Thread(target=run_sync, daemon=True).start()
                return self._json({"started": True})
            if path == "/api/login":
                return self._json(self._login(body))
            return self._json({"error": "Unknown endpoint"}, 404)
        except Exception as err:  # noqa: BLE001
            LOG.exception("POST %s failed", path)
            return self._json({"error": str(err)}, 500)

    def _import(self, raw, name):
        """Import a data file (.zip) downloaded by hand from the portal - no login needed."""
        from .portal import import_zip_bytes
        con = db.connect()
        try:
            r = import_zip_bytes(con, raw, name)
            con.commit()
        except Exception as err:  # noqa: BLE001
            return self._json({"error": f"{name}: {err}"}, 400)
        finally:
            con.close()
        return self._json({"ok": True, "stored": bool(r)})

    def _login(self, body):
        """Test the VW ID login, list the consented cars and save the e-mail/password locally."""
        from .portal import PortalSession
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        if not email or not password:
            return {"error": "Enter your VW ID e-mail and password."}
        s = load_settings()
        if body.get("brand"):
            s["brand"] = body["brand"]
        try:
            session = PortalSession(s, email=email, password=password)
            vehicles = session.login()
        except Exception as err:  # noqa: BLE001
            return {"error": f"Login failed: {err}"}
        if not vehicles:
            return {"error": "Login worked, but no car is linked on the portal yet. "
                             "Follow step 1 of the guide (pair your car and create the data request)."}
        set_password(email, password)
        vin = body.get("vin") or vehicles[0]["vin"]
        save_settings({"email": email, "vin": vin, "brand": s["brand"]})
        return {"ok": True, "vehicles": vehicles, "vin": vin}


def serve(port=None, open_browser=True, background_sync=True):
    s = load_settings()
    port = int(port or s["port"])
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    if background_sync:
        threading.Thread(target=sync_loop, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"Raval Trips {__version__} is running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
