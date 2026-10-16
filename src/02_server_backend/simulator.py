"""
وضع المحاكاة — SV-13.

يولّد رسائل JSON واقعية بنفس عقد البيانات (schema 2) لعقدة أو أكثر،
حتى يُختبر الموقع كاملًا قبل وصول القطع (المرحلة 0 من خطة الاختبار).

محاكاة الأعطال المتاحة لكل عقدة (تُضبط من اللوحة أو من config.json):
    missing   : قائمة معرّفات قطع تُرسل بحالة not_found   (حساس مفقود)
    error     : قائمة معرّفات قطع تُرسل بحالة read_error   (قراءة خاطئة)
    out_range : قائمة معرّفات قطع تُرسل بقيم خارج المدى
    offline   : true فيتوقف الإرسال كليًا                  (انقطاع)
    wind_zero : true فيبقى جهد الموتور صفرًا               (لفحص CK-02)
    wind_neg  : true فيصبح جهد الموتور سالبًا              (لفحص CK-03)
    lux_zero  : true فتبقى الإضاءة صفرًا                     (لفحص CK-04)
    tg_jump   : true فتقفز حرارة الكرة                     (لفحص CK-05)
    reboot    : true فيعود uptime للصفر كل رسالة            (لفحص CK-06)
"""

import math
import random
import threading
import time

from settings import cfg, node_cfg, globe_enabled

_thread = None
_stop = threading.Event()
_state = {"running": False, "faults": {}, "sent": 0, "started_at": None}
_sink = None   # دالة الاستقبال داخل الخادم نفسه (بلا شبكة)


class _NodeSim:
    """نموذج بسيط لعمود في الهواء الطلق في الرياض، بتغيّر سلس وضوضاء خفيفة."""

    def __init__(self, node_id, seed=0):
        self.node_id = node_id
        self.rnd = random.Random(hash(node_id) ^ seed)
        self.phase = self.rnd.random() * math.tau
        self.boot = time.time()
        self.uptime = 0.0
        self.bat_v = 4.05 + self.rnd.random() * 0.1
        self.seq = 0
        self.tg_bias = 0.0

    def _wave(self, period_s, amp, offset):
        t = time.time()
        return offset + amp * math.sin(self.phase + t * math.tau / period_s)

    def message(self, faults):
        self.seq += 1
        self.uptime = time.time() - self.boot
        if faults.get("reboot"):
            self.boot = time.time()
            self.uptime = self.rnd.random() * 3

        rnd = self.rnd
        nset = node_cfg(self.node_id)

        # قيم واقعية لقاعة التقييم: التغذية من USB والكرة مؤجلة
        ta = round(self._wave(600, 1.1, 24.5) + rnd.gauss(0, 0.08), 1)
        rh = round(max(10.0, min(70.0, self._wave(900, 4.0, 42.0) + rnd.gauss(0, 0.4))), 1)
        wind_true = max(0.0, self._wave(120, 0.9, 1.1) + rnd.gauss(0, 0.12))

        # الجهد الخام يُشتق عكسيًا من معاملات المعايرة، كما يفعل الموتور الحقيقي
        k = nset.get("wind_k", 20.0) or 20.0
        b = nset.get("wind_b", 0.5)
        wind_v = max(0.0, (wind_true - b) / k) if wind_true > b else 0.0
        wind_v = round(wind_v + rnd.gauss(0, 0.0015), 4)
        if faults.get("wind_zero"):
            wind_v = 0.0
        if faults.get("wind_neg"):
            wind_v = -abs(wind_v) - 0.01
        wind_ms = round(max(0.0, k * wind_v + b) if wind_v >= nset.get("wind_v_min", 0.02) else 0.0, 2)

        # الكرة أسخن من الهواء تحت الشمس، ويخفضها الهواء
        self.tg_bias += rnd.gauss(0, 0.05)
        self.tg_bias = max(-1.0, min(1.0, self.tg_bias))
        tg = round(ta + 7.5 - 1.1 * min(wind_ms, 4.0) + self.tg_bias, 1)
        if faults.get("tg_jump") and self.seq % 3 == 0:
            tg = round(tg + rnd.choice([-14.0, 14.0]), 1)

        tsurf = round(ta + 2.0 + rnd.gauss(0, 0.4), 1)
        tamb = round(ta + 1.2 + rnd.gauss(0, 0.2), 1)
        # قيم داخلية معقولة لقاعة عرض، لا شمس مباشرة
        lux = int(max(0, self._wave(1800, 180, 620) + rnd.gauss(0, 25)))
        if faults.get("lux_zero"):
            lux = 0

        self.bat_v = max(3.05, self.bat_v - 0.00012 - rnd.random() * 0.00008)
        bat_v = round(self.bat_v, 3)
        rssi = int(-55 + rnd.gauss(0, 4))

        globe_on = globe_enabled()
        missing = set(faults.get("missing") or [])
        errored = set(faults.get("error") or [])
        out_range = set(faults.get("out_range") or [])

        def body(sid, payload):
            if sid in missing:
                return {"status": "not_found"}
            if sid in errored:
                return dict({"status": "read_error"},
                            **{k: None for k in payload})
            return dict({"status": "ok"}, **payload)

        if "dht22" in out_range:
            ta, rh = 92.0, 140.0
        if "ds18b20" in out_range:
            tg = -127.0
        if "battery" in out_range:
            bat_v = 1.8
        if "anemometer" in out_range:
            wind_v, wind_ms = 1.9, 44.0
        if "mlx90614" in out_range:
            tsurf = 155.0
        if "veml7700" in out_range:
            lux = 260000

        i2c = []
        for sid, addr in (("veml7700", "0x10"), ("ads1115", "0x48"), ("mlx90614", "0x5A")):
            if sid not in missing:
                i2c.append(addr)

        return {
            "schema": 3,
            "node_id": self.node_id,
            "fw": "sim-0.3.0",
            "ts": int(time.time()),
            "uptime_s": int(self.uptime),
            "reset_reason": "POWERON",
            "wifi": {"connected": True, "rssi": rssi, "ip": "192.168.1.%d" % (77 + self.seq % 3)},
            "heap_free": 180000 + int(rnd.gauss(0, 2500)),
            "i2c_found": i2c,
            "power_source": "usb",
            "send_interval_s": cfg()["simulation"]["interval_s"],
            "simulated": True,
            "sensors": {
                "dht22": body("dht22", {"ta_c": ta, "rh_pct": rh}),
                "ds18b20": (body("ds18b20", {"tg_c": tg, "count": 1}) if globe_on
                            else {"status": "disabled", "tg_c": None, "count": 0}),
                "ads1115": body("ads1115", {}),
                "anemometer": body("anemometer", {
                    "wind_v": wind_v, "wind_ms": wind_ms,
                    "height_m": nset.get("wind_height_m", 1.8), "samples": 50}),
                "battery": {"status": "disabled", "bat_v": None},
                "mlx90614": body("mlx90614", {"tsurf_c": tsurf, "tamb_c": tamb}),
                "veml7700": body("veml7700", {"lux": lux}),
                "tft": {"status": "assumed"},
            },
        }


def _run():
    sims = {}
    while not _stop.is_set():
        c = cfg()["simulation"]
        interval = max(1.0, float(c.get("interval_s", 5)))
        for node_id in c.get("nodes", []):
            if node_id not in sims:
                sims[node_id] = _NodeSim(node_id)
            faults = _state["faults"].get(node_id, {}) or {}
            if faults.get("offline"):
                continue
            try:
                _sink(sims[node_id].message(faults), "sim")
                _state["sent"] += 1
            except Exception as exc:                      # لا توقف المحاكاة بسبب رسالة واحدة
                print("  [محاكاة] خطأ في رسالة %s: %s" % (node_id, exc))
        _stop.wait(interval)
    _state["running"] = False


def start(sink):
    """sink: دالة تستقبل (رسالة، طريقة الاتصال) وتمررها لمسار المعالجة نفسه."""
    global _thread, _sink
    if _state["running"]:
        return False
    _sink = sink
    _state["faults"] = dict(cfg()["simulation"].get("faults") or {})
    _state["running"] = True
    _state["started_at"] = time.time()
    _stop.clear()
    _thread = threading.Thread(target=_run, name="simulator", daemon=True)
    _thread.start()
    return True


def stop():
    if not _state["running"]:
        return False
    _stop.set()
    _state["running"] = False
    return True


def set_faults(node_id, faults):
    _state["faults"][node_id] = faults or {}
    return _state["faults"]


def status():
    return {
        "running": _state["running"],
        "sent": _state["sent"],
        "nodes": cfg()["simulation"].get("nodes", []),
        "interval_s": cfg()["simulation"].get("interval_s", 5),
        "faults": _state["faults"],
    }
