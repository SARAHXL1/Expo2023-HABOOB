"""
GET /api/platform/live — بيانات «عمود الاختبار» بالشكل الذي تفهمه منصة التشغيل.

المنصة لا تعرف شيئًا عن رسائل ESP32: هذه الوحدة تترجم آخر لقطة لكل عقدة
إلى عمود (pole) ومنطقة (zone) وتنبيهات، بنفس أسماء الحقول في بيانات العرض.
"""
import time

import processing
import storage
from settings import cfg, mode

OK_LIKE = {"ok", "disabled", "assumed"}


def _pole_meta(node_id, simulated, index):
    poles = cfg().get("platform", {}).get("test_poles", {})
    meta = poles.get(node_id, {})
    default_id = ("HB-S%02d" if simulated else "HB-T%02d") % (index + 1)
    return meta.get("pole_id", default_id), meta.get("zone", "Z")


def _pole_status(view):
    if not view.get("online"):
        return "offline"
    bad = [s for s in view["sensors"].values() if s["status"] not in OK_LIKE]
    return "warning" if bad else "online"


def _alert_id(pole_id, code, seen):
    """معرّف ثابت بين التحديثات (قبل: رقم الترتيب) حتى تبقى حالة «مقروء» في المنصة."""
    seen[code] = seen.get(code, 0) + 1
    return "L-%s-%s" % (pole_id, code) + ("" if seen[code] == 1 else "-%d" % seen[code])


def _alerts(view, pole_id):
    """تنبيهات الخادم بصيغة تنبيهات المنصة (sev / type / iv)."""
    sev_map = {"critical": "crit", "warning": "cau", "info": "info"}
    out, seen = [], {}
    for i, a in enumerate(view.get("alerts", [])):
        if a["severity"] == "info" and not a["code"].startswith("WBGT"):
            continue                      # ملاحظات الحساب تبقى في موقع الاختبار فقط
        heat = a["code"].startswith("WBGT-") and a["code"] != "WBGT-NOTE"
        out.append({
            "id": _alert_id(pole_id, a["code"], seen), "code": a["code"],
            "sev": sev_map.get(a["severity"], "info") if not heat else
                   ("crit" if a["severity"] == "critical" else "heat"),
            "type": "heat" if heat else "sensor",
            "iv": "auto" if heat else "maint",
            "status": "active", "read": False, "target": pole_id,
            "time": time.strftime("%H:%M", time.localtime(view.get("rx_ts") or time.time())),
            "title": {"ar": a["text"], "en": a["code"]},
            "problem": {"ar": a["text"], "en": a["text"]},
            "rec": {"ar": a.get("hint") or "", "en": a.get("hint") or ""},
        })
    return out


def live():
    zone_cfg = cfg().get("platform", {}).get("test_zone", {})
    poles, alerts = [], []
    nodes = processing.nodes_view()
    for i, n in enumerate(nodes):
        view = processing.latest_view(n["node_id"])
        if view is None:
            continue
        pid, zid = _pole_meta(n["node_id"], n["simulated"], i)
        d, v = view["derived"], view["values"]
        poles.append({
            "id": pid, "node_id": n["node_id"], "zone": zid, "k": i % 2,
            "simulated": n["simulated"], "transport": view.get("transport"),
            "status": _pole_status(view), "last_s": view.get("age_s"),
            "temp": v.get("ta_c"), "hum": v.get("rh_pct"),
            "wind": v.get("wind_ms"), "wind10": d.get("wind_10m_ms"),
            "solar": d.get("solar_wm2"), "lux": v.get("lux"),
            "wbgt": d.get("wbgt_c"), "flag": d.get("flag"), "flag_ar": d.get("flag_ar"),
            "method": d.get("wbgt_method"), "reason": d.get("wbgt_reason"),
            "utci": d.get("utci_c"),
            "explain": d.get("explain"), "advice": d.get("advice"),
            "analysis": d.get("analysis"), "recommendation": d.get("recommendation"),
            "batt": None, "power": view.get("power_source"),
            "sensors": {k: s["status"] for k, s in view["sensors"].items()},
        })
        pole_alerts = _alerts(view, pid)
        if poles[-1]["status"] == "offline":   # علم WBGT من آخر قراءة قديمة لا يُعرض كتنبيه راهن
            pole_alerts = [x for x in pole_alerts if not x["code"].startswith("WBGT-")]
        alerts += pole_alerts

    # العمود الحقيقي هو مصدر المنطقة ولو انقطع؛ تُستخدم عقدة المحاكاة فقط إن لم توجد عقدة حقيقية
    main = next((p for p in poles if not p["simulated"]), poles[0] if poles else None)
    zone = {"id": zone_cfg.get("id", "Z"),
            "name": zone_cfg.get("name", {"ar": "منطقة الاختبار", "en": "Test zone"}),
            "live": True, "visitors": None, "mitigated": False,
            "temp": None, "hum": None, "wind": None, "solar": None,
            "wbgt": None, "flag": None, "explain": None, "advice": None,
            "analysis": None, "recommendation": None}
    if main and main["status"] != "offline":
        for k in ("temp", "hum", "wind", "solar", "wbgt", "flag", "explain", "advice",
                  "analysis", "recommendation", "method", "reason"):
            zone[k] = main.get(k)
    elif main:    # العمود منقطع: آخر قراءة ليست الحالة الراهنة، فتبقى القيم null ويظهر «—»
        zone["stale_s"] = main.get("last_s")
    return {"server_mode": mode(), "server_time": time.time(),
            "index": "wbgt", "zone": zone, "poles": poles, "alerts": alerts,
            "decisions": storage.recent_decisions(5)}
