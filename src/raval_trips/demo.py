"""Fake data so anyone can try the dashboard without a car."""
import random
from datetime import datetime, timedelta

from . import db


def populate(days=75, seed=7):
    rnd = random.Random(seed)
    con = db.connect()
    now = datetime.now().replace(second=0, microsecond=0)
    t = now - timedelta(days=days)
    soc, odo = 82.0, 1200.0
    cap = 52.0

    def put(ts, charge="off", power=0.0):
        db.add_reading(con, ts.timestamp(), soc=round(soc), odo=round(odo), charge_state=charge,
                       charge_power=power, source="demo")

    put(t)
    while t < now - timedelta(hours=2):
        t += timedelta(days=1)
        # morning commute and evening commute on weekdays, a longer trip now and then
        trips = []
        if t.weekday() < 5:
            trips = [(8, rnd.randint(12, 28)), (18, rnd.randint(12, 28))]
        elif rnd.random() < 0.6:
            trips = [(11, rnd.randint(25, 90))]
        for hour, km in trips:
            start = t.replace(hour=hour, minute=rnd.randint(0, 40))
            if start > now:
                continue
            put(start - timedelta(minutes=20))        # parked reading before leaving
            steps = max(1, km // 14)
            for i in range(steps):
                ts = start + timedelta(minutes=15 * i)
                odo += km / steps
                soc -= (km / steps) * rnd.uniform(0.24, 0.34) * 52 / cap   # ~0.3 % of the battery per km
                put(ts)
            put(start + timedelta(minutes=15 * steps + 5))
        if soc < 38 or (t.weekday() == 6 and soc < 60):
            ts = t.replace(hour=21, minute=15)
            if ts > now:
                continue
            target = rnd.choice([80, 80, 90])
            while soc < target:
                soc = min(target, soc + 2.5)
                put(ts, "charging", 2.3)
                ts += timedelta(minutes=45)
            put(ts, "ready_for_charging")
            put(ts + timedelta(hours=7), "off")
    con.commit()
    con.close()
