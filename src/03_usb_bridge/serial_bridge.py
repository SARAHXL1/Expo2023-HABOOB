#!/usr/bin/env python3
"""
جسر USB — القسم 9.2 من المتطلبات (BR-01 إلى BR-05).

يقرأ المنفذ التسلسلي بسرعة 115200، ويأخذ فقط الأسطر التي تبدأ بـ `DATA:`
(القاعدة DS-05)، ويرسل ما بعدها إلى الخادم على /api/readings مع ترويسة
تبيّن أن طريقة الاتصال USB.

التشغيل:
    python3 03_usb_bridge/serial_bridge.py                       # يعرض المنافذ ثم يختار تلقائيًا
    python3 03_usb_bridge/serial_bridge.py --list                # عرض المنافذ فقط (BR-05)
    python3 03_usb_bridge/serial_bridge.py --port /dev/cu.usbserial-0001
    python3 03_usb_bridge/serial_bridge.py --port COM3 --baud 115200 --server http://localhost:5000

قبل التشغيل: أغلق Serial Monitor في Arduino IDE، فالمنفذ لا يُفتح من برنامجين معًا.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PREFIX = "DATA:"

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("✕ مكتبة pyserial غير مثبّتة. نفّذ:  pip install pyserial")
    sys.exit(1)


def show_ports():
    """BR-05 — عرض قائمة المنافذ المتاحة."""
    ports = list(list_ports.comports())
    if not ports:
        print("  لا توجد منافذ تسلسلية. تأكد من توصيل الكابل (كابل بيانات، لا شحن فقط)،")
        print("  ومن تثبيت تعريف شريحة USB: CP2102 أو CH340.")
        return []
    print("  المنافذ المتاحة:")
    for p in ports:
        print("    %-26s %s" % (p.device, p.description))
    return ports


def guess_port():
    """يختار المنفذ الأرجح أن يكون لوحة ESP32."""
    keys = ("cp210", "ch340", "ch910", "usbserial", "slab", "wchusb", "usbmodem", "silicon")
    for p in list_ports.comports():
        hay = ("%s %s %s" % (p.device, p.description, p.manufacturer or "")).lower()
        if any(k in hay for k in keys):
            return p.device
    ports = list(list_ports.comports())
    return ports[0].device if len(ports) == 1 else None


def post(server, payload, timeout=5):
    req = urllib.request.Request(
        server,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Transport": "usb"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, res.read().decode("utf-8", "replace")


def run(port, baud, server, quiet):
    stats = {"sent": 0, "ok": 0, "bad_json": 0, "rejected": 0, "other_lines": 0}
    ser = None
    last_report = time.time()

    while True:
        # BR-01 — إعادة فتح المنفذ تلقائيًا إن انفصل الكابل
        if ser is None:
            try:
                ser = serial.Serial(port, baud, timeout=1)
                time.sleep(0.4)
                ser.reset_input_buffer()
                print("✓ المنفذ %s مفتوح بسرعة %d." % (port, baud))
            except Exception as exc:
                print("… تعذر فتح %s (%s). إعادة المحاولة بعد 3 ثوانٍ." % (port, exc))
                time.sleep(3)
                continue

        try:
            raw = ser.readline()
        except Exception as exc:
            print("… انقطع المنفذ (%s). إعادة الفتح…" % exc)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(2)
            continue

        if not raw:
            if time.time() - last_report > 30:
                print("  …لا تصل أسطر من العقدة. تأكد أن البرنامج يطبع أسطر %s" % PREFIX)
                last_report = time.time()
            continue

        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue

        # BR-02 — الأسطر الأخرى تُطبع للتشخيص ولا تُرسل
        if not line.startswith(PREFIX):
            stats["other_lines"] += 1
            if not quiet:
                print("  [عقدة] %s" % line)
            continue

        body = line[len(PREFIX):].strip()

        # BR-03 — السطر المعطوب يُتجاهل ويستمر العمل
        try:
            json.loads(body)
        except Exception as exc:
            stats["bad_json"] += 1
            print("  ✕ سطر DATA معطوب، تم تجاهله (%s)" % exc)
            continue

        stats["sent"] += 1
        try:
            code, reply = post(server, body)
            if code == 200:
                stats["ok"] += 1
                try:
                    r = json.loads(reply)
                    extra = ""
                    if r.get("utci_c") is not None:
                        extra = " · UTCI %.1f °م · %s" % (r["utci_c"], r.get("stress_category") or "")
                    print("  → أُرسلت %d (200)%s" % (stats["ok"], extra))
                except Exception:
                    print("  → أُرسلت %d (200)" % stats["ok"])
            else:
                stats["rejected"] += 1
                print("  ✕ الخادم رفض الرسالة (%d): %s" % (code, reply[:160]))
        except urllib.error.HTTPError as exc:
            stats["rejected"] += 1
            detail = ""
            try:
                detail = json.loads(exc.read().decode()).get("error", "")
            except Exception:
                pass
            print("  ✕ الخادم رفض الرسالة (%d): %s" % (exc.code, detail))
        except Exception as exc:
            print("  ✕ تعذر الوصول للخادم (%s). تأكد أنه يعمل على %s" % (exc, server))
            time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description="جسر USB بين ESP32 وخادم موقع الاختبار")
    ap.add_argument("--port", help="اسم المنفذ، مثل COM3 أو /dev/cu.usbserial-0001")
    ap.add_argument("--baud", type=int, default=115200, help="سرعة المنفذ (الافتراضي 115200)")
    ap.add_argument("--server", default="http://localhost:5000/api/readings",
                    help="عنوان نقطة الاستقبال في الخادم")
    ap.add_argument("--list", action="store_true", help="عرض المنافذ المتاحة والخروج")
    ap.add_argument("--quiet", action="store_true", help="إخفاء أسطر التشخيص القادمة من العقدة")
    args = ap.parse_args()

    print("\n══════════════════════════════════════════════════════")
    print("  جسر USB — موقع اختبار الحساسات")
    print("══════════════════════════════════════════════════════")

    if args.list:
        show_ports()
        return

    port = args.port
    if not port:
        show_ports()
        port = guess_port()
        if not port:
            print("\n✕ لم أتمكن من اختيار منفذ تلقائيًا. أعد التشغيل مع --port واسم المنفذ.")
            return
        print("\n  المنفذ المختار تلقائيًا: %s" % port)

    print("  الخادم : %s" % args.server)
    print("  البادئة المقبولة: %s" % PREFIX)
    print("  للإيقاف: Ctrl+C\n")

    try:
        run(port, args.baud, args.server, args.quiet)
    except KeyboardInterrupt:
        print("\n  إيقاف الجسر.")


if __name__ == "__main__":
    main()
