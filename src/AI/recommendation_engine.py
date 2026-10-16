"""
HABOOB - Recommendation Engine

Generates operational recommendations
based on heat stress and environmental conditions.
"""


def generate_recommendation(data, analysis):

    risk = data.get("flag")

    wind = data.get("wind_ms")
    solar = data.get("solar_radiation_wm2")
    humidity = data.get("rh_pct")

    if risk is None:
        return {
            "action": "CHECK_SENSOR",
            "title": "التحقق من قراءات المستشعر",
            "reason": "بيانات الإجهاد الحراري غير متوفرة.",
            "priority": "high",
            "expected_effect": "استعادة المراقبة الموثوقة."
        }

    # Low heat stress
    if risk == "white":
        return {
            "action": "MONITOR",
            "title": "مواصلة المراقبة",
            "reason": "مؤشر الإجهاد الحراري ضمن المستوى الأقل.",
            "priority": "low",
            "expected_effect": "متابعة التغيرات الحرارية."
        }

    # Critical heat stress
    if risk == "black":
        return {
            "action": "LIMIT_EXPOSURE",
            "title": "تقليل التعرض للحرارة فورًا",
            "reason": "مؤشر الإجهاد الحراري عند مستوى حرج.",
            "priority": "critical",
            "expected_effect": "تقليل تعرض الزوار للإجهاد الحراري."
        }

    # Strong sunlight
    if solar is not None and solar >= 700:
        return {
            "action": "ACTIVATE_SHADING",
            "title": "تفعيل المظلات المتحركة",
            "reason": "الإشعاع الشمسي مرتفع في المنطقة.",
            "priority": "high" if risk == "red" else "medium",
            "expected_effect": "تقليل التعرض المباشر لأشعة الشمس."
        }

    # Hot and relatively dry conditions
    if (
        data.get("ta_c") is not None
        and data["ta_c"] >= 38
        and humidity is not None
        and humidity < 50
    ):
        return {
            "action": "ACTIVATE_MISTING",
            "title": "تشغيل نظام الرذاذ",
            "reason": "الهواء حار ورطوبته منخفضة نسبيًا.",
            "priority": "medium",
            "expected_effect": "خفض حرارة الهواء موضعيًا مع مراقبة الرطوبة."
        }

    # Low wind
    if wind is not None and wind < 2.0:
        return {
            "action": "REVIEW_FANS",
            "title": "تقييم تشغيل المراوح",
            "reason": "حركة الهواء منخفضة.",
            "priority": "medium",
            "expected_effect": "تحسين حركة الهواء إذا كانت الظروف مناسبة."
        }

    return {
        "action": "MONITOR_AND_REVIEW",
        "title": "متابعة المنطقة وتقييم التبريد",
        "reason": "مؤشر الإجهاد الحراري يحتاج متابعة.",
        "priority": "medium",
        "expected_effect": "دعم اتخاذ الإجراء المناسب."
    }