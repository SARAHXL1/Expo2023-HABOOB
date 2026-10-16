"""اختبارات توقع Open-Meteo ومسار المنصة: بلا إنترنت وبلا عتاد (الشبكة والحساب مُستبدلان)."""
import datetime as dt
import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "02_server_backend"))

import forecast          # noqa: E402
import platform_view     # noqa: E402

TZ = forecast.TZ
CFG = {"pressure_hpa": 945.0, "latitude": 24.71, "longitude": 46.68, "timezone_utc_offset_hours": 3}


def payload(**over):
    p = {"hourly": {
        "time": ["2026-10-14T12:00", "2026-10-14T13:00", "2026-10-14T14:00", "2026-10-14T15:00"],
        "temperature_2m": [38, 39, 40, None],
        "relative_humidity_2m": [15, 14, 13, 12],
        "wind_speed_10m": [3.0, 3.1, 3.2, 3.3],
        "shortwave_radiation": [800, 820, 0, 700],
        "direct_radiation": [600, 656, 0, 500],
        "surface_pressure": [945, 944, 944, 943]}}
    p["hourly"].update(over)
    return p


class ForecastComputeTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 14, 13, 20, tzinfo=TZ)

    @patch("forecast.wbgt_liljegren", return_value=31.5)
    def test_starts_at_current_hour_and_passes_direct_fraction(self, w):
        rows = forecast.compute(payload(), self.now, 10, CFG)
        self.assertEqual([r["time"][11:13] for r in rows], ["13", "14", "15"])
        self.assertEqual(rows[0]["wbgt"], 31.5)
        self.assertEqual(rows[0]["flag"], "red")
        args = w.call_args_list[0][0]
        self.assertEqual(args[:4], (39, 14, 3.1, 820))
        self.assertAlmostEqual(args[4], 656 / 820)          # fdir = مباشر ÷ إجمالي

    @patch("forecast.wbgt_liljegren", return_value=25.0)
    def test_missing_input_gives_null_not_a_made_up_number(self, w):
        rows = forecast.compute(payload(), self.now, 10, CFG)
        self.assertIsNone(rows[-1]["wbgt"])                  # درجة الحرارة None في الساعة 15
        self.assertIsNone(rows[-1]["flag"])

    @patch("forecast.wbgt_liljegren", return_value=25.0)
    def test_night_hour_has_zero_direct_fraction(self, w):
        forecast.compute(payload(), self.now, 10, CFG)
        night = [c[0] for c in w.call_args_list if c[0][3] == 0]
        self.assertEqual(night[0][4], 0.0)

    @patch("forecast.wbgt_liljegren", return_value=25.0)
    def test_hours_limit(self, w):
        self.assertEqual(len(forecast.compute(payload(), self.now, 2, CFG)), 2)


class ForecastGetTests(unittest.TestCase):
    def setUp(self):
        forecast._cache.update(at=0.0, data=None)
        self.s = patch("forecast._settings", return_value=dict(forecast.DEFAULTS, cache_s=0))
        self.s.start()

    def tearDown(self):
        self.s.stop()
        forecast._cache.update(at=0.0, data=None)

    @patch("forecast.wbgt_liljegren", return_value=28.0)
    def test_success_then_offline_serves_stale_then_unavailable(self, w):
        now = dt.datetime(2026, 10, 14, 12, 5, tzinfo=TZ)
        with patch("forecast._fetch", return_value=payload()):
            ok = forecast.get(now)
        self.assertTrue(ok["available"])
        self.assertFalse(ok["stale"])
        with patch("forecast._fetch", side_effect=urllib.error.URLError("no network")):
            stale = forecast.get(now)
            self.assertTrue(stale["available"])
            self.assertTrue(stale["stale"])                  # آخر نتيجة ناجحة، موسومة
            forecast._cache.update(at=0.0, data=None)
            gone = forecast.get(now)
        self.assertFalse(gone["available"])
        self.assertIn("Open-Meteo", gone["reason"])
        self.assertNotIn("hours", gone)                      # لا ساعات مختلقة

    def test_empty_payload_is_unavailable(self):
        with patch("forecast._fetch", return_value={"hourly": {"time": []}}):
            self.assertFalse(forecast.get()["available"])


def fake_view(ta, wbgt, flag, online=True, simulated=False, alerts=()):
    return {"online": online, "age_s": 1 if online else 40, "rx_ts": 0, "transport": "wifi",
            "sensors": {"dht22": {"status": "ok"}}, "power_source": "usb",
            "values": {"ta_c": ta, "rh_pct": 20, "wind_ms": 1.0, "lux": 90000},
            "derived": {"wbgt_c": wbgt, "flag": flag, "flag_ar": "x", "wind_10m_ms": 1.5,
                        "solar_wm2": 800, "advice": {"action": "monitor"}, "explain": {}},
            "alerts": list(alerts)}


class PlatformViewTests(unittest.TestCase):
    def run_live(self, nodes, views):
        with patch.object(platform_view.processing, "nodes_view", return_value=nodes), \
             patch.object(platform_view.processing, "latest_view", side_effect=lambda n: views[n]), \
             patch.object(platform_view.storage, "recent_decisions", return_value=[]):
            return platform_view.live()

    def test_zone_follows_real_pole_and_blanks_when_it_goes_offline(self):
        nodes = [{"node_id": "sim-01", "simulated": True}, {"node_id": "node-01", "simulated": False}]
        blk = {"code": "WBGT-BLACK", "severity": "critical", "text": "WBGT", "hint": None}
        views = {"sim-01": fake_view(24, 17.0, "white"),
                 "node-01": fake_view(38, 39.0, "black", alerts=[blk])}
        d = self.run_live(nodes, views)
        self.assertEqual(d["zone"]["wbgt"], 39.0)            # الحقيقي لا المحاكاة
        self.assertEqual(d["zone"]["flag"], "black")

        views["node-01"] = fake_view(38, 39.0, "black", online=False, alerts=[blk])
        d = self.run_live(nodes, views)
        self.assertIsNone(d["zone"]["wbgt"])                 # آخر قراءة ليست الراهنة: «—»
        self.assertIsNone(d["zone"]["temp"])
        self.assertFalse([a for a in d["alerts"] if a["code"].startswith("WBGT-")])

    def test_alert_ids_are_stable_codes_not_positions(self):
        a = {"code": "WBGT-RED", "severity": "critical", "text": "x", "hint": None}
        b = {"code": "SENSOR-DHT22", "severity": "warning", "text": "y", "hint": None}
        v1 = fake_view(30, 31.5, "red", alerts=[a, b])
        v2 = fake_view(30, 31.5, "red", alerts=[b, a])       # ترتيب مختلف
        nodes = [{"node_id": "n", "simulated": False}]
        i1 = {x["code"]: x["id"] for x in self.run_live(nodes, {"n": v1})["alerts"]}
        i2 = {x["code"]: x["id"] for x in self.run_live(nodes, {"n": v2})["alerts"]}
        self.assertEqual(i1, i2)


if __name__ == "__main__":
    unittest.main()
