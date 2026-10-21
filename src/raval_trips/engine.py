"""Trip engine: trips, cycles between charges, charging sessions and the monthly report."""
from datetime import datetime

CHARGING = {"charging", "ready_for_charging", "conservation"}
REPORT = 15 * 60          # typical car reporting interval
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _numeric(rows, lo=None, hi=None):
    out = []
    for t, v in rows:
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if (lo is not None and x < lo) or (hi is not None and x > hi):
            continue
        out.append((t, x))
    return out


def _despike(points, jump=8, tol=4):
    """Drop isolated readings that jump away and come back (noise)."""
    keep = list(points)
    i = 1
    while i < len(keep) - 1:
        a, b, c = keep[i - 1][1], keep[i][1], keep[i + 1][1]
        if abs(b - a) >= jump and abs(b - c) >= jump and abs(a - c) <= tol:
            del keep[i]
        else:
            i += 1
    return keep


def month_key(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


def month_name(key):
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


class Engine:
    def __init__(self, odo_rows, soc_rows, chg_rows, battery_kwh=52.0, price=0.23, gap_minutes=30, now=None):
        self.battery_kwh = float(battery_kwh)
        self.price = float(price)
        self.gap = int(gap_minutes) * 60
        self.now = now if now is not None else datetime.now().timestamp()
        self.odo = _numeric(odo_rows, 0, 1_000_000)
        self.soc = _despike(_numeric(soc_rows, 0, 100))
        self.chg_times = [t for t, s in chg_rows if s in CHARGING]

    # ---------------- trips ----------------
    def _soc_before(self, ts, tol=0):
        last = None
        for t, v in self.soc:
            if t < ts + tol:
                last = (t, v)
            else:
                break
        return last

    def trips(self):
        moves, cur = [], None
        for t, v in self.odo:
            if cur is None:
                cur = v
                continue
            if v > cur:                       # the odometer only goes up: lower values are noise
                moves.append((t, cur, v))
                cur = v
        groups, g = [], []
        for m in moves:
            if g and m[0] - g[-1][0] > self.gap:
                groups.append(g)
                g = []
            g.append(m)
        if g:
            groups.append(g)

        out, prev_end = [], None
        for g in groups:
            t_first, t_last = g[0][0], g[-1][0]
            start_odo, end_odo = g[0][1], g[-1][2]
            start = t_first
            lo = max(prev_end or 0, t_first - self.gap - 120)
            window = [(t, v) for t, v in self.soc if lo < t <= t_first]
            before = self._soc_before(window[0][0]) if window else self._soc_before(t_first)
            if window:
                seq_prev = before[1] if before else None
                for t, v in window:
                    if seq_prev is not None and v < seq_prev:
                        start = t
                        break
                    seq_prev = v
            sb, se = self._soc_before(start), self._soc_before(t_last, tol=120)
            soc_start = sb[1] if sb else None
            soc_end = se[1] if se else None
            charged_inside = any(start <= t <= t_last for t in self.chg_times)
            used = None
            if soc_start is not None and soc_end is not None and not charged_inside and soc_start >= soc_end:
                used = soc_start - soc_end
            km = end_odo - start_odo
            kwh = used / 100 * self.battery_kwh if used is not None else None
            out.append(dict(
                start=start, end=t_last, duration=max(t_last - start, REPORT), km=km,
                odo_start=start_odo, odo_end=end_odo, soc_start=soc_start, soc_end=soc_end,
                used_pct=used, kwh=kwh, cost=(kwh * self.price if kwh is not None else None),
                kwh_100=(kwh / km * 100 if kwh is not None and km > 0 else None)))
            prev_end = t_last
        return out

    # ---------------- charging sessions ----------------
    def charges(self, trips):
        wins = [(t["start"], t["end"]) for t in trips]
        sessions, cur, prev = [], None, None
        for t, v in self.soc:
            if prev is not None and v > prev[1] and not any(a <= t <= b for a, b in wins):
                if cur and t - cur["end"] <= 6 * 3600:
                    cur["end"], cur["soc_end"] = t, v
                else:
                    if cur:
                        sessions.append(cur)
                    cur = dict(start=prev[0], end=t, soc_start=prev[1], soc_end=v)
            prev = (t, v)
        if cur:
            sessions.append(cur)
        out = []
        for c in sessions:
            gain = c["soc_end"] - c["soc_start"]
            if gain >= 3:
                c["kwh"] = gain / 100 * self.battery_kwh
                c["cost"] = c["kwh"] * self.price
                out.append(c)
        return out

    # ---------------- cycles (trips between charges) ----------------
    def cycles(self, trips):
        cycles, cur = [], []
        for tr in trips:
            if cur:
                p = cur[-1]
                charged = any(p["end"] < t < tr["start"] for t in self.chg_times)
                if not charged and p["soc_end"] is not None:
                    top = max([v for t, v in self.soc if p["end"] < t <= tr["start"]] or [p["soc_end"]])
                    charged = top >= p["soc_end"] + 4
                if charged:
                    cycles.append(cur)
                    cur = []
            cur.append(tr)
        if cur:
            cycles.append(cur)
        return cycles

    def _charge_end(self, cycle):
        first = cycle[0]["start"]
        last_up, prev = None, None
        for t, v in self.soc:
            if t >= first:
                break
            if prev is not None and v > prev[1]:
                last_up = (t, v)
            prev = (t, v)
        return last_up

    def summary(self, trips):
        with_e = [t for t in trips if t["kwh"] is not None and t["km"] > 0]
        kwh = sum(t["kwh"] for t in with_e)
        km_e = sum(t["km"] for t in with_e)
        return dict(
            trips=len(trips), km=sum(t["km"] for t in trips),
            kwh=kwh if with_e else None, cost=kwh * self.price if with_e else None,
            used_pct=sum(t["used_pct"] for t in with_e) if with_e else None,
            kwh_100=(kwh / km_e * 100 if km_e > 0 else None),
            duration=sum(t["duration"] for t in trips),
            start=trips[0]["start"] if trips else None, end=trips[-1]["end"] if trips else None)

    # ---------------- report ----------------
    def report(self):
        trips = self.trips()
        charges = self.charges(trips)
        cycles = self.cycles(trips)
        out = dict(current=None, cycles=[], months=[], totals={}, now=self.now)
        if cycles:
            cur = cycles[-1]
            ce = self._charge_end(cur)
            out["current"] = dict(
                summary=self.summary(cur), trips=cur,
                last_charge=dict(ts=ce[0], soc=ce[1]) if ce else None,
                in_progress=(self.now - cur[-1]["end"] <= self.gap))
            for c in cycles[:-1][::-1]:
                out["cycles"].append(dict(summary=self.summary(c), trips=c))
        keys = sorted({month_key(t["start"]) for t in trips} | {month_key(c["start"]) for c in charges}, reverse=True)
        for k in keys:
            mt = [t for t in trips if month_key(t["start"]) == k]
            mc = [c for c in charges if month_key(c["start"]) == k]
            s = self.summary(mt)
            s["charges"] = len(mc)
            s["charged_kwh"] = sum(c["kwh"] for c in mc)
            out["months"].append(dict(key=k, name=month_name(k), summary=s, trips=mt, charges=mc))
        s = self.summary(trips) if trips else self.summary([])
        s["charges"] = len(charges)
        s["charged_kwh"] = sum(c["kwh"] for c in charges)
        out["totals"] = s
        return out
