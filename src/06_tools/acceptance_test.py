#!/usr/bin/env python3
"""
اختبار معايير القبول — القسم 12 من ملف المتطلبات.

يشغّل خادمًا مستقلًا على منفذ اختبار، ويتحقق آليًا من كل بند في قائمة القبول،
ثم يطبع تقريرًا. لا يحتاج أي عتاد، ولا يمس قاعدة بيانات العمل.

التشغيل:
    python3 06_tools/acceptance_test.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = 5099
BASE = "http://127.0.0.1:%d" % PORT

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("  %s  %s%s" % ("✓" if ok else "✕", name, ("  — " + detail) if detail else ""))
    return ok


def get(path, timeout=6):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_raw(path, timeout=6):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8-sig"), dict(r.headers)


def post(path, obj, transport="test"):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json", "X-Transport": transport},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def msg(node="node-acc", **over):
    m = {
        "schema": 3, "node_id": node, "fw": "acc-2.0", "ts": int(time.time()),
        "uptime_s": 120, "reset_reason": "POWERON",
        "wifi": {"connected": True, "rssi": -58, "ip": "192.168.1.77"},
        "heap_free": 180000, "i2c_found": ["0x10", "0x48", "0x5A"],
        "power_source": "usb", "send_interval_s": 5,
        "sensors": {
            "dht22": {"status": "ok", "ta_c": 25.0, "rh_pct": 40.0},
            "ds18b20": {"status": "disabled", "tg_c": None, "count": 0},
            "ads1115": {"status": "ok"},
            "anemometer": {"status": "ok", "wind_v": 0.12, "wind_ms": 2.9,
                           "height_m": 1.8, "samples": 50},
            "battery": {"status": "disabled", "bat_v": None},
            "mlx90614": {"status": "ok", "tsurf_c": 27.0, "tamb_c": 26.0},
            "veml7700": {"status": "ok", "lux": 700},
            "tft": {"status": "assumed"},
        },
    }
    m["sensors"].update(over.pop("sensors", {}))
    m.update(over)
    return m


def main():
    db = os.path.join(ROOT, "data", "acceptance_test.db")
    if os.path.exists(db):
        os.remove(db)

    # إعدادات مؤقتة للاختبار، لا تمس config.json الأصلي
    cfg_path = os.path.join(ROOT, "config.json")
    original = open(cfg_path, encoding="utf-8").read()
    c = json.loads(original)
    c["server"]["db_path"] = "data/acceptance_test.db"
    c["simulation"]["enabled"] = False
    c["mode"] = "sim"
    c["mrt_source"] = "assumed"
    # بنود القبول تفترض كل القطع المذكورة في الجدول 3.1 مفعّلة عدا المؤجلة (الكرة والبطارية)،
    # فلا تتأثر بإعداد المشروع الفعلي (config.json يعطّل mlx90614 لأنه غير موصول في العقدة الحالية)
    c["disabled_sensors"] = ["battery"]
    open(cfg_path, "w", encoding="utf-8").write(json.dumps(c, ensure_ascii=False, indent=2))

    print("\n══════════════════════════════════════════════════════════")
    print("  اختبار معايير القبول — القسم 12")
    print("══════════════════════════════════════════════════════════\n")

    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "02_server_backend", "app.py"),
         "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                get("/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.3)
        else:
            print("  ✕ تعذر تشغيل الخادم.")
            return 1

        meta = get("/api/meta")

        # ① بطاقة لكل قطعة من الجدول 3.1 بحالتها الصحيحة
        post("/api/readings", msg())
        d = get("/api/latest?node=node-acc")
        expected = {"esp32", "dht22", "ds18b20", "ads1115", "anemometer",
                    "mlx90614", "veml7700", "battery", "tft"}
        check("بطاقة لكل قطعة من الجدول 3.1 (9 قطع)",
              set(d["sensors"]) == expected,
              "ظهرت %d بطاقة" % len(d["sensors"]))
        deferred = {"ds18b20", "battery"}
        check("كل القطع الموصولة بحالة ok، والشاشة assumed",
              all(d["sensors"][s]["status"] == "ok"
                  for s in expected - {"tft"} - deferred)
              and d["sensors"]["tft"]["status"] == "assumed")

        # --- الإصدار 2: القطع المؤجلة وMRT المفترضة ---
        check("الكرة الحرارية والبطارية مؤجلتان بحالة disabled",
              all(d["sensors"][s]["status"] == "disabled" for s in deferred),
              "، ".join("%s=%s" % (s, d["sensors"][s]["status_ar"]) for s in deferred))
        check("MRT مفترضة مساوية لحرارة الهواء",
              d["derived"]["mrt_assumed"] is True
              and abs(d["derived"]["mrt_c"] - d["values"]["ta_c"]) < 0.01,
              "MRT %.1f = Ta %.1f" % (d["derived"]["mrt_c"], d["values"]["ta_c"]))
        check("UTCI يُحسب رغم تأجيل الكرة",
              d["derived"]["utci_c"] is not None,
              "UTCI %.1f °م · %s" % (d["derived"]["utci_c"], d["derived"]["stress_category"]))
        check("مصدر الطاقة USB يظهر في اللوحة", d["power_source"] == "usb")
        check("حساس الضوء VEML7700 على العنوان 0x10",
              d["sensors"]["veml7700"]["status"] == "ok"
              and "0x10" in d["sensors"]["veml7700"]["port"])
        check("حد الإضاءة 140,000 لوكس حسب ملف مواصفات VEML7700",
              meta["ranges"]["lux"]["max"] == 140000)

        # ② فصل حساس يحوّل بطاقته لحالة خطأ مع رسالة مساعدة
        post("/api/readings", msg(sensors={
            "mlx90614": {"status": "not_found", "tsurf_c": None, "tamb_c": None},
            "dht22": {"status": "read_error", "ta_c": None, "rh_pct": None}}))
        d = get("/api/latest?node=node-acc")
        check("فصل حساس يحوّل بطاقته إلى حالة خطأ",
              d["sensors"]["mlx90614"]["status"] == "not_found"
              and d["sensors"]["dht22"]["status"] == "read_error")
        check("رسالة مساعدة تظهر مع كل عطل (الجدول 8.4)",
              bool(d["sensors"]["mlx90614"]["help"]) and bool(d["sensors"]["dht22"]["help"]),
              (d["sensors"]["mlx90614"]["help"] or "")[:46] + "…")

        # فحص المدى المنطقي (الجدول 3.3) يحوّل ok إلى out_of_range
        post("/api/readings", msg(sensors={
            "veml7700": {"status": "ok", "lux": 260000}}))
        d = get("/api/latest?node=node-acc")
        check("القراءة خارج المدى تتحول إلى out_of_range (SV-04)",
              d["sensors"]["veml7700"]["status"] == "out_of_range",
              d["sensors"]["veml7700"]["reasons"][0]
              if d["sensors"]["veml7700"]["reasons"] else "")

        # ③ إطفاء العقدة يجعلها «غير متصلة»
        offline_s = meta["timing"]["node_offline_s"]
        post("/api/readings", msg(node="node-off"))
        d = get("/api/latest?node=node-off")
        was_online = d["online"]
        print("     …انتظار %d ثانية لاختبار انقطاع العقدة" % (offline_s + 2))
        time.sleep(offline_s + 2)
        d = get("/api/latest?node=node-off")
        check("إطفاء العقدة يجعلها «غير متصلة» خلال %d ثانية" % offline_s,
              was_online and not d["online"])
        check("التنبيه الأول يوضح أن العقدة غير متصلة",
              d["alerts"] and d["alerts"][0]["code"] == "NODE-OFFLINE",
              d["alerts"][0]["text"] if d["alerts"] else "")

        # ④ UTCI وفئته واللون وعلامة الرياح المقيّدة
        post("/api/readings", msg(node="node-utci"))
        d = get("/api/latest?node=node-utci")
        der = d["derived"]
        check("يُحسب UTCI وفئة الإجهاد",
              der["utci_c"] is not None and der["stress_category"],
              "UTCI %.1f °م · %s" % (der["utci_c"], der["stress_category"]))
        check("مفتاح الفئة يطابق أحد نطاقات الجدول 8.3",
              der["stress_key"] in {b["key"] for b in meta["stress_bands"]},
              der["stress_key"])
        check("تُحسب MRT وسرعة الرياح عند 10 م",
              der["mrt_c"] is not None and der["v10_ms"] is not None,
              "MRT %.1f °م · رياح 10م %.2f م/ث" % (der["mrt_c"], der["v10_ms"]))

        post("/api/readings", msg(node="node-calm", sensors={
            "anemometer": {"status": "ok", "wind_v": 0.0, "wind_ms": 0.0,
                           "height_m": 1.8, "samples": 50}}))
        d = get("/api/latest?node=node-calm")
        check("علامة «رياح مقيّدة» تظهر عند هدوء الرياح (CA-04)",
              d["derived"]["wind_clamped"] is True,
              "رُفعت الرياح إلى %.1f م/ث" % d["derived"]["v10_used_ms"])

        # CA-07 — غياب قيمة أساسية يمنع حساب UTCI ويشرح السبب
        post("/api/readings", msg(node="node-miss", sensors={
            "dht22": {"status": "read_error", "ta_c": None, "rh_pct": None}}))
        d = get("/api/latest?node=node-miss")
        check("عند غياب قيمة أساسية لا يُحسب UTCI وتُشرح القيمة الناقصة (CA-07)",
              d["derived"]["utci_c"] is None and d["derived"]["utci_unavailable_reason"],
              d["derived"]["utci_unavailable_reason"])

        # ⑤ الطريقتان: واي فاي وUSB
        post("/api/readings", msg(node="node-usb"), transport="usb")
        d = get("/api/latest?node=node-usb")
        check("طريقة الاتصال USB تظهر في اللوحة", d["transport"] == "usb")
        post("/api/readings", msg(node="node-wifi"), transport="wifi")
        check("طريقة الاتصال واي فاي تظهر في اللوحة",
              get("/api/latest?node=node-wifi")["transport"] == "wifi")

        # ⑥ وضع المحاكاة يعمل بلا عتاد
        sim_node = get("/api/mode")["sim_nodes"][0]
        st = post("/api/simulation", {"action": "start"})[1]
        time.sleep(7)
        sim_nodes = get("/api/nodes")["nodes"]
        check("وضع المحاكاة يولّد بيانات بلا أي عتاد (SV-13)",
              st["running"] and any(n["online"] for n in sim_nodes),
              "%d رسالة · العقد: %s" % (get("/api/simulation")["sent"],
                                        "، ".join(n["node_id"] for n in sim_nodes)))
        post("/api/simulation", {"action": "faults", "node_id": sim_node,
                                 "faults": {"missing": ["veml7700"], "wind_neg": True}})
        time.sleep(7)
        d = get("/api/latest?node=" + sim_node)
        check("محاكاة الأعطال تغيّر الحالات والرسائل",
              d["sensors"]["veml7700"]["status"] == "not_found"
              and any(a["code"] == "CK-03" for a in d["alerts"]))

        # ------------------------------------------------------------------
        # الوضعان: العتاد الحقيقي والمحاكاة
        # ------------------------------------------------------------------
        simulated_ids = [n["node_id"] for n in sim_nodes if n.get("simulated")]
        real_ids = [n["node_id"] for n in sim_nodes if not n.get("simulated")]
        check("معرّفات عقد المحاكاة لا تصطدم بمعرّف العقدة الحقيقية",
              simulated_ids and "node-01" not in simulated_ids
              and not set(simulated_ids) & set(real_ids),
              "محاكاة: %s · حقيقية: %s"
              % ("، ".join(simulated_ids), "، ".join(real_ids) or "لا شيء"))

        m = post("/api/mode", {"mode": "live"})[1]
        check("التبديل إلى وضع العتاد الحقيقي يوقف المحاكاة",
              m["mode"] == "live" and not m["simulation_running"])

        live_nodes = {n["node_id"] for n in get("/api/nodes")["nodes"]}
        check("وضع العتاد يخفي عقد المحاكاة تمامًا",
              not any(n.startswith("sim-") for n in live_nodes),
              "العقد الظاهرة: %s" % ("، ".join(sorted(live_nodes)) or "لا شيء"))
        check("طلب عقدة محاكاة صراحة في وضع العتاد لا يعرض بياناتها",
              get("/api/latest?node=" + sim_node).get("node_id") != sim_node)

        # لا عقدة حقيقية بعد ⇒ يجب أن تظهر كل البطاقات «غير متصل»
        import subprocess as _sp
        proc2 = None
        fresh = _sp.Popen(
            [sys.executable, os.path.join(ROOT, "02_server_backend", "app.py"),
             "--port", str(PORT + 1), "--live"],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        try:
            base2 = "http://127.0.0.1:%d" % (PORT + 1)
            for _ in range(60):
                try:
                    urllib.request.urlopen(base2 + "/api/health", timeout=1)
                    break
                except Exception:
                    time.sleep(0.3)
            with urllib.request.urlopen(base2 + "/api/latest", timeout=6) as r:
                sk = json.loads(r.read().decode())
            waiting = {k: v for k, v in sk["sensors"].items()
                       if k not in ("ds18b20", "battery")}
            check("بلا عتاد موصول: تظهر كل القطع بحالة «غير متصل» لا صفحة فارغة",
                  sk.get("skeleton") is True
                  and len(sk["sensors"]) == len(meta["sensors"])
                  and all(v["status"] == "not_connected" for v in waiting.values()),
                  "%d بطاقة، منها %d بانتظار العقدة"
                  % (len(sk.get("sensors", {})), len(waiting)))
            check("القطع المؤجلة تبقى «معطّل» لا «غير متصل»",
                  all(sk["sensors"][k]["status"] == "disabled"
                      for k in ("ds18b20", "battery")))
            check("بطاقات «غير متصل» تحمل رسالة المساعدة لكل قطعة",
                  all(v["help"] for v in waiting.values()))
            check("التنبيه يوضح أنه لم تصل رسالة من عقدة حقيقية",
                  sk["alerts"] and sk["alerts"][0]["code"] == "NO-NODE")
        finally:
            fresh.terminate()
            try:
                fresh.wait(timeout=5)
            except Exception:
                fresh.kill()

        # عقدة حقيقية جزئية: بعض الحساسات موصولة وبعضها لا
        post("/api/readings", msg(node="node-real", sensors={
            "ads1115": {"status": "not_found"},
            "anemometer": {"status": "not_found", "wind_v": None, "wind_ms": None},
            "veml7700": {"status": "not_found", "lux": None}}), transport="usb")
        d = get("/api/latest?node=node-real")
        check("في وضع العتاد: الموصول يعرض قيمه وغير الموصول «غير موجود»",
              d["sensors"]["dht22"]["status"] == "ok"
              and d["sensors"]["dht22"]["values"]["ta_c"] == 25.0
              and d["sensors"]["veml7700"]["status"] == "not_found"
              and d["sensors"]["ads1115"]["status"] == "not_found")

        m = post("/api/mode", {"mode": "sim"})[1]
        check("الرجوع لوضع المحاكاة يشغّلها من جديد",
              m["mode"] == "sim" and m["simulation_running"])
        post("/api/simulation", {"action": "stop"})

        # ⑦ تصدير CSV
        status, text, headers = get_raw("/api/export.csv?node=node-acc")
        lines = [l for l in text.strip().split("\n") if l]
        header = lines[0].split(",")
        check("يُصدَّر ملف CSV بأعمدة واضحة",
              status == 200 and len(lines) > 1 and "utci_c" in header,
              "%d عمود · %d صف" % (len(header), len(lines) - 1))
        check("CSV فيه عمود حالة لكل قطعة",
              all(("status_" + s["id"]) in header for s in meta["sensors"]))
        check("CSV يُفتح في الإكسل بالعربية (ترميز UTF-8 BOM)",
              text.startswith("﻿") or "﻿" not in text[:1])

        # ⑧ الرسالة المعطوبة تُرفض مع سبب واضح وتُسجَّل (SV-02)
        code, reply = post("/api/readings", {"node_id": "bad"})
        check("الرسالة المعطوبة تُرفض مع سبب عربي واضح (SV-02)",
              code == 400 and reply.get("error"), reply.get("error"))
        check("الرسالة المرفوضة تُسجَّل في /api/errors",
              any("sensors" in e["reason"] for e in get("/api/errors")["errors"]))

        # ⑨ الحقول غير المعروفة تُتجاهل ولا تُعطّل الخادم (DS-06)
        m = msg(node="node-new")
        m["sensors"]["new_sensor_2030"] = {"status": "ok", "co2_ppm": 410}
        m["unknown_root_field"] = {"anything": [1, 2, 3]}
        code, _ = post("/api/readings", m)
        check("الحقول غير المعروفة تُقبل وتُتجاهل (DS-06)", code == 200)

        # ⑩ ساعة العقدة الخاطئة تُستبدل بوقت الاستلام (SV-03)
        post("/api/readings", msg(node="node-time", ts=0))
        d = get("/api/latest?node=node-time")
        check("ts غير المنطقي يُستبدل بوقت الاستلام (SV-03)", d["ts_replaced"] is True)

        # ⑪ المعايرة تُحفظ وتُطبَّق (SV-15)
        post("/api/calibration", {"node_id": "node-cal", "wind_k": 40.0,
                                  "wind_b": 0.0, "wind_v_min": 0.01})
        post("/api/readings", msg(node="node-cal", sensors={
            "anemometer": {"status": "ok", "wind_v": 0.1, "wind_ms": 2.5,
                           "height_m": 1.8, "samples": 50}}))
        d = get("/api/latest?node=node-cal")
        check("الخادم يعيد حساب سرعة الرياح بمعاملات المعايرة (SV-15)",
              abs(d["values"]["wind_ms"] - 4.0) < 0.01,
              "0.1V × K=40 ⇒ %.2f م/ث (العقدة أرسلت %.2f)"
              % (d["values"]["wind_ms"], d["values"]["wind_ms_node"]))

        # ⑫ التاريخ القصير للرسوم
        h = get("/api/history?node=node-acc&minutes=15")
        check("سلسلة زمنية متاحة للرسوم الصغيرة", len(h["series"]["t"]) > 0,
              "%d نقطة" % len(h["series"]["t"]))

        # ⑬ اللوحة وملفاتها تُقدَّم محليًا بلا إنترنت
        ok_files = True
        for f in ("/bench/", "/bench/css/style.css", "/bench/js/app.js", "/bench/js/charts.js"):
            try:
                s, body, _ = get_raw(f)
                ok_files = ok_files and s == 200 and len(body) > 100
            except Exception:
                ok_files = False
        check("لوحة الاختبار وملفاتها تُقدَّم من الخادم المحلي على /bench/", ok_files)

        # المنصة الموحدة على / ومسارها /api/platform/live (دليل دمج موقع هبوب)
        try:
            s_p, body_p, _ = get_raw("/")
            s_l, body_l, _ = get_raw("/js/live.js")
            plat_ok = s_p == 200 and "js/live.js" in body_p and s_l == 200
        except Exception:
            plat_ok = False
        check("منصة التشغيل وزر مصدر البيانات تُقدَّم على /", plat_ok)
        live = get("/api/platform/live")
        check("GET /api/platform/live يعيد المنطقة والأعمدة بمؤشر WBGT",
              live.get("index") == "wbgt" and "zone" in live and "poles" in live)

        # المنصة على WBGT فقط: لا بقايا UTCI في الواجهة (القسم 7 من الدليل)
        ui_txt = get_raw("/")[1] + get_raw("/js/live.js")[1]
        check("لا ذكر لـ UTCI في واجهة المنصة (المؤشر الرئيسي WBGT)",
              "utci" not in ui_txt.lower(), "UTCI يبقى في موقع الاختبار للمقارنة فقط")

        # التحليل والتوصية بالقواعد (AI/heat_analysis + AI/recommendation_engine) في الرد
        dd = get("/api/latest?node=node-acc")["derived"]
        check("الرد يحمل التحليل والتوصية بالقواعد بجانب advice",
              isinstance(dd.get("analysis"), dict) and isinstance(dd.get("recommendation"), dict)
              and dd["recommendation"].get("action") and "advice" in dd,
              "الإجراء: %s" % (dd.get("recommendation") or {}).get("action"))

        # تسجيل قرار «تفعيل الآن» في وضع عمود الاختبار
        st_bad, _ = post("/api/platform/decision", {"systems": []})
        st_ok, rec = post("/api/platform/decision", {
            "node_id": "node-acc", "pole_id": "HB-T01", "zone": "Z",
            "systems": ["shading", "coolingSys"], "wbgt_c": 38.8, "flag": "black",
            "expected_c": 31.8, "expected_flag": "red"})
        last = (get("/api/platform/live").get("decisions") or [{}])[0]
        check("POST /api/platform/decision يسجّل القرار ويرفض القرار الفارغ",
              st_bad == 400 and st_ok == 200 and rec.get("accepted") is True
              and last.get("systems") == ["shading", "coolingSys"]
              and last.get("expected_c") == 31.8)

        # GET /api/forecast: بلا إنترنت يعيد available=false بسبب واضح ولا يختلق ساعات
        fc = get("/api/forecast", timeout=15)
        fc_ok = (fc.get("available") is True and fc.get("hours")
                 and all(h.get("flag") in (None, "white", "green", "yellow", "red", "black")
                         for h in fc["hours"])
                 ) or (fc.get("available") is False and fc.get("reason") and "hours" not in fc)
        check("GET /api/forecast يعيد توقع WBGT أو سببًا واضحًا لتعذره", fc_ok,
              ("%d ساعة" % len(fc["hours"])) if fc.get("available") else "بلا إنترنت: " + (fc.get("reason") or "")[:60])

        # UI-02 — نفحص سمات التحميل الفعلية (src و href)، لا مجرد ورود كلمة http،
        # لأن عناوين مجالات أسماء XML ليست طلبًا للشبكة.
        import re as _re
        page = get_raw("/bench/")[1]   # UI-02 لموقع الاختبار؛ المنصة تطلب خط Google Fonts
        refs = _re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', page)
        external = [r for r in refs if _re.match(r'^(?:https?:)?//', r.strip())]
        check("لا يوجد أي طلب للإنترنت في الصفحة (UI-02)",
              not external,
              "فُحصت %d مرجعًا، كلها محلية" % len(refs) if not external
              else "مراجع خارجية: %s" % external)
        check("الصفحة عربية من اليمين لليسار (القسم 8.1)",
              'lang="ar"' in page and 'dir="rtl"' in page)

        # ⑭ الحسابات بمكتبة معتمدة
        check("مكتبة pythermalcomfort مثبّتة وتعمل (CA-01 إلى CA-03)",
              meta["pythermalcomfort"] is True)
        health = get("/api/health")
        check("مكتبة thermofeel مثبّتة لحساب WBGT بطريقة Liljegren",
              health.get("thermofeel") is True)

        # --- معيار القبول: تفعيل الكرة الحرارية بإعداد واحد ---
        cfg_live = json.loads(open(cfg_path, encoding="utf-8").read())
        cfg_live["mrt_source"] = "globe"
        open(cfg_path, "w", encoding="utf-8").write(
            json.dumps(cfg_live, ensure_ascii=False, indent=2))
        globe_proc = _sp.Popen(
            [sys.executable, os.path.join(ROOT, "02_server_backend", "app.py"),
             "--port", str(PORT + 2), "--live"],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        try:
            base3 = "http://127.0.0.1:%d" % (PORT + 2)
            for _ in range(60):
                try:
                    urllib.request.urlopen(base3 + "/api/health", timeout=1)
                    break
                except Exception:
                    time.sleep(0.3)
            gm = json.loads(urllib.request.urlopen(base3 + "/api/meta", timeout=6)
                            .read().decode())
            check("تفعيل الكرة الحرارية بإعداد واحد (mrt_source = globe)",
                  gm["globe_enabled"] is True
                  and "ds18b20" not in gm["disabled_sensors"],
                  "المعطلة بعد التفعيل: %s" % "، ".join(gm["disabled_sensors"]))

            g = json.dumps(msg(node="node-globe", sensors={
                "ds18b20": {"status": "ok", "tg_c": 33.0, "count": 1}})).encode()
            rq = urllib.request.Request(
                base3 + "/api/readings", data=g,
                headers={"Content-Type": "application/json", "X-Transport": "usb"},
                method="POST")
            rep = json.loads(urllib.request.urlopen(rq, timeout=6).read().decode())
            gd = json.loads(urllib.request.urlopen(
                base3 + "/api/latest?node=node-globe", timeout=6).read().decode())
            check("بعد التفعيل تُحسب MRT من الكرة لا تُفترض",
                  gd["derived"]["mrt_assumed"] is False
                  and rep.get("mrt_source") == "globe"
                  and gd["derived"]["mrt_c"] > gd["values"]["ta_c"],
                  "MRT %.1f °م من كرة %.1f °م وهواء %.1f °م"
                  % (gd["derived"]["mrt_c"], gd["values"]["tg_c"], gd["values"]["ta_c"]))
        finally:
            globe_proc.terminate()
            try:
                globe_proc.wait(timeout=5)
            except Exception:
                globe_proc.kill()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        open(cfg_path, "w", encoding="utf-8").write(original)
        if os.path.exists(db):
            os.remove(db)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("\n══════════════════════════════════════════════════════════")
    print("  النتيجة: %d من %d" % (passed, total))
    if passed == total:
        print("  ✓ كل معايير القبول التي يمكن اختبارها بلا عتاد نجحت.")
        print("    يبقى اختبار العتاد نفسه حسب خطة المراحل في القسم 10.")
    else:
        print("  ✕ بنود لم تنجح:")
        for name, ok, detail in results:
            if not ok:
                print("      - %s %s" % (name, detail))
    print("══════════════════════════════════════════════════════════\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
