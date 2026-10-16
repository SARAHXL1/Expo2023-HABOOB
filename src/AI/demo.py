"""Run one synthetic sample without sensors or a website."""
import json
from datetime import datetime, timezone, timedelta
from .pipeline import process_reading


def main():
    sample = {"node_id": "node-01", "sensors": {
        "dht22": {"status": "ok", "ta_c": 35, "rh_pct": 20},
        "anemometer": {"status": "ok", "wind_v": 0.025, "height_m": 1.8},
        "veml7700": {"status": "ok", "lux": 88000}
    }}
    local_noon = datetime(2026, 10, 13, 12, tzinfo=timezone(timedelta(hours=3)))
    print(json.dumps({"node_id": sample["node_id"], "derived": process_reading(sample, local_noon)}, indent=2))


if __name__ == "__main__":
    main()
