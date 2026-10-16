"""
توقع WBGT للساعات القادمة من Open-Meteo — GET /api/forecast (تحسين اختياري، الملحق ج).

الطقس المتوقع (حرارة، رطوبة، رياح على 10 م، إشعاع، ضغط) يأتي من Open-Meteo،
ثم يُحسب WBGT لكل ساعة بدالة Liljegren نفسها التي تحسب القراءة الحية (مجلد AI)،
فلا يختلف المنحنى عن القراءة في الطريقة. لا شيء يُختلق: إن تعذر الاتصال بالإنترنت
أو نقصت ساعة بعض مدخلاتها تعود الاستجابة بـ available=false أو بقيمة null.

الإشعاع الأفقي المباشر ÷ الإجمالي = نسبة الإشعاع المباشر fdir. قيم Open-Meteo متوسط الساعة
السابقة، فتُحسب زاوية الشمس عند منتصف تلك الساعة.
"""
import datetime as dt
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import heat_index                                   # noqa: F401  — يضيف جذر المشروع إلى المسار
from AI.pipeline import load_config                 # noqa: E402
from AI.wbgt_calculator import cos_zenith, wbgt_liljegren   # noqa: E402
from AI.risk_classification import wbgt_flag        # noqa: E402
from settings import cfg                            # noqa: E402

DEFAULTS = {
    "url": "https://api.open-meteo.com/v1/forecast",
    "hours": 10,             # عدد الساعات المعروضة بدءًا من الساعة الحالية
    "cache_s": 1800,         # لا نطلب من Open-Meteo أكثر من مرة كل نصف ساعة
    "stale_ok_s": 21600,     # عند فشل الطلب نعرض آخر نتيجة ناجحة حتى 6 ساعات، موسومة stale
    "timeout_s": 6,
}
HOURLY = ("temperature_2m,relative_humidity_2m,wind_speed_10m,"
          "shortwave_radiation,direct_radiation,surface_pressure")
TZ = dt.timezone(dt.timedelta(hours=3))             # الرياض

_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}


def _settings():
    s = dict(DEFAULTS)
    s.update(cfg().get("forecast", {}))
    return s


def _fallback_context():
    """بايثون المثبّت من python.org على ماك يأتي بلا شهادات الجذر. نبحث عن حزمة شهادات موجودة
    (certifi أو شهادات النظام) ونبقي التحقق من الشهادة مفعّلًا؛ لا نعطّله أبدًا."""
    cands = []
    try:
        import certifi
        cands.append(certifi.where())
    except Exception:
        pass
    cands += ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"]
    for cafile in cands:
        if os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    return None


def _fetch(url, timeout):
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
    except urllib.error.URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
        ctx = _fallback_context()
        if ctx is None:
            raise
        r = urllib.request.urlopen(url, timeout=timeout, context=ctx)
    with r:
        return json.loads(r.read().decode("utf-8"))


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compute(payload, now, hours, ai_cfg):
    """يحوّل رد Open-Meteo إلى قائمة ساعات فيها WBGT والعلم. دالة نقية قابلة للاختبار."""
    h = payload.get("hourly") or {}
    times = h.get("time") or []
    rows = []
    start = now.replace(minute=0, second=0, microsecond=0)
    for i, stamp in enumerate(times):
        try:
            t = dt.datetime.fromisoformat(stamp).replace(tzinfo=TZ)
        except ValueError:
            continue
        if t < start:
            continue
        g = lambda k: _num((h.get(k) or [None] * len(times))[i])
        ta, rh, v10 = g("temperature_2m"), g("relative_humidity_2m"), g("wind_speed_10m")
        ghi, direct, p = g("shortwave_radiation"), g("direct_radiation"), g("surface_pressure")
        row = {"time": stamp, "ts": int(t.timestamp()), "temp": ta, "hum": rh,
               "wind10": v10, "solar": ghi, "wbgt": None, "flag": None}
        if None not in (ta, rh, v10, ghi):
            fdir = min(1.0, max(0.0, direct / ghi)) if (direct is not None and ghi > 0) else 0.0
            cz = cos_zenith(t - dt.timedelta(minutes=30), ai_cfg)
            try:
                w = wbgt_liljegren(ta, rh, v10, ghi, fdir, cz, p or ai_cfg["pressure_hpa"])
                row["wbgt"], row["flag"] = round(w, 1), wbgt_flag(w)
            except (ArithmeticError, ValueError):
                pass
        rows.append(row)
        if len(rows) >= hours:
            break
    return rows


def get(now=None):
    """استجابة /api/forecast. لا ترمي استثناءً؛ الخطأ يظهر في الحقل reason."""
    s = _settings()
    now = now or dt.datetime.now(TZ)
    t0 = time.time()
    with _lock:
        if _cache["data"] is not None and t0 - _cache["at"] < s["cache_s"]:
            return _cache["data"]
    ai_cfg = load_config()
    q = urllib.parse.urlencode({
        "latitude": ai_cfg["latitude"], "longitude": ai_cfg["longitude"],
        "hourly": HOURLY, "wind_speed_unit": "ms",
        "timezone": "Asia/Riyadh", "forecast_days": 2}, safe=",")
    try:
        payload = _fetch(s["url"] + "?" + q, s["timeout_s"])
        rows = compute(payload, now, int(s["hours"]), ai_cfg)
        if not rows:
            raise ValueError("رد Open-Meteo لا يحوي ساعات قادمة")
        data = {"available": True, "stale": False, "source": "open-meteo",
                "fetched_at": int(t0), "location": {"lat": ai_cfg["latitude"],
                                                    "lon": ai_cfg["longitude"]},
                "hours": rows,
                "note": "توقع الطقس من Open-Meteo، وWBGT محسوب بدالة Liljegren نفسها؛ "
                        "لا يعتمد على قراءات عمود الاختبار."}
        with _lock:
            _cache.update(at=t0, data=data)
        return data
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        with _lock:
            old, age = _cache["data"], t0 - _cache["at"]
        if old is not None and age <= s["stale_ok_s"]:
            return dict(old, stale=True)
        return {"available": False,
                "reason": "تعذر جلب التوقع من Open-Meteo (يلزم اتصال بالإنترنت): %s" % exc}
