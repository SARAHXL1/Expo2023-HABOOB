"""
HABOOB - Heat Stress Analysis

Analyzes environmental conditions and identifies
potential contributors to heat stress.
"""


def analyze_heat(data):
    """
    Analyze environmental readings and WBGT results.
    """

    wbgt = data.get("wbgt_c")
    temp = data.get("ta_c")
    humidity = data.get("rh_pct")
    wind = data.get("wind_ms")
    solar = data.get("solar_radiation_wm2")

    if wbgt is None:
        return {
            "status": "unavailable",
            "reason": "WBGT calculation is unavailable.",
            "factors": []
        }

    factors = []

    # High solar radiation
    if solar is not None and solar >= 700:
        factors.append({
            "factor": "High Solar Radiation",
            "value": solar,
            "reason": "Strong sunlight increases radiant heat exposure."
        })

    # Low wind speed
    if wind is not None and wind < 2.0:
        factors.append({
            "factor": "Low Wind Speed",
            "value": wind,
            "reason": "Low airflow can reduce evaporative cooling."
        })

    # High air temperature
    if temp is not None and temp >= 38:
        factors.append({
            "factor": "High Air Temperature",
            "value": temp,
            "reason": "High air temperature reduces the body's ability to lose heat."
        })

    # High humidity
    if humidity is not None and humidity >= 60:
        factors.append({
            "factor": "High Humidity",
            "value": humidity,
            "reason": "High humidity reduces sweat evaporation."
        })

    return {
        "status": "analyzed",
        "wbgt_c": wbgt,
        "risk_level": data.get("flag"),
        "factors": factors,
        "factor_count": len(factors),
        "analysis_method": "rule_based_screening"
    }