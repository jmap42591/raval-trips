"""Local SQLite database with the car readings."""
import sqlite3
import time

from .config import data_dir

SCHEMA = """
create table if not exists readings (
    ts real primary key,          -- time the car captured the reading (epoch, UTC)
    soc real, odo real, charge_state text, charge_power real,
    locked integer, outdoor real, cabin real, source text
);
create table if not exists deliveries (
    name text primary key, created text, size integer, processed_at real, status text
);
"""


def connect(path=None) -> sqlite3.Connection:
    con = sqlite3.connect(path or (data_dir() / "raval.sqlite"), timeout=30)
    con.executescript(SCHEMA)
    return con


def add_reading(con, ts, soc=None, odo=None, charge_state=None, charge_power=None,
                locked=None, outdoor=None, cabin=None, source="portal"):
    con.execute(
        "insert or replace into readings(ts,soc,odo,charge_state,charge_power,locked,outdoor,cabin,source) "
        "values(?,?,?,?,?,?,?,?,?)",
        (ts, soc, odo, charge_state, charge_power, locked, outdoor, cabin, source))


def delivery_known(con, name) -> bool:
    return con.execute("select 1 from deliveries where name=?", (name,)).fetchone() is not None


def mark_delivery(con, name, created, size, status):
    con.execute("insert or replace into deliveries values(?,?,?,?,?)", (name, created, size, time.time(), status))


def series(con):
    """Time-ordered series for the engine: odometer, state of charge and charging state."""
    odo = [(t, v) for t, v in con.execute("select ts, odo from readings where odo is not null order by ts")]
    soc = [(t, v) for t, v in con.execute("select ts, soc from readings where soc is not null order by ts")]
    chg = [(t, s) for t, s in con.execute("select ts, charge_state from readings where charge_state is not null order by ts")]
    return odo, soc, chg


def counts(con):
    n = con.execute("select count(*), min(ts), max(ts) from readings").fetchone()
    d = con.execute("select count(*) from deliveries").fetchone()[0]
    return dict(readings=n[0], first=n[1], last=n[2], deliveries=d)
