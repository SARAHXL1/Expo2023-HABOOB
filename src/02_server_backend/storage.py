"""
التخزين المحلي في SQLite وتصدير CSV.
يغطي: SV-08، SV-10، SV-02 (سجل الأخطاء)، NF-08 (البيانات الخام لا تُعدّل).
"""

import csv
import io
import json
import os
import sqlite3
import threading
import time
from collections import deque

from settings import db_path, cfg, SENSOR_CATALOG, FIELD_OWNER

_lock = threading.Lock()
_conn = None

# سجل الرسائل المرفوضة في الذاكرة (GET /api/errors)
_errors = deque(maxlen=200)

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rx_ts       REAL    NOT NULL,
    ts          REAL,
    node_id     TEXT    NOT NULL,
    transport   TEXT,
    raw_json    TEXT    NOT NULL,   -- الرسالة كما وصلت، لا تُعدّل أبدًا (NF-08)
    derived_json TEXT   NOT NULL,   -- القيم المشتقة والحالات بجانبها
    ta_c REAL, rh_pct REAL, tg_c REAL, tsurf_c REAL, tamb_c REAL,
    wind_v REAL, wind_ms REAL, lux REAL, bat_v REAL, rssi REAL,
    mrt_c REAL, v10_ms REAL, utci_c REAL, stress_category TEXT,
    battery_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_readings_node_time ON readings (node_id, rx_ts);

CREATE TABLE IF NOT EXISTS decisions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    rx_ts     REAL NOT NULL,
    node_id   TEXT,
    pole_id   TEXT,
    zone      TEXT,
    systems   TEXT,            -- JSON: الأنظمة التي اعتمدها المشغل (shading, fans, coolingSys)
    wbgt_c    REAL,            -- WBGT وقت القرار
    flag      TEXT,
    expected_c REAL,           -- الأثر المتوقع من advice (محسوب، لا مقيس)
    expected_flag TEXT
);

CREATE TABLE IF NOT EXISTS rejected (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    rx_ts    REAL NOT NULL,
    reason   TEXT NOT NULL,
    source   TEXT,
    body     TEXT
);
"""

NUMERIC_COLUMNS = ["ta_c", "rh_pct", "tg_c", "tsurf_c", "tamb_c",
                   "wind_v", "wind_ms", "lux", "bat_v", "rssi"]
DERIVED_COLUMNS = ["mrt_c", "v10_ms", "utci_c", "battery_pct", "wbgt_c"]

# أعمدة أُضيفت بعد إنشاء القاعدة: تُضاف تلقائيًا لقاعدة قديمة دون حذف بياناتها
MIGRATIONS = [("wbgt_c", "REAL"), ("flag", "TEXT")]


def init():
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        path = db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        have = {r[1] for r in _conn.execute("PRAGMA table_info(readings)")}
        for col, typ in MIGRATIONS:
            if col not in have:
                _conn.execute("ALTER TABLE readings ADD COLUMN %s %s" % (col, typ))
        _conn.commit()
        return _conn


def conn():
    return init()


def save_reading(processed, raw_msg):
    """SV-08 — تخزين الرسالة الخام مع القيم المشتقة."""
    d = processed["derived"]
    v = processed["values"]
    row = {
        "rx_ts": processed["rx_ts"],
        "ts": processed["ts"],
        "node_id": processed["node_id"],
        "transport": processed["transport"],
        "raw_json": json.dumps(raw_msg, ensure_ascii=False),
        "derived_json": json.dumps(
            {"sensors": {k: {"status": s["status"], "values": s["values"]}
                         for k, s in processed["sensors"].items()},
             "derived": d,
             "alerts": processed["alerts"]},
            ensure_ascii=False),
        "stress_category": d.get("stress_category"),
        "flag": d.get("flag"),
    }
    for col in NUMERIC_COLUMNS:
        row[col] = v.get(col)
    for col in DERIVED_COLUMNS:
        row[col] = d.get(col)

    cols = ", ".join(row.keys())
    marks = ", ".join("?" for _ in row)
    with _lock:
        _conn.execute("INSERT INTO readings (%s) VALUES (%s)" % (cols, marks),
                      list(row.values()))
        _conn.commit()


def save_decision(d):
    """قرار المشغل في المنصة (تفعيل الآن). الأثر المتوقع محسوب من advice وليس قياسًا."""
    row = (time.time(), d.get("node_id"), d.get("pole_id"), d.get("zone"),
           json.dumps(d.get("systems") or [], ensure_ascii=False),
           d.get("wbgt_c"), d.get("flag"), d.get("expected_c"), d.get("expected_flag"))
    with _lock:
        cur = _conn.execute(
            "INSERT INTO decisions (rx_ts,node_id,pole_id,zone,systems,wbgt_c,flag,expected_c,expected_flag) "
            "VALUES (?,?,?,?,?,?,?,?,?)", row)
        _conn.commit()
    return {"id": cur.lastrowid, "rx_ts": row[0]}


def recent_decisions(limit=10):
    with _lock:
        rows = _conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        x = dict(r)
        try:
            x["systems"] = json.loads(x["systems"] or "[]")
        except Exception:
            x["systems"] = []
        out.append(x)
    return out


def save_rejected(reason, body, source="unknown"):
    """SV-02 — تسجيل الرسالة المرفوضة وسببها."""
    rec = {"rx_ts": time.time(), "reason": reason, "source": source,
           "body": (body or "")[:2000]}
    _errors.appendleft(rec)
    try:
        with _lock:
            _conn.execute("INSERT INTO rejected (rx_ts, reason, source, body) VALUES (?,?,?,?)",
                          (rec["rx_ts"], reason, source, rec["body"]))
            _conn.commit()
    except Exception:
        pass
    return rec


def recent_errors(limit=None):
    limit = limit or cfg()["server"]["errors_keep"]
    return list(_errors)[:limit]


def history(node_id, minutes=15):
    """GET /api/history — سلسلة زمنية للرسوم الصغيرة."""
    since = time.time() - minutes * 60
    with _lock:
        rows = _conn.execute(
            "SELECT rx_ts, ta_c, tg_c, wind_ms, bat_v, mrt_c, utci_c, lux, tsurf_c, rh_pct, wbgt_c "
            "FROM readings WHERE node_id = ? AND rx_ts >= ? ORDER BY rx_ts ASC",
            (node_id, since)).fetchall()
    series = {k: [] for k in ("t", "ta_c", "tg_c", "mrt_c", "utci_c", "wind_ms",
                              "bat_v", "lux", "tsurf_c", "rh_pct", "wbgt_c")}
    for r in rows:
        series["t"].append(round(r["rx_ts"], 1))
        for k in list(series.keys())[1:]:
            series[k].append(r[k])
    return series


def export_csv(node_id=None, ts_from=None, ts_to=None):
    """
    SV-10 — تصدير CSV بعمود لكل قيمة وعمود لكل حالة.
    يُكتب بترميز UTF-8 مع BOM حتى يفتح الإكسل العربية بشكل صحيح.
    """
    q = "SELECT * FROM readings WHERE 1=1"
    args = []
    if node_id:
        q += " AND node_id = ?"
        args.append(node_id)
    if ts_from:
        q += " AND rx_ts >= ?"
        args.append(float(ts_from))
    if ts_to:
        q += " AND rx_ts <= ?"
        args.append(float(ts_to))
    q += " ORDER BY rx_ts ASC"

    with _lock:
        rows = _conn.execute(q, args).fetchall()

    sensor_ids = [s["id"] for s in SENSOR_CATALOG]
    header = (["rx_time_local", "rx_ts", "ts", "node_id", "transport"]
              + NUMERIC_COLUMNS
              + ["mrt_c", "v10_ms", "utci_c", "stress_category", "battery_pct", "wbgt_c", "flag"]
              + ["status_" + sid for sid in sensor_ids]
              + ["alerts"])

    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        try:
            dj = json.loads(r["derived_json"])
        except Exception:
            dj = {}
        statuses = {k: v.get("status") for k, v in (dj.get("sensors") or {}).items()}
        alerts = "؛ ".join(a.get("text", "") for a in (dj.get("alerts") or []))
        line = [time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["rx_ts"])),
                round(r["rx_ts"], 3), r["ts"], r["node_id"], r["transport"]]
        line += [r[c] for c in NUMERIC_COLUMNS]
        line += [r["mrt_c"], r["v10_ms"], r["utci_c"], r["stress_category"], r["battery_pct"],
                 r["wbgt_c"], r["flag"]]
        line += [statuses.get(sid, "") for sid in sensor_ids]
        line.append(alerts)
        w.writerow(line)
    return buf.getvalue()


def known_nodes():
    with _lock:
        rows = _conn.execute("SELECT DISTINCT node_id FROM readings").fetchall()
    return [r["node_id"] for r in rows]


def prune():
    """حذف السجلات الأقدم من النافذة المحددة، حتى لا يتضخم الملف (NF-04)."""
    keep = cfg()["server"].get("history_keep_minutes", 180)
    if not keep:
        return 0
    cutoff = time.time() - keep * 60
    with _lock:
        cur = _conn.execute("DELETE FROM readings WHERE rx_ts < ?", (cutoff,))
        _conn.execute("DELETE FROM rejected WHERE rx_ts < ?", (cutoff,))
        _conn.commit()
    return cur.rowcount


def stats():
    with _lock:
        n = _conn.execute("SELECT COUNT(*) AS c FROM readings").fetchone()["c"]
        e = _conn.execute("SELECT COUNT(*) AS c FROM rejected").fetchone()["c"]
    return {"readings": n, "rejected": e, "db_path": db_path()}
