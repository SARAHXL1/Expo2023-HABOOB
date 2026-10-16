"""Basic offline tests, including a modeled calculation with no library dependency."""
import unittest
from unittest.mock import patch
from datetime import datetime
from AI.pipeline import process_reading
from AI.risk_classification import wbgt_flag
from AI.sensor_processing import wind_voltage_to_ms, lux_to_solar_wm2


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.message = {"sensors": {
            "dht22": {"status": "ok", "ta_c": 35, "rh_pct": 20},
            "anemometer": {"status": "ok", "wind_v": 0.1, "height_m": 1.8},
            "veml7700": {"status": "ok", "lux": 88000}
        }}

    def test_five_flags(self):
        self.assertEqual([wbgt_flag(x) for x in [26.6, 26.7, 29.4, 31.1, 32.2]],
                         ["white", "green", "yellow", "red", "black"])

    def test_full_model_path(self):
        with patch("AI.pipeline.wbgt_liljegren", return_value=29.1):
            d = process_reading(self.message, datetime(2026, 10, 13, 12))
        self.assertEqual(d["flag"], "green")
        self.assertEqual(d["wbgt_method"], "liljegren")
        self.assertAlmostEqual(d["solar_radiation_wm2"], 800)

    def test_missing_light_fallback(self):
        self.message["sensors"]["veml7700"]["status"] = "error"
        self.assertEqual(process_reading(self.message)["wbgt_method"], "simple")

    def test_missing_temperature(self):
        self.message["sensors"]["dht22"]["ta_c"] = None
        self.assertEqual(process_reading(self.message)["reason"], "missing_ta_rh")

    def test_conversions(self):
        cfg = {"wind_voltage_min": 0.02, "wind_k": 20, "wind_b": .5, "lux_per_wm2": 110}
        self.assertAlmostEqual(wind_voltage_to_ms(.1, cfg), 2.5)
        self.assertAlmostEqual(lux_to_solar_wm2(88000, cfg), 800)


if __name__ == "__main__":
    unittest.main()
