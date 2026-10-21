import unittest
from raval_trips.engine import Engine

H = 3600


def eng(odo, soc, chg=(), **kw):
    return Engine(odo, soc, list(chg), now=10 * 86400, **kw)


class TripTests(unittest.TestCase):
    def test_gap_splits_trips(self):
        # readings 15 min apart = one trip; a 2 h gap = a second trip
        odo = [(0, 100), (1 * H, 110), (1 * H + 900, 112), (4 * H, 120)]
        soc = [(0, 80), (1 * H - 60, 78), (1 * H + 900, 76), (4 * H - 60, 76), (4 * H, 74)]
        trips = eng(odo, soc).trips()
        self.assertEqual(len(trips), 2)
        self.assertAlmostEqual(trips[0]["km"], 12)
        self.assertAlmostEqual(trips[1]["km"], 8)

    def test_energy_and_cost(self):
        odo = [(0, 100), (H, 120)]
        soc = [(0, 80), (H, 70)]
        t = eng(odo, soc, battery_kwh=50, price=0.2).trips()[0]
        self.assertAlmostEqual(t["used_pct"], 10)
        self.assertAlmostEqual(t["kwh"], 5)         # 10 % of 50 kWh
        self.assertAlmostEqual(t["cost"], 1.0)      # 5 kWh * 0.2
        self.assertAlmostEqual(t["kwh_100"], 25)    # 5 kWh over 20 km

    def test_stale_lower_odometer_is_ignored(self):
        odo = [(0, 100), (H, 120), (H + 900, 110), (2 * H, 130)]   # 110 is a stale value
        soc = [(0, 80), (H, 75), (2 * H, 70)]
        total = sum(t["km"] for t in eng(odo, soc).trips())
        self.assertAlmostEqual(total, 30)

    def test_charge_closes_cycle(self):
        odo = [(0, 100), (H, 120), (20 * H, 125)]
        soc = [(0, 80), (H, 70)] + [(h * H, 70 + 2 * (h - 2)) for h in range(2, 12)] + [(19 * H, 90), (20 * H, 88)]
        rep = eng(odo, soc).report()
        self.assertEqual(len(rep["cycles"]) + 1, 2)
        self.assertEqual(rep["totals"]["charges"], 1)

    def test_monthly_totals(self):
        odo = [(0, 100), (H, 120)]
        soc = [(0, 80), (H, 70)]
        rep = eng(odo, soc, battery_kwh=50, price=0.2).report()
        self.assertEqual(len(rep["months"]), 1)
        self.assertAlmostEqual(rep["months"][0]["summary"]["cost"], 1.0)


if __name__ == "__main__":
    unittest.main()
