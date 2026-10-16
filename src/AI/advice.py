"""تفسير السبب والتوصية والأثر المتوقع — الملحق ب والقسم 7.2 من دليل علم البيانات v3.

كل الأرقام هنا ناتجة من دالة WBGT نفسها (إعادة الحساب بمدخل معدّل)، لا من تخمين.
"""
from .wbgt_calculator import wbgt_liljegren
from .risk_classification import wbgt_flag

SHADE_WM2 = 120.0      # الإشعاع المنتشر المتبقي تحت المظلة (افتراض معلن)
FAN_V10_MS = 3.0       # سرعة الرياح على 10 م بعد تشغيل المراوح (افتراض معلن)
FAN_MAX_TA_C = 37.0    # فوقها قد تزيد المراوح الإجهاد في الحر الجاف
LOW_WIND_MS = 1.5      # تحتها تُعد الرياح ضعيفة


def explain(ta, rh, v10, ghi, fdir, cz, p_hpa, v10_ref=FAN_V10_MS):
    """مساهمة كل عامل = WBGT الآن − WBGT والعامل عند قيمته المرجعية."""
    base = wbgt_liljegren(ta, rh, v10, ghi, fdir, cz, p_hpa)
    no_sun = wbgt_liljegren(ta, rh, v10, 0.0, 0.0, cz, p_hpa)
    windy = wbgt_liljegren(ta, rh, max(v10_ref, v10), ghi, fdir, cz, p_hpa)
    return {"wbgt": round(base, 1),
            "radiation": round(base - no_sun, 1) + 0.0,
            "low_wind": round(base - windy, 1) + 0.0}


def advise(ta, rh, v10, ghi, fdir, cz, p_hpa, flag, contrib):
    """جدول القواعد 7.2 + الأثر المتوقع لكل إجراء مقترح."""
    if flag in (None, "white", "green"):
        return {"action": "monitor", "systems": [], "drop_c": 0.0,
                "after_c": contrib["wbgt"], "after_flag": flag}
    base = contrib["wbgt"]
    systems = []
    shade_after = wbgt_liljegren(ta, rh, v10, min(ghi, SHADE_WM2), 0.0, cz, p_hpa)
    fan_after = wbgt_liljegren(ta, rh, max(v10, FAN_V10_MS), ghi, fdir, cz, p_hpa)
    if flag in ("red", "black"):
        systems = ["shading", "coolingSys"]
        after = shade_after
    elif contrib["radiation"] >= contrib["low_wind"] and contrib["radiation"] > 0.5:
        systems, after = ["shading"], shade_after
    elif v10 < LOW_WIND_MS and ta < FAN_MAX_TA_C:
        systems, after = ["fans"], fan_after
    else:
        systems, after = ["shading"], shade_after
    return {"action": "intervene", "systems": systems,
            "drop_c": round(base - after, 1), "after_c": round(after, 1),
            "after_flag": wbgt_flag(after)}
