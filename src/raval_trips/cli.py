"""Command line: raval-trips serve | import-zip | sync | report | demo"""
import argparse
import logging
import sys
from datetime import datetime

from . import __version__, db
from .config import load_settings


def _import_zip(paths):
    from .portal import import_zip_bytes
    con = db.connect()
    n = 0
    for p in paths:
        try:
            with open(p, "rb") as fh:
                r = import_zip_bytes(con, fh.read(), str(p))
            if r:
                n += 1
                print(f"imported {p}: soc={r['soc']} odo={r['odo']} charge={r['charge_state']}")
            else:
                print(f"nothing useful in {p}")
        except Exception as err:  # noqa: BLE001
            print(f"skipped {p}: {err}")
    con.commit()
    con.close()
    print(f"{n} file(s) imported.")


def _report():
    from .engine import Engine
    s = load_settings()
    con = db.connect()
    odo, soc, chg = db.series(con)
    con.close()
    rep = Engine(odo, soc, chg, s["battery_kwh"], s["price_kwh"], s["gap_minutes"]).report()
    fmt = lambda ts: datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
    cur = rep["current"]
    if not cur:
        print("No trips yet.")
        return
    print(f"Current cycle: {cur['summary']['trips']} trips, {cur['summary']['km']:.1f} km")
    for t in cur["trips"]:
        energy = "" if t["kwh"] is None else "%.1f kWh" % t["kwh"]
        print("  %s -> %s  %.1f km  %s" % (fmt(t["start"]), fmt(t["end"]), t["km"], energy))
    for m in rep["months"]:
        s_ = m["summary"]
        print(f"{m['name']}: {s_['trips']} trips, {s_['charges']} charges, {s_['km']:.0f} km, "
              f"{(s_['kwh'] or 0):.1f} kWh, {(s_['cost'] or 0):.2f} EUR")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="raval-trips", description="Trips, consumption and cost for your CUPRA - 100% local.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    sp = sub.add_parser("serve", help="start the local dashboard (default)")
    sp.add_argument("--port", type=int)
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--no-sync", action="store_true", help="do not sync in the background")
    ip = sub.add_parser("import-zip", help="import data files (.zip) downloaded from the portal")
    ip.add_argument("files", nargs="+")
    sub.add_parser("sync", help="download new data files from the portal now")
    sub.add_parser("report", help="print a text report")
    dp = sub.add_parser("demo", help="start with fake data to try the dashboard (no car needed)")
    dp.add_argument("--port", type=int)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cmd == "import-zip":
        return _import_zip(args.files)
    if args.cmd == "sync":
        from .server import run_sync, STATE
        run_sync()
        snap = STATE.snapshot()
        print(snap["last_error"] or f"OK {snap['last_stats']}")
        return 1 if snap["last_error"] else 0
    if args.cmd == "report":
        return _report()
    if args.cmd == "demo":
        import os
        import tempfile
        os.environ["RAVAL_TRIPS_HOME"] = tempfile.mkdtemp(prefix="raval-demo-")
        from .demo import populate
        populate()
        from .server import serve
        return serve(args.port, open_browser=True, background_sync=False)
    from .server import serve
    return serve(getattr(args, "port", None), open_browser=not getattr(args, "no_browser", False),
                 background_sync=not getattr(args, "no_sync", False))


if __name__ == "__main__":
    sys.exit(main())
