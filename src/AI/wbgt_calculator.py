"""Compute sun angle and WBGT according to the HABOOB reference appendix."""
import math


def cos_zenith(local_time, cfg):
    """NOAA-style approximate cosine of solar zenith angle in local time."""
    day = local_time.timetuple().tm_yday
    hour = local_time.hour + local_time.minute / 60 + local_time.second / 3600
    gamma = 2 * math.pi / 365 * (day - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(gamma)
                    - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma)
                    - 0.040849 * math.sin(2 * gamma))
    solar_minutes = hour * 60 + eqt + 4 * cfg["longitude"] - 60 * cfg["timezone_utc_offset_hours"]
    angle = math.radians(solar_minutes / 4 - 180)
    latitude = math.radians(cfg["latitude"])
    return max(0.0, math.sin(latitude) * math.sin(decl)
               + math.cos(latitude) * math.cos(decl) * math.cos(angle))


def wbgt_liljegren(ta_c, rh_pct, wind_10m_ms, solar_wm2, direct_fraction, cos_sza, pressure_hpa):
    """Call ECMWF thermofeel; it expects air temperature in kelvin and RH in %."""
    import numpy as np
    import thermofeel as tf
    scalar = lambda x: np.array([x], dtype=float)
    value_k = tf.calculate_wbgt_liljegren(
        scalar(ta_c + 273.15), scalar(rh_pct), scalar(pressure_hpa),
        scalar(wind_10m_ms), scalar(solar_wm2), scalar(direct_fraction), scalar(cos_sza)
    )
    value_c = float(value_k[0]) - 273.15
    if not math.isfinite(value_c):
        raise ArithmeticError("WBGT model did not converge")
    return value_c


def wbgt_simple(ta_c, rh_pct):
    """Documented approximate fallback when wind or light sensors are missing."""
    vapor_pressure_hpa = rh_pct / 100 * 6.112 * math.exp(17.62 * ta_c / (243.12 + ta_c))
    return 0.567 * ta_c + 0.393 * vapor_pressure_hpa + 3.94
