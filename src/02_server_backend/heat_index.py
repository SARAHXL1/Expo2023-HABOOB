"""
جسر الخادم مع وحدة الذكاء الاصطناعي (مجلد AI): حساب WBGT والعلم والتفسير والتوصية.

يُستدعى من processing.process لكل رسالة، بعد فحص المدى وحالات القطع،
حتى لا تدخل الحساب قيمة رفضها الخادم.
"""
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from AI.pipeline import process_reading, load_config       # noqa: E402
from AI.advice import explain, advise                      # noqa: E402
from AI.heat_analysis import analyze_heat                  # noqa: E402
from AI.recommendation_engine import generate_recommendation   # noqa: E402

try:
    import thermofeel  # noqa: F401  — يُستورد هنا مرة واحدة عند تشغيل الخادم
    LILJEGREN_OK, LIB_ERROR = True, ""
except Exception as exc:                                   # المكتبة غير مثبّتة
    LILJEGREN_OK, LIB_ERROR = False, str(exc)

TZ = dt.timezone(dt.timedelta(hours=3))                    # الرياض

FLAG_AR = {"white": "أبيض", "green": "أخضر", "yellow": "أصفر",
           "red": "أحمر", "black": "أسود"}

EMPTY = {"wbgt_c": None, "flag": None, "flag_ar": None, "wbgt_method": None,
         "wind_10m_ms": None, "solar_wm2": None, "sun_flag": None,
         "cos_sza": None, "wbgt_reason": None, "explain": None, "advice": None,
         "analysis": None, "recommendation": None}


def _part(sensors, sid, fields):
    entry = sensors.get(sid) or {}
    out = {"status": entry.get("status")}
    for f in fields:
        out[f] = (entry.get("values") or {}).get(f)
    return out


def _ai_config(nset):
    """config.json في جذر المشروع هو المصدر الوحيد لمعاملات المعايرة."""
    c = load_config()
    c["wind_k"] = nset.get("wind_k", c["wind_k"])
    c["wind_b"] = nset.get("wind_b", c["wind_b"])
    c["wind_voltage_min"] = nset.get("wind_v_min", c["wind_voltage_min"])
    c["wind_sensor_height_m"] = nset.get("wind_height_m", c["wind_sensor_height_m"])
    return c


def compute(sensors, ts, nset):
    """sensors = حالات القطع بعد معالجة الخادم · ts = وقت القراءة (epoch) · nset = إعدادات العقدة."""
    out = dict(EMPTY)
    c = _ai_config(nset)
    msg = {"sensors": {
        "dht22": _part(sensors, "dht22", ["ta_c", "rh_pct"]),
        "anemometer": dict(_part(sensors, "anemometer", ["wind_v"]),
                           height_m=c["wind_sensor_height_m"]),
        "veml7700": _part(sensors, "veml7700", ["lux"]),
    }}
    if not LILJEGREN_OK:          # بلا thermofeel: الصيغة الاحتياطية بدل توقف الاستقبال
        msg["sensors"]["anemometer"]["status"] = "lib_missing"
    t_local = dt.datetime.fromtimestamp(ts, TZ)
    try:
        r = process_reading(msg, t_local, c)
    except Exception as exc:      # أي خطأ في الحساب لا يُسقط حفظ الرسالة
        out["wbgt_reason"] = "تعذر حساب WBGT: %s" % exc
        return out

    out.update({"wbgt_c": r.get("wbgt_c"), "flag": r.get("flag"),
                "flag_ar": FLAG_AR.get(r.get("flag")),
                "wbgt_method": r.get("wbgt_method"),
                "wind_10m_ms": r.get("wind_10m_ms"),
                "solar_wm2": r.get("solar_radiation_wm2"),
                "sun_flag": r.get("sun_flag"), "cos_sza": r.get("cos_sza")})
    if r.get("reason") == "missing_ta_rh":
        out["wbgt_reason"] = "لا يُحسب WBGT لغياب حرارة الهواء أو الرطوبة."
    elif r.get("reason") == "no_convergence":
        out["wbgt_reason"] = "معادلة WBGT لم تتقارب لهذه المدخلات."
    elif r.get("wbgt_method") == "simple":
        out["wbgt_reason"] = ("قيمة تقريبية بالصيغة الاحتياطية: قراءة الرياح أو الإضاءة غير متوفرة"
                              + ("، ومكتبة thermofeel غير مثبّتة." if not LILJEGREN_OK else "."))

    # تحليل العوامل والتوصية النصية بالقواعد (heat_analysis / recommendation_engine)
    try:
        out["analysis"] = analyze_heat(r)
        out["recommendation"] = generate_recommendation(r, out["analysis"])
    except Exception as exc:
        out["rules_error"] = str(exc)

    # التفسير والتوصية: فقط عند الحساب الكامل (Liljegren)
    if r.get("wbgt_method") == "liljegren":
        try:
            fdir = c["direct_radiation_fraction"] if r.get("sun_flag") else 0.0
            args = (r["ta_c"], r["rh_pct"], r["wind_10m_ms"], r["solar_radiation_wm2"],
                    fdir, r["cos_sza"], c["pressure_hpa"])
            contrib = explain(*args)
            out["explain"] = contrib
            out["advice"] = advise(*args, r["flag"], contrib)
        except Exception as exc:
            out["explain_error"] = str(exc)
    return out
