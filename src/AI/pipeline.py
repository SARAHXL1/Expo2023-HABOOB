"""One public function to convert an ESP32 JSON message to derived dashboard data."""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .risk_classification import wbgt_flag
from .sensor_processing import wind_voltage_to_ms, wind_to_10m, lux_to_solar_wm2
from .wbgt_calculator import cos_zenith, wbgt_liljegren, wbgt_simple

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config():
    """Load editable calibration parameters from JSON."""
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def _numeric(value, low, high):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def process_reading(message, timestamp=None, config=None):
    """Process a sensor JSON object, returning derived values or a reason for missing WBGT.

    timestamp must be a datetime representing the local time at the sensor site.
    Call from an existing Flask handler; this module does not start a server.
    """
    cfg = config or load_config()
    if timestamp is None:
        offset = timezone(timedelta(hours=cfg["timezone_utc_offset_hours"]))
        timestamp = datetime.now(offset)
    sensors = message.get("sensors", {})
    dht = sensors.get("dht22") or {}
    ta = _numeric(dht.get("ta_c"), -40, 85)
    rh = _numeric(dht.get("rh_pct"), 0, 100)
    if dht.get("status") != "ok" or ta is None or rh is None:
        return {"wbgt_c": None, "flag": None, "reason": "missing_ta_rh"}

    def fallback():
        result = wbgt_simple(ta, rh)
        return {"ta_c": ta, "rh_pct": rh, "wind_ms": None,
                "solar_radiation_wm2": None, "wbgt_c": round(result, 1),
                "flag": wbgt_flag(result), "wbgt_method": "simple",
                "flags": ["fallback_simple"]}

    anemometer = sensors.get("anemometer") or {}
    light = sensors.get("veml7700") or {}
    voltage = _numeric(anemometer.get("wind_v"), 0, 6)
    lux = _numeric(light.get("lux"), 0, 200000)
    if (anemometer.get("status") != "ok" or light.get("status") != "ok"
            or voltage is None or lux is None):
        return fallback()

    sensor_height = _numeric(anemometer.get("height_m", cfg["wind_sensor_height_m"]), 0.1, 30)
    if sensor_height is None:
        return fallback()
    wind_ms = wind_voltage_to_ms(voltage, cfg)
    wind_10m_ms = wind_to_10m(wind_ms, sensor_height, cfg)
    solar_wm2 = lux_to_solar_wm2(lux, cfg)
    sunny = solar_wm2 > cfg["sun_radiation_threshold_wm2"]
    direct_fraction = cfg["direct_radiation_fraction"] if sunny else 0.0
    cos_sza = cos_zenith(timestamp, cfg)
    try:
        wbgt = wbgt_liljegren(ta, rh, wind_10m_ms, solar_wm2,
                             direct_fraction, cos_sza, cfg["pressure_hpa"])
    except ArithmeticError:
        return {"wbgt_c": None, "flag": None, "reason": "no_convergence"}
    return {"ta_c": ta, "rh_pct": rh, "wind_ms": round(wind_ms, 2),
            "wind_10m_ms": round(wind_10m_ms, 2),
            "solar_radiation_wm2": round(solar_wm2, 1),
            "wbgt_c": round(wbgt, 1), "flag": wbgt_flag(wbgt),
            "wbgt_method": "liljegren", "sun_flag": int(sunny),
            "cos_sza": round(cos_sza, 3), "flags": []}
