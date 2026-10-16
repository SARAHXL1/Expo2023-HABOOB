#!/usr/bin/env python3
"""
خادم موقع اختبار الحساسات — مشروع الراحة الحرارية، تحدي 2.3.

يغطي القسم 6 من المتطلبات: SV-01 إلى SV-15، وواجهات القسم 6.2.

مبني على مكتبة Python القياسية فقط (http.server)، بلا إطار خارجي،
حتى يعمل على ويندوز وماك بلا إنترنت وبلا تثبيت إضافي (NF-01، NF-02).
المكتبة الوحيدة الخارجية هي pythermalcomfort للحسابات، وإن غابت
يبقى الموقع يعمل وتظهر رسالة واضحة بدل قيمة UTCI.

التشغيل:
    python3 02_server_backend/app.py              # الوضع العادي
    python3 02_server_backend/app.py --simulate   # مع وضع المحاكاة
    python3 02_server_backend/app.py --port 5001
"""

import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import calculations as ca          # noqa: E402
import forecast                    # noqa: E402
import heat_index                  # noqa: E402
import platform_view               # noqa: E402
import processing                  # noqa: E402
import simulator                   # noqa: E402
import storage                     # noqa: E402
from settings import (             # noqa: E402
    cfg, save, load, node_cfg, mode, set_mode, mrt_source, globe_enabled,
    effective_disabled, SENSOR_CATALOG, STATUS_AR,
)

WEB_DIR = os.path.join(ROOT, "web")   # / = منصة التشغيل · /bench/ = موقع اختبار الحساسات
START_TIME = time.time()
ACTIVE_PORT = None
_ingest_lock = threading.Lock()


# ---------------------------------------------------------------------------
# مسار الاستقبال المشترك: الواي فاي، وجسر USB، والمحاكاة كلها تمر من هنا (SV-01)
# ---------------------------------------------------------------------------
def ingest(msg, transport="wifi"):
    with _ingest_lock:
        processed = processing.process(msg, rx_ts=time.time(), transport=transport)
        storage.save_reading(processed, msg)
    return processed


def ingest_sim(msg, transport="sim"):
    return ingest(msg, transport)


# ---------------------------------------------------------------------------
# أدوات الشبكة
# ---------------------------------------------------------------------------
def local_ips():
    """SV-12 — عناوين IP الخاصة باللابتوب، ليكتبها المستخدم في إعدادات ESP32."""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # لا يُرسل شيئًا؛ يكشف الواجهة الخارجة فقط
        ip = s.getsockname()[0]
        s.close()
        if ip not in ips:
            ips.insert(0, ip)
    except Exception:
        pass
    return ips


# ---------------------------------------------------------------------------
# معالج الطلبات
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "ThermalComfortTestBench/1.0"
    protocol_version = "HTTP/1.1"

    # --- أدوات الرد ---
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        # JSON القياسي لا يعرف Infinity ولا NaN، ومتصفحات الويب ترفضهما.
        # نحوّلهما إلى null قبل الإرسال حتى لا تنكسر اللوحة.
        self._send(code, json.dumps(_safe(obj), ensure_ascii=False, default=_jsonable))

    def _error(self, code, message_ar):
        self._json({"accepted": False, "error": message_ar}, code)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        return self.rfile.read(n).decode("utf-8", "replace") if n else ""

    def log_message(self, fmt, *args):
        # سجل مختصر: نتجاهل طلبات اللوحة المتكررة حتى لا تغرق الطرفية
        path = args[0] if args else ""
        if any(q in str(path) for q in ("/api/latest", "/api/nodes", "/api/history",
                                         "/api/platform")):
            return
        sys.stderr.write("  %s  %s\n" % (time.strftime("%H:%M:%S"), str(path)))

    # --- التوجيه ---
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/nodes":
                return self._json({"nodes": processing.nodes_view(),
                                   "mode": mode(),
                                   "server_time": time.time()})
            if path == "/api/latest":
                return self._api_latest(q)
            if path == "/api/platform/live":
                return self._json(platform_view.live())
            if path == "/api/forecast":
                return self._json(forecast.get())
            if path == "/api/history":
                return self._api_history(q)
            if path == "/api/errors":
                return self._json({"errors": storage.recent_errors()})
            if path == "/api/export.csv":
                return self._api_export(q)
            if path == "/api/meta":
                return self._api_meta()
            if path == "/api/simulation":
                return self._json(simulator.status())
            if path == "/api/mode":
                return self._json(self._mode_payload())
            if path == "/api/health":
                return self._json({
                    "ok": True, "server_time": time.time(),
                    "uptime_s": round(time.time() - START_TIME, 1),
                    "mode": mode(),
                    "mrt_source": mrt_source(),
                    "pythermalcomfort": ca.LIB_OK,
                    "thermofeel": heat_index.LILJEGREN_OK,
                    "storage": storage.stats(),
                })
            if path in ("/", "/index.html"):
                return self._static("index.html")
            return self._static(path.lstrip("/"))
        except BrokenPipeError:
            pass
        except Exception as exc:
            self._error(500, "خطأ داخلي في الخادم: %s" % exc)

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain", {
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/readings":
                return self._api_readings()
            if path == "/api/platform/decision":
                return self._api_decision()
            if path == "/api/calibration":
                return self._api_calibration()
            if path == "/api/simulation":
                return self._api_simulation()
            if path == "/api/config":
                return self._api_config()
            if path == "/api/mode":
                return self._api_mode()
            return self._error(404, "المسار غير موجود: %s" % path)
        except BrokenPipeError:
            pass
        except Exception as exc:
            self._error(500, "خطأ داخلي في الخادم: %s" % exc)

    # --- SV-01، SV-02: استقبال رسالة ---
    def _api_readings(self):
        raw = self._body()
        source = self.headers.get("X-Transport") or "wifi"
        if source not in ("wifi", "usb", "sim", "test"):
            source = "wifi"
        try:
            msg = json.loads(raw)
        except Exception as exc:
            rec = storage.save_rejected("JSON غير صالح: %s" % exc, raw, source)
            return self._json({"accepted": False, "error": rec["reason"]}, 400)

        try:
            processed = ingest(msg, source)
        except processing.ValidationError as exc:
            rec = storage.save_rejected(str(exc), raw, source)
            return self._json({"accepted": False, "error": rec["reason"]}, 400)

        d = processed["derived"]
        # رد الخادم كما في القسم 5.3، تعرضه الشاشة (FW-11)
        return self._json({
            "accepted": True,
            "utci_c": d.get("utci_c"),
            "stress_category": d.get("stress_category"),
            # مفتاح الفئة بالإنجليزي، تستخدمه الشاشة لاختيار اللون،
            # لأن مكتبة Adafruit GFX لا تعرض الحروف العربية
            "stress_key": d.get("stress_key"),
            "mrt_c": d.get("mrt_c"),
            # 5.3 — مصدر MRT: assumed (تساوي حرارة الهواء) أو globe
            "mrt_source": d.get("mrt_source"),
            "server_time": int(time.time()),
            "alerts": len(processed["alerts"]),
            # المؤشر الرئيسي (دليل علم البيانات v3): تقرؤه الشاشة من الإصدار 0.4.0
            "wbgt_c": d.get("wbgt_c"),
            "flag": d.get("flag"),
        })

    # --- POST /api/platform/decision: «تفعيل الآن» في وضع عمود الاختبار ---
    def _api_decision(self):
        try:
            d = json.loads(self._body())
            assert isinstance(d, dict)
        except Exception:
            return self._error(400, "جسم الطلب ليس JSON صالحًا.")
        ok = {"shading", "fans", "coolingSys", "misting"}
        systems = [x for x in (d.get("systems") or []) if x in ok]
        if not systems:
            return self._error(400, "لا نظام معروف في القرار.")
        rec = storage.save_decision({
            "node_id": d.get("node_id"), "pole_id": d.get("pole_id"), "zone": d.get("zone"),
            "systems": systems, "wbgt_c": d.get("wbgt_c"), "flag": d.get("flag"),
            "expected_c": d.get("expected_c"), "expected_flag": d.get("expected_flag")})
        return self._json({"accepted": True, **rec})

    # --- GET /api/latest ---
    def _api_latest(self, q):
        current = mode()
        nodes = processing.nodes_view()
        visible = {n["node_id"] for n in nodes}

        node = (q.get("node") or [None])[0]
        # عقدة من الوضع الآخر لا تُعرض هنا: نتجاهل الاختيار ونعود لعقد الوضع الحالي
        if node and node not in visible:
            node = None
        if not node:
            if not nodes:
                if current == "live":
                    # وضع العتاد: نعرض كل البطاقات «غير متصل» بدل صفحة فارغة
                    view = processing.skeleton_view()
                    view["mode"] = current
                    return self._json(view)
                return self._json({
                    "available": False, "mode": current,
                    "message": "وضع المحاكاة متوقف ولم تصل أي رسالة. "
                               "شغّل المحاكاة من قسم «أدوات»."})
            node = nodes[0]["node_id"]

        view = processing.latest_view(node)
        if view is None:
            return self._json({"available": False, "mode": current,
                               "message": "لا توجد بيانات للعقدة «%s» بعد." % node})
        view["available"] = True
        view["skeleton"] = False
        view["mode"] = current
        return self._json(view)

    # --- GET /api/history ---
    def _api_history(self, q):
        nodes = processing.nodes_view()
        visible = {n["node_id"] for n in nodes}
        node = (q.get("node") or [None])[0]
        if node and node not in visible:
            node = None
        if not node:
            node = nodes[0]["node_id"] if nodes else None
        if not node:
            return self._json({"series": {}, "node_id": None, "mode": mode()})
        try:
            minutes = int((q.get("minutes") or [cfg()["timing"]["history_minutes_default"]])[0])
        except ValueError:
            minutes = 15
        minutes = max(1, min(minutes, 180))
        return self._json({"node_id": node, "minutes": minutes,
                           "series": storage.history(node, minutes)})

    # --- GET /api/export.csv (SV-10) ---
    def _api_export(self, q):
        node = (q.get("node") or [None])[0]
        ts_from = (q.get("from") or [None])[0]
        ts_to = (q.get("to") or [None])[0]
        text = storage.export_csv(node, ts_from, ts_to)
        name = "readings_%s_%s.csv" % (node or "all", time.strftime("%Y%m%d_%H%M%S"))
        self._send(200, text, "text/csv; charset=utf-8",
                   {"Content-Disposition": 'attachment; filename="%s"' % name})

    # --- POST /api/calibration (SV-15) ---
    def _api_calibration(self):
        try:
            payload = json.loads(self._body())
        except Exception as exc:
            return self._error(400, "JSON غير صالح: %s" % exc)

        node = payload.get("node_id")
        if not node:
            return self._error(400, "الحقل node_id مطلوب.")

        allowed = ("wind_k", "wind_b", "wind_v_min", "wind_height_m",
                   "globe_offset_c", "recompute_wind_on_server", "name")
        c = json.loads(json.dumps(cfg()))          # نسخة للتعديل
        nodes = c.setdefault("nodes", {})
        entry = nodes.setdefault(node, dict(c.get("node_defaults", {})))
        changed = {}
        for key in allowed:
            if key in payload:
                val = payload[key]
                if key == "recompute_wind_on_server":
                    val = bool(val)
                elif key != "name":
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        return self._error(400, "القيمة «%s» ليست رقمًا." % key)
                entry[key] = val
                changed[key] = val
        if not changed:
            return self._error(400, "لم تُرسل أي قيمة للحفظ.")
        save(c)
        return self._json({"accepted": True, "node_id": node, "saved": changed,
                           "node_settings": node_cfg(node),
                           "message": "حُفظت معاملات المعايرة، وستُطبّق على الرسائل القادمة."})

    # --- POST /api/simulation (SV-13) ---
    def _api_simulation(self):
        try:
            payload = json.loads(self._body() or "{}")
        except Exception as exc:
            return self._error(400, "JSON غير صالح: %s" % exc)

        action = payload.get("action")
        if action == "start":
            simulator.start(ingest_sim)
        elif action == "stop":
            simulator.stop()
        elif action == "faults":
            simulator.set_faults(payload.get("node_id"), payload.get("faults") or {})
        elif action is not None:
            return self._error(400, "إجراء غير معروف: %s" % action)
        return self._json(simulator.status())

    # --- POST /api/config: تعديل الإعدادات الحية من اللوحة ---
    def _api_config(self):
        try:
            payload = json.loads(self._body() or "{}")
        except Exception as exc:
            return self._error(400, "JSON غير صالح: %s" % exc)
        c = json.loads(json.dumps(cfg()))
        if "disabled_sensors" in payload:
            vals = payload["disabled_sensors"]
            if not isinstance(vals, list):
                return self._error(400, "disabled_sensors يجب أن تكون قائمة.")
            c["disabled_sensors"] = [str(v) for v in vals]
        if "calibration_mode" in payload:
            c.setdefault("checks", {})["calibration_mode"] = bool(payload["calibration_mode"])
        save(c)
        return self._json({"accepted": True, "config": {
            "disabled_sensors": c.get("disabled_sensors", []),
            "calibration_mode": c.get("checks", {}).get("calibration_mode", False),
        }})

    # --- الوضع: العتاد الحقيقي أو المحاكاة ---
    def _mode_payload(self):
        current = mode()
        nodes = processing.nodes_view()
        return {
            "mode": current,
            "mode_ar": "العتاد الحقيقي" if current == "live" else "المحاكاة",
            "simulation_running": simulator.status()["running"],
            "nodes": nodes,
            "node_count": len(nodes),
            "sim_nodes": cfg()["simulation"].get("nodes", []),
        }

    def _api_mode(self):
        try:
            payload = json.loads(self._body() or "{}")
        except Exception as exc:
            return self._error(400, "JSON غير صالح: %s" % exc)

        want = payload.get("mode")
        if want not in ("live", "sim"):
            return self._error(400, "الوضع يجب أن يكون live أو sim.")

        if want == mode():
            return self._json(dict(self._mode_payload(),
                                   message="الوضع لم يتغيّر."))

        set_mode(want)
        if want == "live":
            # وضع العتاد: نوقف المحاكاة فورًا حتى لا تختلط بيانات وهمية بالقراءات
            simulator.stop()
            msg = ("وضع العتاد الحقيقي. أُوقفت المحاكاة، وتُعرض الآن العقد "
                   "الموصولة عبر الواي فاي أو USB فقط.")
        else:
            simulator.start(ingest_sim)
            msg = "وضع المحاكاة. تُولَّد بيانات وهمية بلا أي عتاد."

        return self._json(dict(self._mode_payload(), message=msg))

    # --- GET /api/meta: كل ما تحتاجه اللوحة لتبني نفسها ---
    def _api_meta(self):
        c = cfg()
        return self._json({
            "sensors": [{"id": s["id"], "ar": s["ar"], "tech": s["tech"],
                         "port": s["port"], "fields": s["fields"]}
                        for s in SENSOR_CATALOG],
            "status_ar": STATUS_AR,
            "ranges": c["ranges"],
            "stress_bands": [{"min": lo, "max": hi, "key": k, "ar": ar}
                             for lo, hi, k, ar in ca.STRESS_BANDS],
            "timing": c["timing"],
            "disabled_sensors": sorted(effective_disabled()),
            "calibration_mode": c.get("checks", {}).get("calibration_mode", False),
            "mode": mode(),
            "mrt_source": mrt_source(),
            "globe_enabled": globe_enabled(),
            "pythermalcomfort": ca.LIB_OK,
            "pythermalcomfort_error": ca.LIB_ERROR,
            "server_ips": local_ips(),
            "port": globals().get("ACTIVE_PORT", c["server"]["port"]),
        })

    # --- الملفات الساكنة (UI-02: كلها محلية، بلا أي طلب للإنترنت) ---
    def _static(self, rel):
        rel = urllib.parse.unquote(rel)
        if not rel:
            rel = "index.html"
        target = os.path.normpath(os.path.join(WEB_DIR, rel))
        if target.startswith(WEB_DIR) and os.path.isdir(target):
            if not rel.endswith("/"):            # /bench ← /bench/ حتى تعمل الروابط النسبية
                return self._send(301, b"", "text/plain", {"Location": "/" + rel + "/"})
            target = os.path.join(target, "index.html")
        if not target.startswith(WEB_DIR) or not os.path.isfile(target):
            return self._error(404, "الملف غير موجود: %s" % rel)
        ctype, _ = mimetypes.guess_type(target)
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(target, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)


def _safe(o):
    """يستبدل NaN و±Infinity بـ null في أي مكان من الكائن."""
    if isinstance(o, float):
        return o if (o == o and o not in (float("inf"), float("-inf"))) else None
    if isinstance(o, dict):
        return {k: _safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_safe(v) for v in o]
    return o


def _jsonable(o):
    try:
        import numpy as np
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    return str(o)


# ---------------------------------------------------------------------------
# مهمة دورية: تنظيف قاعدة البيانات (NF-04)
# ---------------------------------------------------------------------------
def _janitor():
    while True:
        time.sleep(300)
        try:
            storage.prune()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# التشغيل
# ---------------------------------------------------------------------------
BANNER = """
══════════════════════════════════════════════════════════════════
  هبوب — موقع اختبار الحساسات
  مشروع هاكثون إكسبو 2030 الرياض · تحدي 2.3
══════════════════════════════════════════════════════════════════"""


def bind_server(host, port, fallback=True):
    """
    يفتح المنفذ قبل طباعة أي شيء، حتى لا نطبع عنوانًا لا يعمل.

    ملاحظة مهمة لمستخدمي ماك: المنفذ 5000 يحجزه «مستقبل AirPlay» في macOS
    (عملية ControlCenter)، وهذا أكثر سبب لفشل التشغيل من أول مرة.
    لذلك نجرّب المنافذ التالية تلقائيًا بدل أن نتوقف.
    """
    tried = []
    candidates = [port] + ([port + i for i in range(1, 6)] if fallback else [])
    for p in candidates:
        try:
            httpd = ThreadingHTTPServer((host, p), Handler)
            httpd.daemon_threads = True
            return httpd, p, tried
        except OSError as exc:
            if getattr(exc, "errno", None) not in (48, 98, 10048):   # المنفذ مشغول
                raise
            tried.append(p)
    return None, None, tried


def main():
    ap = argparse.ArgumentParser(description="خادم موقع اختبار الحساسات")
    ap.add_argument("--port", type=int, default=None, help="منفذ الخادم (الافتراضي من config.json)")
    ap.add_argument("--host", default=None, help="عنوان الاستماع (الافتراضي 0.0.0.0)")
    ap.add_argument("--simulate", action="store_true",
                    help="بدء الخادم في وضع المحاكاة (بيانات وهمية بلا عتاد)")
    ap.add_argument("--live", action="store_true",
                    help="بدء الخادم في وضع العتاد الحقيقي (بلا أي محاكاة)")
    ap.add_argument("--no-fallback", action="store_true",
                    help="لا تجرّب منفذًا بديلًا إن كان المنفذ مشغولًا")
    args = ap.parse_args()

    load(force=True)
    c = cfg()
    host = args.host or c["server"]["host"]
    want_port = args.port or c["server"]["port"]

    httpd, port, tried = bind_server(host, want_port, fallback=not args.no_fallback)
    if httpd is None:
        print(BANNER)
        print("\n  ✕ تعذر فتح أي منفذ. المنافذ المشغولة: %s"
              % "، ".join(str(p) for p in tried))
        print("\n  الأسباب الشائعة:")
        print("    • على ماك: «مستقبل AirPlay» يحجز المنفذ 5000.")
        print("      أطفئه من: إعدادات النظام ← عام ← AirDrop و Handoff ← مستقبل AirPlay")
        print("    • نسخة أخرى من الخادم ما زالت تعمل في نافذة طرفية أخرى.")
        print("\n  الحل الأسرع: شغّله على منفذ آخر، مثل:")
        print("      python3 02_server_backend/app.py --port 5050\n")
        return 1

    storage.init()
    threading.Thread(target=_janitor, name="janitor", daemon=True).start()

    # المحاكاة لا تعمل إطلاقًا في وضع العتاد الحقيقي، حتى لو طُلبت بـ --simulate
    if args.live:
        set_mode("live")
    elif args.simulate:
        set_mode("sim")
    c = cfg()

    if c.get("mode", "sim") == "sim" and (args.simulate or c["simulation"].get("enabled")):
        simulator.start(ingest_sim)

    print(BANNER)
    if tried:
        print("\n  ⚠ المنفذ %d مشغول، فشُغّل الخادم على المنفذ %d بدلًا منه."
              % (tried[0], port))
        if tried[0] == 5000 and sys.platform == "darwin":
            print("    (على ماك يحجز «مستقبل AirPlay» المنفذ 5000. يمكن إطفاؤه من:")
            print("     إعدادات النظام ← عام ← AirDrop و Handoff ← مستقبل AirPlay)")
        print("    تذكّر أن تكتب المنفذ %d في إعدادات ESP32." % port)

    print("  WBGT      : %s" % ("thermofeel جاهزة (Liljegren)" if heat_index.LILJEGREN_OK else
                                   "⚠ thermofeel غير مثبّتة — الصيغة الاحتياطية فقط. "
                                   "نفّذ: pip install thermofeel==2.3.0"))
    print("\n  الحسابات  : %s" % ("pythermalcomfort جاهزة" if ca.LIB_OK else
                                   "⚠ pythermalcomfort غير مثبّتة — لن تُحسب UTCI. "
                                   "نفّذ: pip install pythermalcomfort"))
    print("  قاعدة البيانات: %s" % storage.stats()["db_path"])
    _m = cfg().get("mode", "sim")
    if _m == "live":
        print("  الوضع     : 🔌 العتاد الحقيقي — تُعرض العقد الموصولة فقط، والمحاكاة متوقفة")
    else:
        print("  الوضع     : 🧪 المحاكاة — بيانات وهمية بلا عتاد (%s)"
              % ("تعمل" if simulator.status()["running"] else "متوقفة"))
    print("  يُبدَّل الوضع من أعلى اللوحة، أو بـ --live / --simulate عند التشغيل")
    print("\n  افتح اللوحة على هذا اللابتوب:")
    print("      http://localhost:%d          ← منصة التشغيل" % port)
    print("      http://localhost:%d/bench/   ← موقع اختبار الحساسات" % port)
    ips = local_ips()
    if ips:
        print("\n  عناوين اللابتوب على الشبكة (SV-12) — اكتب أحدها في إعدادات ESP32:")
        for ip in ips:
            print('      const char* SERVER_URL = "http://%s:%d/api/readings";' % (ip, port))
        print("\n  ومن جوال أو لابتوب آخر على نفس الشبكة افتح:")
        print("      http://%s:%d" % (ips[0], port))
    else:
        print("\n  ⚠ تعذر معرفة عنوان IP. استخدم ipconfig في ويندوز أو ifconfig في ماك.")
    print("\n  للإيقاف: Ctrl+C")
    print("══════════════════════════════════════════════════════════════════\n")
    sys.stdout.flush()   # حتى تظهر هذه الرسائل فورًا، وإن وُجّه الخرج إلى ملف

    # يُستخدم في /api/meta حتى تعرض اللوحة المنفذ الفعلي لا المطلوب
    globals()["ACTIVE_PORT"] = port

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  إيقاف الخادم…")
    finally:
        simulator.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
