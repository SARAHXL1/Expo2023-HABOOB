"""
تحميل ملف الإعدادات الوحيد config.json  (SV-14) — مشروع هبوب
وتعريف كتالوج القطع المذكور في الجدول 3.1 من المتطلبات.

كل الرسائل الموجهة للمستخدم بالعربي، وأسماء الحقول والمتغيرات بالإنجليزي (NF-07).
"""

import json
import os
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")

_lock = threading.Lock()
_cfg = None


def load(force=False):
    """يقرأ config.json ويحتفظ بنسخة في الذاكرة."""
    global _cfg
    with _lock:
        if _cfg is None or force:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _cfg = json.load(f)
        return _cfg


def cfg():
    return load()


def save(new_cfg):
    """يكتب الإعدادات على القرص (تستخدمها نقطة المعايرة SV-15)."""
    global _cfg
    with _lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        _cfg = new_cfg
    return _cfg


def node_cfg(node_id):
    """إعدادات عقدة بعينها، مع الرجوع للقيم الافتراضية لأي حقل ناقص."""
    c = cfg()
    merged = dict(c.get("node_defaults", {}))
    merged.update(c.get("nodes", {}).get(node_id, {}))
    merged.setdefault("name", node_id)
    return merged


def mode():
    """وضع التشغيل: live (العتاد الحقيقي) أو sim (المحاكاة)."""
    return cfg().get("mode", "sim")


def set_mode(new_mode):
    if new_mode not in ("live", "sim"):
        raise ValueError("الوضع يجب أن يكون live أو sim")
    c = json.loads(json.dumps(cfg()))
    c["mode"] = new_mode
    save(c)
    return new_mode


def mrt_source():
    """مصدر MRT: assumed (تساوي حرارة الهواء) أو globe (من الكرة الحرارية)."""
    return cfg().get("mrt_source", "assumed")


def globe_enabled():
    """
    الكرة الحرارية مؤجلة في الإصدار 2، لأن التقييم داخل القاعة لا في الشمس.
    هذا هو المفتاح الوحيد لإعادتها: mrt_source = "globe".
    """
    return mrt_source() == "globe"


def effective_disabled():
    """
    القطع المعطلة فعليًا: المعطلة صراحة في الإعدادات، ويُضاف إليها
    DS18B20 ما دامت الكرة مؤجلة.
    """
    out = set(cfg().get("disabled_sensors", []))
    if not globe_enabled():
        out.add("ds18b20")
    return out


def db_path():
    # HABOOB_DB: مسار قاعدة بديل للتجارب، حتى لا تختلط بيانات التجربة بقاعدة العرض
    p = os.environ.get("HABOOB_DB") or cfg()["server"]["db_path"]
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


# ---------------------------------------------------------------------------
# كتالوج القطع — الجدول 3.1
#   id      : معرّف القطعة في الموقع وفي رسالة JSON
#   ar      : الاسم بالعربي الظاهر على البطاقة
#   tech    : الاسم التقني
#   port    : منفذ التوصيل كتذكير على البطاقة
#   fields  : الحقول الرقمية التي ترسلها هذه القطعة (تُفحص بجدول المدى 3.3)
#   help    : رسائل المساعدة عند الأعطال — الجدول 8.4
# ---------------------------------------------------------------------------
SENSOR_CATALOG = [
    {
        "id": "esp32", "ar": "لوحة التحكم", "tech": "ESP32 DevKit V1", "port": "—",
        "fields": ["rssi"],
        "help": {
            "*": "تحقق من كابل USB والطاقة، ومن الواي فاي 2.4 GHz، ومن عنوان الخادم "
                 "في إعدادات ESP32، أو استخدم جسر USB.",
        },
    },
    {
        "id": "dht22", "ar": "حرارة الهواء والرطوبة", "tech": "DHT22", "port": "GPIO 4",
        "fields": ["ta_c", "rh_pct"],
        "help": {
            "read_error": "تحقق من طرف OUT على GPIO 4 ومن التغذية 3V3 "
                          "(الوحدة فيها مقاومة السحب أصلًا)، ولا تقرأه أسرع من كل ثانيتين.",
            "not_found": "DHT22 لا يُكتشف مسبقًا: الحالة تأتي من أول قراءة. "
                         "تحقق من طرف OUT على GPIO 4 ومن التغذية 3V3.",
            "out_of_range": "القراءة خارج المدى المنطقي: تحقق من أن الحساس داخل الواقي الإشعاعي "
                            "ولا يلمس جدرانه.",
        },
    },
    {
        "id": "ds18b20", "ar": "حرارة الكرة الحرارية", "tech": "DS18B20 (مؤجلة)",
        "port": "GPIO 13 (1-Wire)",
        "fields": ["tg_c"],
        "help": {
            "not_found": "تحقق من مقاومة 4.7kΩ بين DATA و3V3، ومن ألوان الأسلاك؛ "
                         "القيمة −127 تعني انقطاعًا.",
            "read_error": "تحقق من مقاومة 4.7kΩ بين DATA و3V3، ومن ألوان الأسلاك؛ "
                          "القيمة −127 تعني انقطاعًا.",
            "out_of_range": "حرارة الكرة خارج المدى: تأكد أن المجس في مركز الكرة ولا يلمس جدارها.",
        },
    },
    {
        "id": "ads1115", "ar": "المحول التناظري الرقمي", "tech": "ADS1115 — الموتور فقط",
        "port": "I2C 0x48",
        "fields": [],
        "help": {
            "not_found": "العنوان 0x48 غير موجود: تحقق من SDA (GPIO 21) وSCL (GPIO 22) "
                         "ومن توصيل ADDR بـ GND. المدخل A1 غير مستخدم في هذا الإصدار.",
            "read_error": "الشريحة تستجيب لكن القراءة فشلت: تحقق من ثبات التغذية 3V3.",
        },
    },
    {
        "id": "anemometer", "ar": "مقياس الرياح", "tech": "موتور DC عبر ADS1115", "port": "A0",
        "fields": ["wind_v", "wind_ms"],
        "help": {
            "out_of_range": "راجع كسب ADS1115 (GAIN_FOUR)، أو اعكس سلكي الموتور إن كانت القيمة سالبة.",
            "not_found": "الموتور يُقرأ عبر ADS1115: تحقق أولًا من بطاقة ADS1115.",
            "read_error": "تحقق من مقاومة 1kΩ على التوالي مع الموتور، ومن مقاومة الحِمل 10kΩ "
                          "بين طرفيه.",
        },
    },
    {
        "id": "mlx90614", "ar": "حرارة سطح الأرض", "tech": "MLX90614", "port": "I2C 0x5A",
        "fields": ["tsurf_c", "tamb_c"],
        "help": {
            "not_found": "العنوان 0x5A غير موجود: تحقق من التغذية ومن لحام الأطراف، "
                         "ومن أن سرعة I2C مضبوطة على 100 kHz.",
            "read_error": "تحقق من ثبات التغذية ومن طول أسلاك I2C.",
            "out_of_range": "القراءة خارج المدى: تأكد أن الحساس مائل للأسفل 30 إلى 45 درجة "
                            "وبعيد عن ظل العمود.",
        },
    },
    {
        "id": "veml7700", "ar": "شدة الإضاءة", "tech": "VEML7700", "port": "I2C 0x10",
        "fields": ["lux"],
        "help": {
            "not_found": "العنوان 0x10 غير موجود: تحقق من VIN وSDA وSCL ومن لحام الأطراف.",
            "read_error": "تحقق من أسلاك I2C ومن ثبات التغذية 3V3.",
            "out_of_range": "الإضاءة خارج المدى المسموح (حتى 140,000 لوكس حسب ملف المواصفات).",
        },
    },
    {
        "id": "battery", "ar": "البطارية", "tech": "مؤجلة — التغذية من USB", "port": "—",
        "fields": ["bat_v"],
        "help": {
            "out_of_range": "تحقق من مقسّم الجهد (10kΩ + 10kΩ) على A1؛ "
                            "والجهد المنخفض يعني الحاجة للشحن.",
            "not_found": "البطارية تُقرأ عبر ADS1115: تحقق أولًا من بطاقة ADS1115.",
            "read_error": "تحقق من مقسّم الجهد على A1 ومن نقطة المنتصف.",
        },
    },
    {
        "id": "tft", "ar": "شاشة العرض", "tech": "ST7789V2 1.69 بوصة · 240×280",
        "port": "SPI (CS 5 · DC 16 · RST 17)",
        "fields": [],
        "help": {
            "*": "الشاشة لا ترسل قراءة، وحالتها «مفترضة». إن ظهرت بيضاء راجع DC وRST، "
                 "وتأكد من تهيئة المقاس init(240, 280) ومن الإزاحة الصحيحة.",
        },
    },
]

SENSOR_BY_ID = {s["id"]: s for s in SENSOR_CATALOG}

# أي حقل ينتمي لأي قطعة (يُستخدم في فحص المدى وفي تصدير CSV)
FIELD_OWNER = {}
for _s in SENSOR_CATALOG:
    for _f in _s["fields"]:
        FIELD_OWNER[_f] = _s["id"]

# الحالات السبع — الجدول 3.2
STATUS_OK = "ok"
STATUS_NOT_FOUND = "not_found"
STATUS_READ_ERROR = "read_error"
STATUS_OUT_OF_RANGE = "out_of_range"
STATUS_STALE = "stale"
STATUS_DISABLED = "disabled"
STATUS_ASSUMED = "assumed"
# حالة عرض إضافية (ليست من حالات العقدة السبع): تُستخدم في وضع العتاد الحقيقي
# عندما لا تكون هناك عقدة ترسل أصلًا، فتظهر كل البطاقات «غير متصل» بدل أن تختفي.
STATUS_NOT_CONNECTED = "not_connected"

STATUS_AR = {
    STATUS_OK: "يعمل",
    STATUS_NOT_FOUND: "غير موجود",
    STATUS_READ_ERROR: "قراءة خاطئة",
    STATUS_OUT_OF_RANGE: "خارج المدى",
    STATUS_STALE: "متوقف",
    STATUS_DISABLED: "معطّل",
    STATUS_ASSUMED: "مفترض",
    STATUS_NOT_CONNECTED: "غير متصل",
}

# ترتيب الخطورة لفرز التنبيهات (SV-06)
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
