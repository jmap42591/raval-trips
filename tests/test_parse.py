import io
import json
import unittest
import zipfile

from raval_trips import db
from raval_trips.portal import charge_state_label, import_zip_bytes, parse_payload


def payload():
    return {"vin": "VSSZZZ00000000000", "user_id": "x", "Data": [
        {"key": "a", "dataFieldName": "battery_state_report.soc", "value": "83"},
        {"key": "b", "dataFieldName": "mileage.value", "value": "197"},
        {"key": "c", "dataFieldName": "mileage.value", "value": "190"},      # stale, lower
        {"key": "d", "dataFieldName": "locked", "value": "true"},
        {"key": "e", "dataFieldName": "charging_state_report.current_charge_state",
         "value": "CHARGE_STATE_CHARGING_HV_BATTERY"},
        {"key": "f", "dataFieldName": "car_captured_time", "value": "2026-10-11T09:42:09Z"},
    ]}


class ParseTests(unittest.TestCase):
    def test_reading(self):
        r = parse_payload(payload())
        self.assertEqual(r["soc"], 83.0)
        self.assertEqual(r["odo"], 197.0)              # largest value wins
        self.assertEqual(r["charge_state"], "charging")
        self.assertEqual(r["locked"], 1)
        self.assertEqual(r["ts"], 1791711729.0)

    def test_charge_labels(self):
        self.assertEqual(charge_state_label("CHARGE_STATE_NOT_READY_FOR_CHARGING"), "off")
        self.assertEqual(charge_state_label("CHARGE_STATE_READY_FOR_CHARGING"), "ready_for_charging")

    def test_zip_import(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("data.json", json.dumps(payload()))
        con = db.connect(":memory:")
        self.assertIsNotNone(import_zip_bytes(con, buf.getvalue(), "20261011113233_VSSZZZ00000000000.zip"))
        self.assertEqual(con.execute("select count(*) from readings").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
