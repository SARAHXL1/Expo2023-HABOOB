"""
HABOOB - Decision Engine

Combines environmental analysis,
risk classification and recommendations
into a dashboard-ready response.

Run from the project root:
    python3 -m AI.decision_engine --db data/readings.db
"""

import json
import argparse

from .heat_analysis import analyze_heat
from .recommendation_engine import generate_recommendation


def make_decision(node_id, derived):

    # Analyze environmental conditions
    analysis = analyze_heat(derived)

    # Generate operational recommendation
    recommendation = generate_recommendation(
        derived,
        analysis
    )

    # Prepare output for website backend
    return {
        "node_id": node_id,

        "environment": {
            "temperature_c": derived.get("ta_c"),
            "humidity_pct": derived.get("rh_pct"),
            "wind_ms": derived.get("wind_ms"),
            "solar_wm2": derived.get(
                "solar_radiation_wm2"
            )
        },

        "heat_stress": {
            "index": "WBGT",
            "value_c": derived.get("wbgt_c"),
            "risk_level": derived.get("flag"),
            "method": derived.get("wbgt_method")
        },

        "analysis": analysis,

        "recommendation": recommendation
    }


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        default="data/readings.db"
    )

    args = parser.parse_args()

    # imported here: data_analysis is only needed for the database command line
    from .data_analysis import process_database

    results = process_database(args.db)

    for item in results:

        derived = item["derived"]

        decision = make_decision(
            item["node_id"],
            derived
        )

        print(
            json.dumps(
                decision,
                ensure_ascii=False,
                indent=4
            )
        )


if __name__ == "__main__":
    main()
