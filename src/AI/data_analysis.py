"""
HABOOB - Time Series & Statistical Data Analysis

This module analyzes historical environmental sensor data
to identify temperature trends, WBGT variations,
and high-risk zones.

Input is either a CSV file (timestamp, temperature, wbgt, zone) or the
server's SQLite database (data/readings.db). pandas is imported only when an
analysis runs, so the web server never needs it.
"""

import json
import sqlite3


def _pd():
    import pandas as pd
    return pd


# 1. Load historical sensor data
def load_data(csv_file):
    """
    Load environmental sensor readings from a CSV file.
    """
    pd = _pd()
    df = pd.read_csv(csv_file)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    return df


def load_database(db_path, node_id=None):
    """
    Load readings from the server database in the same shape as the CSV:
    timestamp, temperature, wbgt, zone (the zone is the node id).
    Rows without a WBGT value are skipped; nothing is filled in.
    """
    pd = _pd()
    q = ("SELECT rx_ts, ta_c, wbgt_c, node_id FROM readings "
         "WHERE wbgt_c IS NOT NULL")
    args = []
    if node_id:
        q += " AND node_id = ?"
        args.append(node_id)
    q += " ORDER BY rx_ts"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(q, args).fetchall()
    df = pd.DataFrame(rows, columns=["rx_ts", "temperature", "wbgt", "zone"])
    df["timestamp"] = pd.to_datetime(df.pop("rx_ts"), unit="s")
    return df[["timestamp", "temperature", "wbgt", "zone"]]


def process_database(db_path):
    """
    Latest reading of every node, as the input the decision engine expects:
    [{"node_id": ..., "derived": {ta_c, rh_pct, wind_ms, solar_radiation_wm2,
                                  wbgt_c, flag, wbgt_method}}].
    """
    out = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        nodes = [r[0] for r in conn.execute("SELECT DISTINCT node_id FROM readings")]
        for node in nodes:
            r = conn.execute("SELECT * FROM readings WHERE node_id = ? "
                             "ORDER BY rx_ts DESC LIMIT 1", (node,)).fetchone()
            try:
                d = json.loads(r["derived_json"]).get("derived", {})
            except (ValueError, TypeError):
                d = {}
            out.append({"node_id": node, "derived": {
                "ta_c": r["ta_c"], "rh_pct": r["rh_pct"], "wind_ms": r["wind_ms"],
                "solar_radiation_wm2": d.get("solar_wm2"),
                "wbgt_c": r["wbgt_c"], "flag": r["flag"],
                "wbgt_method": d.get("wbgt_method")}})
    return out


# 2. Statistical analysis
def statistical_analysis(df):
    """
    Calculate statistical summaries of temperature and WBGT.
    """

    columns = ["temperature", "wbgt"]

    return df[columns].agg(
        ["mean", "max", "min", "std"]
    )


# 3. Time series analysis
def time_series_analysis(df):
    """
    Calculate average temperature and WBGT for each minute.
    """

    data = df.copy()

    data = data.set_index("timestamp")

    result = data.resample("1min")[
        ["temperature", "wbgt"]
    ].mean()

    return result


# 4. Trend detection
def detect_trend(df):
    """
    Detect whether WBGT is increasing or decreasing.
    """

    data = df.sort_values("timestamp")

    if len(data) < 2:
        return "Insufficient data"

    first = data["wbgt"].iloc[0]
    last = data["wbgt"].iloc[-1]

    if last > first:
        return "Increasing heat stress"

    elif last < first:
        return "Decreasing heat stress"

    return "Stable heat stress"


# 5. Zone comparison
def compare_zones(df):
    """
    Compare average WBGT across different Expo zones.
    """

    return (
        df.groupby("zone")["wbgt"]
        .mean()
        .sort_values(ascending=False)
    )


# 6. Main analysis function
def analyze_data(path):
    """
    Run all statistical and time series analyses on a .csv or .db file.
    """

    df = load_database(path) if str(path).endswith((".db", ".sqlite")) else load_data(path)

    print("\n--- Statistical Analysis ---")
    print(statistical_analysis(df))

    print("\n--- Time Series Analysis ---")
    print(time_series_analysis(df))

    print("\n--- WBGT Trend ---")
    print(detect_trend(df))

    print("\n--- Zone Comparison ---")
    print(compare_zones(df))


if __name__ == "__main__":
    import sys
    analyze_data(sys.argv[1] if len(sys.argv) > 1 else "data/readings.db")
