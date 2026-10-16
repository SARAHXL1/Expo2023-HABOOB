"""اختبارات التحليل بالقواعد، والتوصية، ومحرك القرار، وتحليل البيانات (قاعدة SQLite مؤقتة)."""
import json
import os
import sqlite3
import tempfile
import unittest

from AI.decision_engine import make_decision
from AI.heat_analysis import analyze_heat
from AI.recommendation_engine import generate_recommendation


def derived(**over):
    d = {"ta_c": 35, "rh_pct": 20, "wind_ms": 2.9, "solar_radiation_wm2": 300,
         "wbgt_c": 28.0, "flag": "green", "wbgt_method": "liljegren"}
    d.update(over)
    return d


class AnalysisTests(unittest.TestCase):
    def test_factors_are_found_by_thresholds(self):
        a = analyze_heat(derived(solar_radiation_wm2=850, wind_ms=0.9, ta_c=40, rh_pct=65,
                                 wbgt_c=33, flag="black"))
        self.assertEqual(a["factor_count"], 4)

    def test_unavailable_without_wbgt(self):
        self.assertEqual(analyze_heat({"wbgt_c": None})["status"], "unavailable")


class RecommendationTests(unittest.TestCase):
    def rec(self, **over):
        d = derived(**over)
        return generate_recommendation(d, analyze_heat(d))

    def test_missing_flag_asks_to_check_sensor(self):
        self.assertEqual(self.rec(flag=None, wbgt_c=None)["action"], "CHECK_SENSOR")

    def test_white_monitor_black_limit_exposure(self):
        self.assertEqual(self.rec(flag="white")["action"], "MONITOR")
        self.assertEqual(self.rec(flag="black", wbgt_c=33)["priority"], "critical")

    def test_sun_then_mist_then_fans(self):
        self.assertEqual(self.rec(flag="yellow", solar_radiation_wm2=800)["action"], "ACTIVATE_SHADING")
        self.assertEqual(self.rec(flag="yellow", ta_c=39, rh_pct=20)["action"], "ACTIVATE_MISTING")
        self.assertEqual(self.rec(flag="yellow", wind_ms=1.0)["action"], "REVIEW_FANS")


class DecisionTests(unittest.TestCase):
    def test_dashboard_shape(self):
        d = make_decision("node-01", derived())
        self.assertEqual(d["heat_stress"]["index"], "WBGT")
        self.assertEqual(d["heat_stress"]["risk_level"], "green")
        self.assertIn("recommendation", d)


class DataAnalysisTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE readings (rx_ts REAL, node_id TEXT, derived_json TEXT, ta_c REAL,"
                  " rh_pct REAL, wind_ms REAL, wbgt_c REAL, flag TEXT)")
        for i, w in enumerate([28.0, 29.0, 31.5]):
            c.execute("INSERT INTO readings VALUES (?,?,?,?,?,?,?,?)",
                      (1_800_000_000 + i * 60, "node-01",
                       json.dumps({"derived": {"solar_wm2": 800, "wbgt_method": "liljegren"}}),
                       35.0, 20.0, 1.0, w, "red" if w > 31 else "green"))
        c.execute("INSERT INTO readings VALUES (?,?,?,?,?,?,?,?)",
                  (1_800_000_300, "node-02", "{}", None, None, None, None, None))   # بلا WBGT
        c.commit()
        c.close()

    def tearDown(self):
        os.remove(self.db)

    def test_process_database_takes_latest_reading_per_node(self):
        from AI.data_analysis import process_database
        items = {i["node_id"]: i["derived"] for i in process_database(self.db)}
        self.assertEqual(items["node-01"]["wbgt_c"], 31.5)
        self.assertEqual(items["node-01"]["solar_radiation_wm2"], 800)
        self.assertEqual(items["node-02"]["flag"], None)
        # القرار من القاعدة يعمل (لا ImportError كما كان في النسخة المرفقة)
        self.assertEqual(make_decision("node-02", items["node-02"])["recommendation"]["action"],
                         "CHECK_SENSOR")

    def test_trend_and_zone_ranking_skip_rows_without_wbgt(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas غير مثبّتة")
        from AI.data_analysis import compare_zones, detect_trend, load_database
        df = load_database(self.db)
        self.assertEqual(len(df), 3)                       # صف node-02 بلا WBGT لا يدخل
        self.assertEqual(detect_trend(df), "Increasing heat stress")
        self.assertEqual(list(compare_zones(df).index), ["node-01"])


if __name__ == "__main__":
    unittest.main()
