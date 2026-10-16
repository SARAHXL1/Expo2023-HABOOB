"""
الحسابات في الخادم — القسم 7 من المتطلبات (CA-01 إلى CA-07).

تعتمد على pythermalcomfort (الإصدار 3 أو أحدث). أسماء الدوال وما ترجعه
مُتحقق منها على الإصدار المثبّت:
    mean_radiant_tmp(tg, tdb, v, d, emissivity, standard) -> رقم
    scale_wind_speed_log(v_z1, z2, z1)                    -> كائن فيه .v_z2
    utci(tdb, tr, v, rh)                                  -> كائن فيه .utci و .stress_category

إن لم تكن المكتبة مثبّتة، يبقى الموقع يعمل: تُحسب MRT وسرعة الرياح عند 10 م
بمعادلتيهما القياسيتين (ISO 7726 وملف اللوغاريتم)، ولا تُحسب UTCI، وتظهر
رسالة واضحة في اللوحة بدل رقم مُختلق.
"""

import math

from settings import cfg, globe_enabled, mrt_source

# ---------------------------------------------------------------------------
# استيراد المكتبة مرة واحدة
# ---------------------------------------------------------------------------
LIB_OK = True
LIB_ERROR = ""
try:
    from pythermalcomfort.models import utci as _ptc_utci
    from pythermalcomfort.environment import (
        mean_radiant_tmp as _ptc_mrt,
        scale_wind_speed_log as _ptc_wind,
    )
except Exception as exc:  # pragma: no cover - مسار الاحتياط
    LIB_OK = False
    LIB_ERROR = str(exc)
    _ptc_utci = _ptc_mrt = _ptc_wind = None


# فئات الإجهاد — الجدول 8.3. الترجمة والحدود معًا، ليكون اللون والكلمة من مصدر واحد (UI-03).
STRESS_BANDS = [
    (46.0,   float("inf"), "extreme_heat",     "إجهاد حراري شديد جدًا"),
    (38.0,   46.0,         "very_strong_heat", "إجهاد حراري قوي جدًا"),
    (32.0,   38.0,         "strong_heat",      "إجهاد حراري قوي"),
    (26.0,   32.0,         "moderate_heat",    "إجهاد حراري متوسط"),
    (9.0,    26.0,         "no_stress",        "لا يوجد إجهاد حراري"),
    (0.0,    9.0,          "slight_cold",      "إجهاد بارد خفيف"),
    (-13.0,  0.0,          "moderate_cold",    "إجهاد بارد متوسط"),
    (float("-inf"), -13.0, "strong_cold",      "إجهاد بارد قوي أو أشد"),
]


def stress_band(utci_c):
    """يرجع (المفتاح، الاسم بالعربي) لفئة الإجهاد حسب الجدول 8.3."""
    if utci_c is None or not _is_num(utci_c):
        return None, None
    for low, high, key, ar in STRESS_BANDS:
        if low <= utci_c < high:
            return key, ar
    return None, None


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(x) \
        and not math.isinf(x)


def _f(x):
    """تحويل آمن إلى float عادي (قد ترجع المكتبة numpy.float64)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if not (math.isnan(v) or math.isinf(v)) else None


# ---------------------------------------------------------------------------
# CA-01 — سرعة الرياح عند 10 م
# ---------------------------------------------------------------------------
def wind_at_10m(v_local, height_m):
    if not _is_num(v_local) or not _is_num(height_m) or height_m <= 0:
        return None
    if v_local <= 0:
        return 0.0
    if LIB_OK:
        try:
            return _f(_ptc_wind(v_z1=v_local, z2=10.0, z1=height_m).v_z2)
        except Exception:
            pass
    # احتياط: ملف الرياح اللوغاريتمي بخشونة سطح z0 = 0.01 م (نفس افتراض المكتبة)
    z0 = 0.01
    return v_local * math.log(10.0 / z0) / math.log(height_m / z0)


# ---------------------------------------------------------------------------
# CA-02 — متوسط الحرارة الإشعاعية
#
# في الإصدار 2 الكرة الحرارية مؤجلة، لأن التقييم داخل القاعة لا في الشمس.
# فتُفترض MRT مساوية لحرارة الهواء، وتُعلَّم بوضوح على أنها «مفترضة» في كل
# مكان تظهر فيه. معادلة الكرة تبقى كما هي وتعمل فور تحويل mrt_source إلى globe.
# ---------------------------------------------------------------------------
def mean_radiant(tg_c, ta_c, v_local, diameter_m, emissivity):
    if not all(_is_num(x) for x in (tg_c, ta_c, v_local)):
        return None
    v = max(v_local, 0.0)
    if LIB_OK:
        try:
            return _f(_ptc_mrt(tg=tg_c, tdb=ta_c, v=v, d=diameter_m,
                               emissivity=emissivity, standard="ISO"))
        except Exception:
            pass
    # احتياط: معادلة ISO 7726 للحمل القسري
    try:
        term = (1.1e8 * (v ** 0.6) * (tg_c - ta_c)) / (emissivity * (diameter_m ** 0.4))
        val = ((tg_c + 273.15) ** 4 + term) ** 0.25 - 273.15
        return _f(val)
    except (ValueError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------------------
# CA-03 + CA-04 — UTCI وفئة الإجهاد، مع حماية المدى
# ---------------------------------------------------------------------------
def utci_value(ta_c, mrt_c, v10_ms, rh_pct):
    """يرجع (قيمة UTCI أو None، سبب التعذّر بالعربي أو None)."""
    if not LIB_OK:
        return None, ("مكتبة pythermalcomfort غير مثبّتة، فلا يُحسب UTCI. "
                      "نفّذ: pip install pythermalcomfort")
    try:
        res = _ptc_utci(tdb=ta_c, tr=mrt_c, v=v10_ms, rh=rh_pct, limit_inputs=True)
        val = _f(res.utci)
        if val is None:
            return None, "المكتبة أرجعت NaN: المدخلات خارج حدود صلاحية معادلة UTCI."
        return val, None
    except Exception as exc:
        return None, "تعذر حساب UTCI: %s" % exc


# ---------------------------------------------------------------------------
# CA-05 — نسبة شحن البطارية (تقريبية)
# ---------------------------------------------------------------------------
_BAT_CURVE = [(3.30, 5.0), (3.70, 50.0), (4.20, 100.0)]


def battery_percent(bat_v):
    """تقريب خطي بين نقاط الجدول: 4.2V=100% و3.7V≈50% و3.3V≈5%."""
    if not _is_num(bat_v):
        return None
    if bat_v <= _BAT_CURVE[0][0]:
        return 0.0
    if bat_v >= _BAT_CURVE[-1][0]:
        return 100.0
    for (v1, p1), (v2, p2) in zip(_BAT_CURVE, _BAT_CURVE[1:]):
        if v1 <= bat_v <= v2:
            return round(p1 + (bat_v - v1) * (p2 - p1) / (v2 - v1), 1)
    return None


# ---------------------------------------------------------------------------
# الدالة الرئيسية: تأخذ القيم الخام وترجع القيم المشتقة
# ---------------------------------------------------------------------------
def derive(values, node_settings):
    """
    values        : قاموس بالقيم الخام المستخرجة من الرسالة (ta_c, rh_pct, tg_c, ...)
    node_settings : إعدادات العقدة (ارتفاع الرياح، معاملات المعايرة، تصحيح الكرة)

    ترجع قاموس القيم المشتقة، وفيه دائمًا مفتاح notes بقائمة ملاحظات عربية.
    القيم الخام لا تُعدّل (NF-08): نسخة التصحيح تُحفظ في حقول جديدة.
    """
    c = cfg()
    lim = c["utci_limits"]
    globe = c["globe"]

    use_globe = globe_enabled()

    out = {
        "mrt_source": mrt_source(),
        "mrt_assumed": not use_globe,
        "mrt_c": None,
        "v10_ms": None,
        "v10_used_ms": None,
        "wind_clamped": False,
        "utci_c": None,
        "stress_key": None,
        "stress_category": None,
        "tg_corrected_c": None,
        "battery_pct": None,
        "utci_unavailable_reason": None,
        "notes": [],
    }

    ta = values.get("ta_c")
    rh = values.get("rh_pct")
    tg = values.get("tg_c")
    wind_ms = values.get("wind_ms")
    height = node_settings.get("wind_height_m") or 1.8

    # CA-05 — نسبة البطارية: مؤجلة ما دامت التغذية من USB، وتُحسب تلقائيًا
    # إن وصلت قراءة bat_v (أي عند إعادة تركيب دائرة البطارية)
    out["battery_pct"] = battery_percent(values.get("bat_v"))

    # CA-06 — تصحيح الكرة من المعايرة (عند تفعيل الكرة فقط)
    offset = (node_settings.get("globe_offset_c") or 0.0) if use_globe else 0.0
    if _is_num(tg):
        out["tg_corrected_c"] = round(tg - offset, 2)
        if offset:
            out["notes"].append("طُبّق تصحيح الكرة %+.2f °م من المعايرة." % (-offset))
    tg_used = out["tg_corrected_c"] if out["tg_corrected_c"] is not None else tg

    # CA-07 — عند غياب قيمة أساسية لا يُحسب UTCI
    required = [("ta_c", "حرارة الهواء"), ("rh_pct", "الرطوبة"),
                ("wind_ms", "سرعة الرياح")]
    if use_globe:
        required.insert(2, ("tg_c", "حرارة الكرة"))
    missing = [label for key, label in required if not _is_num(values.get(key))]

    # CA-01 — الرياح عند 10 م (تُحسب ما دامت الرياح متوفرة، حتى لو نقص غيرها)
    if _is_num(wind_ms):
        v10 = wind_at_10m(wind_ms, height)
        out["v10_ms"] = round(v10, 3) if v10 is not None else None
        if v10 is not None:
            used = min(max(v10, lim["wind_min_ms"]), lim["wind_max_ms"])
            out["v10_used_ms"] = round(used, 3)
            if abs(used - v10) > 1e-9:
                out["wind_clamped"] = True
                out["notes"].append(
                    "رياح مقيّدة: القيمة المحسوبة %.2f م/ث خارج مدى صلاحية UTCI "
                    "(%.1f إلى %.1f)، فاستُخدمت %.2f م/ث."
                    % (v10, lim["wind_min_ms"], lim["wind_max_ms"], used))

    # CA-02 — MRT: مفترضة، أو من الكرة عند تفعيلها
    if use_globe:
        # بسرعة الرياح عند الكرة، لا عند 10 م
        if _is_num(tg_used) and _is_num(ta) and _is_num(wind_ms):
            mrt = mean_radiant(tg_used, ta, max(wind_ms, 0.0),
                               globe["diameter_m"], globe["emissivity"])
            out["mrt_c"] = round(mrt, 2) if mrt is not None else None
            if mrt is None:
                out["notes"].append("تعذر حساب MRT من قراءة الكرة الحالية.")
    elif _is_num(ta):
        out["mrt_c"] = round(ta, 2)
        out["notes"].append(
            "MRT مفترضة مساوية لحرارة الهواء، لأن الكرة الحرارية مؤجلة في هذا "
            "الإصدار. لتفعيلها: اجعل mrt_source = \"globe\" في ملف الإعدادات.")

    if missing:
        out["utci_unavailable_reason"] = "لا يُحسب UTCI لنقص: " + "، ".join(missing) + "."
        return out

    if out["mrt_c"] is None:
        out["utci_unavailable_reason"] = (
            "لا يُحسب UTCI لتعذر حساب MRT من الكرة." if use_globe
            else "لا يُحسب UTCI لتعذر تحديد MRT.")
        return out

    # CA-04 — حماية مدى MRT
    if not (ta - lim["mrt_below_tdb_c"] <= out["mrt_c"] <= ta + lim["mrt_above_tdb_c"]):
        out["utci_unavailable_reason"] = (
            "MRT (%.1f °م) خارج مدى صلاحية UTCI المسموح مع حرارة هواء %.1f °م "
            "(من %.1f إلى %.1f). راجع معايرة الكرة."
            % (out["mrt_c"], ta, ta - lim["mrt_below_tdb_c"], ta + lim["mrt_above_tdb_c"]))
        return out

    # CA-03
    val, reason = utci_value(ta, out["mrt_c"], out["v10_used_ms"], rh)
    if val is None:
        out["utci_unavailable_reason"] = reason
        return out

    out["utci_c"] = round(val, 1)
    key, ar = stress_band(out["utci_c"])
    out["stress_key"] = key
    out["stress_category"] = ar
    return out


def wind_from_voltage(wind_v, node_settings):
    """
    SV-15 — إعادة حساب سرعة الرياح من الجهد الخام بمعاملات المعايرة المحفوظة
    في الخادم، حتى لا نعيد برمجة ESP32 بعد كل معايرة.
        wind_ms = K × wind_v + B،  وتساوي صفرًا إن كان wind_v أقل من V_MIN.
    """
    if not _is_num(wind_v):
        return None
    v_min = node_settings.get("wind_v_min", 0.02)
    if wind_v < v_min:
        return 0.0
    k = node_settings.get("wind_k", 20.0)
    b = node_settings.get("wind_b", 0.5)
    return round(max(k * wind_v + b, 0.0), 3)
