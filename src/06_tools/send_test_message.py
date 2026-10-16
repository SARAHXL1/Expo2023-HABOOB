#!/usr/bin/env python3
"""
إرسال رسالة اختبار إلى الخادم — القسم 6.8 خطوة 4 من دليل البناء.

يُستخدم للتأكد أن الخادم يستقبل ويحسب قبل توصيل ESP32 إطلاقًا.
الرسالة مطابقة تمامًا لما يبنيه برنامج العقدة (schema 2)، بما في ذلك
إرسال القيم غير المتوفرة على شكل null كما تنص القاعدة DS-02.

أمثلة:
    python3 06_tools/send_test_message.py
    python3 06_tools/send_test_message.py --server http://localhost:5000 --node node-test
    python3 06_tools/send_test_message.py --missing veml7700 mlx90614
    python3 06_tools/send_test_message.py --repeat 20 --interval 2
"""

import argparse
import json
import time
import urllib.error
import urllib.request

SENSORS = ["dht22", "ds18b20", "ads1115", "anemometer", "battery",
           "mlx90614", "veml7700", "tft"]


def build(node, missing, errored, seq):
    def st(sid, ok_payload):
        if sid in missing:
            return {"status": "not_found"}
        if sid in errored:
            body = {"status": "read_error"}
            body.update({k: None for k in ok_payload})
            return body
        return dict({"status": "ok"}, **ok_payload)

    i2c = [a for sid, a in (("veml7700", "0x10"), ("ads1115", "0x48"), ("mlx90614", "0x5A"))
           if sid not in missing]

    return {
        "schema": 3,
        "node_id": node,
        "fw": "test-0.3.0",
        "ts": int(time.time()),
        "uptime_s": 60 + seq * 5,
        "reset_reason": "POWERON",
        "wifi": {"connected": True, "rssi": -58, "ip": "192.168.1.77"},
        "heap_free": 182340,
        "i2c_found": i2c,
        "power_source": "usb",
        "send_interval_s": 5,
        "sensors": {
            "dht22":      st("dht22", {"ta_c": 24.8, "rh_pct": 41.0}),
            # الكرة والبطارية مؤجلتان في الإصدار 2
            "ds18b20":    {"status": "disabled", "tg_c": None, "count": 0},
            "ads1115":    st("ads1115", {}),
            "anemometer": st("anemometer", {"wind_v": 0.084, "wind_ms": 1.9,
                                            "height_m": 1.8, "samples": 50}),
            "battery":    {"status": "disabled", "bat_v": None},
            "mlx90614":   st("mlx90614", {"tsurf_c": 27.1, "tamb_c": 26.0}),
            "veml7700":   st("veml7700", {"lux": 680}),
            "tft":        {"status": "assumed"},
        },
    }


def send(server, msg):
    url = server.rstrip("/")
    if not url.endswith("/api/readings"):
        url += "/api/readings"
    req = urllib.request.Request(
        url, data=json.dumps(msg).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Transport": "test"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode())
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return 0, {"error": str(exc)}


def main():
    ap = argparse.ArgumentParser(description="إرسال رسالة اختبار للخادم")
    ap.add_argument("--server", default="http://localhost:5000")
    ap.add_argument("--node", default="node-test")
    ap.add_argument("--missing", nargs="*", default=[], choices=SENSORS,
                    help="قطع تُرسل بحالة not_found")
    ap.add_argument("--error", nargs="*", default=[], choices=SENSORS,
                    help="قطع تُرسل بحالة read_error")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    print("  الخادم: %s · العقدة: %s" % (args.server, args.node))
    for i in range(args.repeat):
        msg = build(args.node, set(args.missing), set(args.error), i)
        code, reply = send(args.server, msg)
        if code == 200:
            u = reply.get("utci_c")
            print("  ✓ %d/%d — 200 · UTCI %s · %s · MRT %s" % (
                i + 1, args.repeat,
                "—" if u is None else "%.1f °م" % u,
                reply.get("stress_category") or "—",
                "—" if reply.get("mrt_c") is None else "%.1f °م" % reply["mrt_c"]))
        elif code == 0:
            print("  ✕ تعذر الوصول للخادم: %s" % reply.get("error"))
            print("    تأكد أن الخادم يعمل:  python3 02_server_backend/app.py")
            print("    وإن كان يعمل على منفذ آخر (على ماك يُحجز 5000 لـ AirPlay)،")
            print("    انسخ المنفذ الذي طبعه الخادم واستخدمه هنا، مثل:")
            print("        python3 06_tools/send_test_message.py --server http://localhost:5001")
            return
        else:
            print("  ✕ %d — %s" % (code, reply.get("error")))
        if i + 1 < args.repeat:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
