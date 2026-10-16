"""
التحقق من الرسائل، وتحديد حالات القطع، والفحوص المنطقية.
يغطي: SV-02، SV-03، SV-04، SV-05، SV-06، والجدولين 3.3 و3.4.
"""

import math
import time
from collections import deque, defaultdict

import calculations as ca
import heat_index
from settings import (
    cfg, node_cfg, mode, globe_enabled, effective_disabled, mrt_source,
    SENSOR_CATALOG, SENSOR_BY_ID, FIELD_OWNER,
    STATUS_OK, STATUS_NOT_FOUND, STATUS_READ_ERROR, STATUS_OUT_OF_RANGE,
    STATUS_STALE, STATUS_DISABLED, STATUS_ASSUMED, STATUS_NOT_CONNECTED, STATUS_AR,
)

NODE_STATUSES = {STATUS_OK, STATUS_NOT_FOUND, STATUS_READ_ERROR, STATUS_ASSUMED}


class ValidationError(Exception):
    """رسالة معطوبة تُرفض مع سبب عربي واضح (SV-02)."""


# ---------------------------------------------------------------------------
# SV-02 — التحقق من بنية الرسالة
# ---------------------------------------------------------------------------
def validate(msg):
    if not isinstance(msg, dict):
        raise ValidationError("الرسالة ليست كائن JSON.")

    node_id = msg.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValidationError("الحقل node_id مفقود أو ليس نصًا.")

    sensors = msg.get("sensors")
    if not isinstance(sensors, dict):
        raise ValidationError("الحقل sensors مفقود أو ليس كائنًا.")
    if not sensors:
        raise ValidationError("الحقل sensors فارغ.")

    for sid, body in sensors.items():
        if not isinstance(body, dict):
            raise ValidationError("القطعة «%s» ليست كائنًا." % sid)
        st = body.get("status")
        if st is not None and not isinstance(st, str):
            raise ValidationError("حالة القطعة «%s» ليست نصًا." % sid)
        for key, val in body.items():
            if key in ("status",):
                continue
            if val is None or isinstance(val, (str, bool, list, dict)):
                continue
            if not isinstance(val, (int, float)):
                raise ValidationError("القيمة «%s» في القطعة «%s» ليست رقمًا." % (key, sid))
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                raise ValidationError("القيمة «%s» في القطعة «%s» ليست رقمًا منطقيًا." % (key, sid))
    return node_id.strip()


# ---------------------------------------------------------------------------
# SV-03 — وقت الاستلام بدل ts غير المنطقي
# ---------------------------------------------------------------------------
TS_MIN = 1_577_836_800   # 2020-01-01، أي أقدم من هذا يعني أن ساعة العقدة لم تُضبط


def resolve_timestamp(msg, rx_ts):
    ts = msg.get("ts")
    ok = isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts >= TS_MIN \
        and ts <= rx_ts + 86400
    if ok:
        return float(ts), False
    return float(rx_ts), True


# ---------------------------------------------------------------------------
# استخراج القيم الخام من الرسالة
# ---------------------------------------------------------------------------
def _num(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        f = float(x)
        if not (math.isnan(f) or math.isinf(f)):
            return f
    return None


def extract_values(msg):
    """يجمع كل الحقول الرقمية المعروفة من sensors ومن جذر الرسالة."""
    values = {}
    sensors = msg.get("sensors", {})
    for sid, body in sensors.items():
        if not isinstance(body, dict):
            continue
        for field in SENSOR_BY_ID.get(sid, {}).get("fields", []):
            if field in body:
                values[field] = _num(body[field])
    # rssi يأتي داخل كائن wifi في جذر الرسالة
    wifi = msg.get("wifi")
    if isinstance(wifi, dict) and "rssi" in wifi:
        values.setdefault("rssi", _num(wifi.get("rssi")))
    return values


# ---------------------------------------------------------------------------
# SV-04 — فحص المدى المنطقي (الجدول 3.3)
# ---------------------------------------------------------------------------
def range_check(field, value):
    """ترجع None إن كانت القيمة ضمن المدى، أو رسالة عربية تصف الخروج."""
    r = cfg()["ranges"].get(field)
    if r is None or value is None:
        return None
    if value < r["min"] or value > r["max"]:
        return "%s = %g %s خارج المدى المسموح (%g إلى %g)." % (
            r["label"], round(value, 3), r["unit"], r["min"], r["max"])
    return None


# ---------------------------------------------------------------------------
# حالة العقدة في الذاكرة: لمتابعة stale والفحوص الزمنية
# ---------------------------------------------------------------------------
class NodeState:
    def __init__(self, node_id):
        self.node_id = node_id
        self.last_msg_rx = 0.0
        self.last_raw = None          # آخر رسالة خام كما وصلت (للوحة التشخيص)
        self.last_processed = None    # آخر رسالة بعد المعالجة
        self.transport = "—"
        self.sensor_last_ok = {}      # معرّف القطعة -> وقت آخر قراءة ok
        self.tg_history = deque(maxlen=200)      # (ts, tg) لفحص CK-05
        self.wind_zero_since = None              # لفحص CK-02
        self.lux_zero_since = None               # لفحص CK-04
        self.reset_times = deque(maxlen=50)      # لفحص CK-06
        self.last_uptime = None
        self.msg_count = 0
        self.simulated = False

    def is_online(self, now=None):
        now = now or time.time()
        return (now - self.last_msg_rx) <= cfg()["timing"]["node_offline_s"]


class StateStore:
    def __init__(self):
        self.nodes = {}

    def get(self, node_id):
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeState(node_id)
        return self.nodes[node_id]

    def known(self):
        return list(self.nodes.values())


STATE = StateStore()


# ---------------------------------------------------------------------------
# بناء حالات القطع
# ---------------------------------------------------------------------------
def build_sensor_states(msg, values, state, rx_ts):
    """
    يبني قاموسًا: معرّف القطعة -> {status, values, ...}
    العقدة تحدد ok / not_found / read_error / assumed،
    والخادم يضيف out_of_range (SV-04) و stale (SV-05) و disabled.
    """
    c = cfg()
    disabled = effective_disabled()
    sensors_in = msg.get("sensors", {}) or {}
    result = {}

    for spec in SENSOR_CATALOG:
        sid = spec["id"]
        body = sensors_in.get(sid)
        entry = {
            "id": sid,
            "ar": spec["ar"],
            "tech": spec["tech"],
            "port": spec["port"],
            "values": {},
            "extra": {},
            "status": STATUS_NOT_FOUND,
            "status_ar": "",
            "reasons": [],
            "last_update": None,
            "age_s": None,
        }

        # القطعة المعطلة عمدًا
        if sid in disabled:
            entry["status"] = STATUS_DISABLED
            entry["status_ar"] = STATUS_AR[STATUS_DISABLED]
            result[sid] = entry
            continue

        # قطعة لم ترد في الرسالة إطلاقًا
        if body is None:
            if sid == "esp32":
                # وصول الرسالة نفسه دليل على أن اللوحة تعمل
                entry["status"] = STATUS_OK
                state.sensor_last_ok[sid] = rx_ts
                entry["values"] = {k: v for k, v in (("rssi", values.get("rssi")),)
                                   if v is not None}
            else:
                entry["status"] = STATUS_NOT_FOUND
                entry["reasons"].append("القطعة لم ترد في رسالة العقدة.")
            entry["status_ar"] = STATUS_AR[entry["status"]]
            entry["last_update"] = state.sensor_last_ok.get(sid)
            result[sid] = entry
            continue

        reported = body.get("status")
        status = reported if reported in NODE_STATUSES else STATUS_READ_ERROR
        if reported not in NODE_STATUSES and reported is not None:
            entry["reasons"].append("العقدة أرسلت حالة غير معروفة: «%s»." % reported)

        # القيم والحقول الإضافية
        for field in spec["fields"]:
            if field in body:
                entry["values"][field] = _num(body[field])
        for key, val in body.items():
            if key != "status" and key not in spec["fields"]:
                entry["extra"][key] = val
        if sid == "esp32" and values.get("rssi") is not None:
            entry["values"].setdefault("rssi", values["rssi"])

        # SV-04 — المدى المنطقي يُطبّق على الحالة ok فقط
        if status == STATUS_OK:
            if spec["fields"] and all(entry["values"].get(f) is None for f in spec["fields"]):
                status = STATUS_READ_ERROR
                entry["reasons"].append("الحالة ok لكن كل القيم فارغة.")
            else:
                for field, val in entry["values"].items():
                    msg_range = range_check(field, val)
                    if msg_range:
                        status = STATUS_OUT_OF_RANGE
                        entry["reasons"].append(msg_range)

        if status == STATUS_OK:
            state.sensor_last_ok[sid] = rx_ts

        entry["last_update"] = state.sensor_last_ok.get(sid)
        entry["status"] = status
        entry["status_ar"] = STATUS_AR[status]
        result[sid] = entry

    return result


def apply_staleness(sensors, node_online, now):
    """
    SV-05 — تُطبّق عند كل قراءة للوحة، لا عند الاستلام فقط،
    حتى تتحول البطاقة إلى «متوقف» من تلقاء نفسها عندما تصمت العقدة.
    """
    stale_s = cfg()["timing"]["sensor_stale_s"]
    for sid, entry in sensors.items():
        last = entry.get("last_update")
        entry["age_s"] = round(now - last, 1) if last else None
        if entry["status"] in (STATUS_DISABLED, STATUS_ASSUMED):
            continue
        too_old = last is None or (now - last) > stale_s
        if too_old and (entry["status"] == STATUS_OK or not node_online):
            if entry["status"] == STATUS_OK:
                entry["status"] = STATUS_STALE
                entry["status_ar"] = STATUS_AR[STATUS_STALE]
                entry["reasons"].append("لم تصل قراءة جديدة منذ أكثر من %d ثانية." % stale_s)
    return sensors


# ---------------------------------------------------------------------------
# SV-06 — الفحوص المنطقية (الجدول 3.4) والتنبيهات
# ---------------------------------------------------------------------------
def _alert(code, severity, text, hint=None):
    return {"code": code, "severity": severity, "text": text, "hint": hint}


def run_checks(state, values, sensors, derived, rx_ts, msg):
    c = cfg()
    chk = c["checks"]
    warn = c["warnings"]
    alerts = []

    ta = values.get("ta_c")
    tg = values.get("tg_c")
    wind_v = values.get("wind_v")
    lux = values.get("lux")
    bat_v = values.get("bat_v")
    rssi = values.get("rssi")

    # CK-01 — فرق الهواء والكرة في الظل وقت المعايرة (عند تفعيل الكرة فقط)
    if globe_enabled() and chk.get("calibration_mode") and ta is not None and tg is not None:
        in_shade = lux is None or lux <= chk["ck01_shade_lux_max"]
        if in_shade and abs(tg - ta) > chk["ck01_ta_tg_diff_c"]:
            alerts.append(_alert(
                "CK-01", "warning",
                "تحقق من معايرة الكرة: الفرق بين حرارة الهواء والكرة %.1f °م في الظل."
                % (tg - ta),
                "سجّل الفرق كمعامل تصحيح في نموذج المعايرة أسفل اللوحة."))

    # CK-02 — جهد الموتور ثابت عند الصفر
    v_min = node_cfg(state.node_id).get("wind_v_min", 0.02)
    if wind_v is not None:
        if abs(wind_v) < v_min:
            if state.wind_zero_since is None:
                state.wind_zero_since = rx_ts
            elif rx_ts - state.wind_zero_since >= chk["ck02_wind_zero_seconds"]:
                alerts.append(_alert(
                    "CK-02", "info",
                    "جهد الموتور ثابت عند الصفر منذ %d ثانية."
                    % int(rx_ts - state.wind_zero_since),
                    "إن كانت المروحة تعمل، تحقق من توصيل الموتور أو اتجاهه."))
        else:
            state.wind_zero_since = None

        # CK-03 — جهد سالب
        if wind_v < 0:
            alerts.append(_alert(
                "CK-03", "warning",
                "جهد الموتور سالب (%.3f V)." % wind_v,
                "اعكس سلكي الموتور."))

    # CK-04 — الإضاءة ثابتة عند الصفر في مكان مضاء
    if lux is not None:
        if lux <= 0:
            if state.lux_zero_since is None:
                state.lux_zero_since = rx_ts
            elif rx_ts - state.lux_zero_since >= chk.get("ck04_lux_stuck_zero_seconds", 20):
                alerts.append(_alert(
                    "CK-04", "warning",
                    "الإضاءة ثابتة عند الصفر منذ %d ثانية."
                    % int(rx_ts - state.lux_zero_since),
                    "إن كان المكان مضاءً، تحقق من VEML7700: VIN وSDA وSCL ولحام الأطراف."))
        else:
            state.lux_zero_since = None

    # CK-05 — قفزة في قراءة الكرة (عند تفعيل الكرة فقط)
    if globe_enabled() and tg is not None:
        state.tg_history.append((rx_ts, tg))
        window = chk["ck05_window_s"]
        recent = [v for (t, v) in state.tg_history if rx_ts - t <= window]
        if len(recent) >= 2 and (max(recent) - min(recent)) > chk["ck05_tg_jump_c"]:
            alerts.append(_alert(
                "CK-05", "warning",
                "قراءة الكرة غير مستقرة: تغيّرت %.1f °م خلال %d ثوانٍ."
                % (max(recent) - min(recent), window),
                "تأكد من تثبيت المجس في مركز الكرة وإغلاق الثقب بالشمع."))

    # CK-06 — إعادة تشغيل متكررة
    uptime = _num(msg.get("uptime_s"))
    if uptime is not None:
        if state.last_uptime is not None and uptime < state.last_uptime:
            state.reset_times.append(rx_ts)
        state.last_uptime = uptime
        window = chk["ck06_window_s"]
        recent_resets = [t for t in state.reset_times if rx_ts - t <= window]
        if len(recent_resets) >= chk["ck06_resets_in_window"]:
            alerts.append(_alert(
                "CK-06", "critical",
                "العقدة أُعيد تشغيلها %d مرات خلال %d دقائق."
                % (len(recent_resets), window // 60),
                "مشكلة طاقة محتملة؛ غيّر كابل USB أو المنفذ، أو ركّب مكثفًا على خط التغذية."))

    # تنبيهات إضافية: البطارية (إن عادت) وقوة الإشارة
    if bat_v is not None and "battery" not in effective_disabled():
        if bat_v < warn["battery_critical_v"]:
            alerts.append(_alert("BAT-CRIT", "critical",
                                 "جهد البطارية حرج (%.2f V)." % bat_v,
                                 "صل المحول فورًا؛ حماية TP4056 تقطع قرب 3.0V."))
        elif bat_v < warn["battery_low_v"]:
            alerts.append(_alert("BAT-LOW", "warning",
                                 "جهد البطارية منخفض (%.2f V)." % bat_v,
                                 "انقل العقدة لوضع التوفير أو صل الشاحن."))
    if rssi is not None and rssi < warn["rssi_weak_dbm"]:
        alerts.append(_alert("WIFI-WEAK", "warning",
                             "إشارة الواي فاي ضعيفة (%d dBm)." % int(rssi),
                             "قرّب الهوتسبوت من العمود أو استخدم جسر USB."))

    # تنبيهات مشتقة من الحساب
    if derived.get("wind_clamped"):
        alerts.append(_alert("CA-04", "info", "رياح مقيّدة لحساب UTCI.",
                             derived["notes"][-1] if derived.get("notes") else None))
    if derived.get("utci_unavailable_reason"):
        alerts.append(_alert("CA-07", "warning", derived["utci_unavailable_reason"], None))

    # تنبيه علم WBGT: الأصفر فأعلى يحتاج قرارًا من المشغل
    flag = derived.get("flag")
    if flag in ("yellow", "red", "black"):
        sev = "critical" if flag in ("red", "black") else "warning"
        alerts.append(_alert(
            "WBGT-" + flag.upper(), sev,
            "WBGT = %.1f °م (العلم %s)." % (derived["wbgt_c"], derived.get("flag_ar")),
            "التوصية في صفحة المنطقة على المنصة."))
    if derived.get("wbgt_reason"):
        alerts.append(_alert("WBGT-NOTE", "info", derived["wbgt_reason"], None))

    # تنبيهات حالات القطع
    for sid, entry in sensors.items():
        if entry["status"] in (STATUS_NOT_FOUND, STATUS_READ_ERROR, STATUS_OUT_OF_RANGE):
            sev = "critical" if entry["status"] == STATUS_NOT_FOUND else "warning"
            alerts.append(_alert(
                "SENSOR-" + sid.upper(), sev,
                "%s (%s): %s." % (entry["ar"], entry["tech"], entry["status_ar"]),
                help_text(sid, entry["status"])))

    from settings import SEVERITY_ORDER
    alerts.sort(key=lambda a: SEVERITY_ORDER.get(a["severity"], 9))
    return alerts


def help_text(sensor_id, status):
    """الجدول 8.4 — رسالة المساعدة المقترحة لكل قطعة وحالة."""
    spec = SENSOR_BY_ID.get(sensor_id)
    if not spec:
        return None
    helps = spec.get("help", {})
    return helps.get(status) or helps.get("*")


# ---------------------------------------------------------------------------
# المعالجة الكاملة لرسالة واحدة
# ---------------------------------------------------------------------------
def process(msg, rx_ts=None, transport="wifi"):
    """
    يرجع قاموس الرسالة بعد المعالجة. يرمي ValidationError للرسالة المعطوبة.
    """
    rx_ts = rx_ts or time.time()
    node_id = validate(msg)
    state = STATE.get(node_id)
    nset = node_cfg(node_id)

    ts, ts_replaced = resolve_timestamp(msg, rx_ts)
    values = extract_values(msg)

    # SV-15 — إعادة حساب سرعة الرياح من الجهد بمعاملات الخادم
    wind_recomputed = False
    if nset.get("recompute_wind_on_server") and values.get("wind_v") is not None:
        new_ms = ca.wind_from_voltage(values["wind_v"], nset)
        if new_ms is not None:
            values["wind_ms_node"] = values.get("wind_ms")
            values["wind_ms"] = new_ms
            wind_recomputed = True

    # يُسجَّل وقت الاستلام قبل بناء الحالات، لأن حالة بطاقة ESP32 تعتمد على كون
    # العقدة متصلة، والرسالة التي بين أيدينا هي الدليل على أنها متصلة الآن.
    state.last_msg_rx = rx_ts
    sensors = build_sensor_states(msg, values, state, rx_ts)
    derived = ca.derive(values, nset)
    if wind_recomputed:
        derived["notes"].append(
            "أُعيد حساب سرعة الرياح في الخادم بمعاملات المعايرة K=%.3f و B=%.3f."
            % (nset.get("wind_k", 0.0), nset.get("wind_b", 0.0)))
        # القيمة المعروضة على بطاقة مقياس الرياح تتبع حساب الخادم
        if "anemometer" in sensors and sensors["anemometer"]["values"].get("wind_ms") is not None:
            sensors["anemometer"]["values"]["wind_ms"] = values["wind_ms"]

    # WBGT والعلم والتفسير والتوصية من وحدة الذكاء الاصطناعي (مجلد AI)
    derived.update(heat_index.compute(sensors, ts, nset))

    alerts = run_checks(state, values, sensors, derived, rx_ts, msg)

    if ts_replaced:
        derived["notes"].append("ساعة العقدة غير مضبوطة، فاستُخدم وقت الاستلام.")

    wifi = msg.get("wifi") if isinstance(msg.get("wifi"), dict) else {}
    processed = {
        "power_source": msg.get("power_source") or "usb",
        "node_id": node_id,
        "node_name": nset.get("name", node_id),
        "schema": msg.get("schema"),
        "fw": msg.get("fw"),
        "ts": ts,
        "ts_replaced": ts_replaced,
        "rx_ts": rx_ts,
        "transport": transport,
        "uptime_s": _num(msg.get("uptime_s")),
        "reset_reason": msg.get("reset_reason"),
        "heap_free": _num(msg.get("heap_free")),
        "i2c_found": msg.get("i2c_found") or [],
        "send_interval_s": _num(msg.get("send_interval_s")),
        "wifi": {
            "connected": bool(wifi.get("connected")),
            "rssi": _num(wifi.get("rssi")),
            "ip": wifi.get("ip"),
        },
        "values": values,
        "sensors": sensors,
        "derived": derived,
        "alerts": alerts,
        "node_settings": nset,
    }

    state.last_raw = msg
    state.last_processed = processed
    state.transport = transport
    state.simulated = (transport == "sim")
    state.msg_count += 1
    return processed


def latest_view(node_id, now=None):
    """
    لقطة محدّثة زمنيًا لآخر رسالة: تُعاد فيها حسابات stale وعمر القراءات،
    حتى لا تتجمد البطاقات عندما تصمت العقدة (SV-05، UI-06).
    """
    now = now or time.time()
    state = STATE.nodes.get(node_id)
    if state is None or state.last_processed is None:
        return None

    import copy
    view = copy.deepcopy(state.last_processed)
    online = state.is_online(now)
    view["online"] = online
    view["age_s"] = round(now - state.last_msg_rx, 1)
    view["server_time"] = now
    view["msg_count"] = state.msg_count
    # الرسالة الخام كما وصلت، للوحة التشخيص (8.1 / 6)
    view["raw"] = state.last_raw
    apply_staleness(view["sensors"], online, now)

    if not online:
        view["alerts"] = [_alert(
            "NODE-OFFLINE", "critical",
            "العقدة «%s» غير متصلة منذ %.0f ثانية." % (view["node_name"], view["age_s"]),
            help_text("esp32", STATUS_NOT_FOUND))] + view["alerts"]

    # رسائل المساعدة تُحسب على الحالة النهائية بعد stale
    for sid, entry in view["sensors"].items():
        entry["help"] = help_text(sid, entry["status"])
    return view


def visible_nodes(current_mode=None):
    """
    العقد التي تخص الوضع الحالي.

    القاعدة غير متماثلة عن قصد:
    • وضع العتاد الحقيقي (live) يخفي عقد المحاكاة تمامًا، حتى لا تُقرأ بيانات
      وهمية على أنها قراءات عتاد — وهذا هو جوهر الوضع.
    • وضع المحاكاة (sim) يعرض الجميع، لأن إخفاء عقدة حقيقية موصولة أثناء
      المحاكاة يربك أكثر مما يفيد. وعقد المحاكاة تُقدَّم في الترتيب وتُميَّز
      باسمها، فلا يختلط الأمر.
    """
    m = current_mode or mode()
    known = STATE.known()
    if m == "live":
        return [st for st in known if not st.simulated]
    return sorted(known, key=lambda st: (not st.simulated, st.node_id))


def skeleton_view(now=None):
    """
    لقطة «لا توجد عقدة بعد» لوضع العتاد الحقيقي.

    تُبنى بطاقة لكل قطعة في الكتالوج بحالة «غير متصل»، مع رسالة المساعدة
    الخاصة بها، حتى يرى المستخدم القائمة الكاملة لما يُفترض أن يكون موصولًا
    بدل أن يرى صفحة فارغة. القطع المعطلة عمدًا تبقى «معطّل».
    """
    now = now or time.time()
    disabled = effective_disabled()
    sensors = {}
    for spec in SENSOR_CATALOG:
        sid = spec["id"]
        status = STATUS_DISABLED if sid in disabled else STATUS_NOT_CONNECTED
        sensors[sid] = {
            "id": sid, "ar": spec["ar"], "tech": spec["tech"], "port": spec["port"],
            "values": {}, "extra": {}, "status": status,
            "status_ar": STATUS_AR[status],
            "reasons": [], "last_update": None, "age_s": None,
            "help": help_text(sid, STATUS_NOT_FOUND) if sid not in disabled else None,
        }
    return {
        "available": True,
        "skeleton": True,
        "node_id": None,
        "node_name": "لا توجد عقدة",
        "online": False,
        "transport": "—",
        "age_s": None,
        "server_time": now,
        "msg_count": 0,
        "fw": None, "schema": None, "uptime_s": None, "reset_reason": None,
        "heap_free": None, "i2c_found": [], "send_interval_s": None,
        "ts": None, "ts_replaced": False,
        "wifi": {"connected": False, "rssi": None, "ip": None},
        "power_source": "usb",
        "values": {},
        "sensors": sensors,
        "derived": {
            "mrt_source": mrt_source(), "mrt_assumed": not globe_enabled(),
            "mrt_c": None, "v10_ms": None, "v10_used_ms": None, "wind_clamped": False,
            "utci_c": None, "stress_key": None, "stress_category": None,
            "tg_corrected_c": None, "battery_pct": None,
            "utci_unavailable_reason": "لم تصل أي رسالة من العقدة بعد.",
            "wbgt_c": None, "flag": None, "flag_ar": None, "wbgt_method": None,
            "wbgt_reason": "لم تصل أي رسالة من العقدة بعد.", "explain": None, "advice": None,
            "notes": [],
        },
        "alerts": [_alert(
            "NO-NODE", "critical",
            "لم تصل أي رسالة من عقدة حقيقية بعد.",
            "شغّل العقدة وتأكد من عنوان الخادم، أو وصّلها بسلك USB وشغّل الجسر: "
            "python3 03_usb_bridge/serial_bridge.py")],
        "node_settings": {},
        "raw": None,
    }


def nodes_view(now=None, current_mode=None):
    """GET /api/nodes — قائمة العقد وحالة كل واحدة وآخر ظهور."""
    now = now or time.time()
    out = []
    for state in visible_nodes(current_mode):
        p = state.last_processed or {}
        out.append({
            "simulated": state.simulated,
            "node_id": state.node_id,
            "node_name": node_cfg(state.node_id).get("name", state.node_id),
            "online": state.is_online(now),
            "last_seen_s": round(now - state.last_msg_rx, 1) if state.last_msg_rx else None,
            "transport": state.transport,
            "fw": p.get("fw"),
            "msg_count": state.msg_count,
            "utci_c": (p.get("derived") or {}).get("utci_c"),
            "wbgt_c": (p.get("derived") or {}).get("wbgt_c"),
            "flag": (p.get("derived") or {}).get("flag"),
        })
    if (current_mode or mode()) == "sim":
        out.sort(key=lambda n: (not n["simulated"], n["node_id"]))
    else:
        out.sort(key=lambda n: n["node_id"])
    return out
