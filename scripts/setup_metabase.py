"""Configure Metabase as the BI layer: admin user, ERP connection, questions and dashboard.

Idempotent: re-running reuses the existing database, questions and dashboard by name.
Local demo credentials only (Metabase is bound to 127.0.0.1).

Usage:  uv run python scripts/setup_metabase.py
"""
from __future__ import annotations

import os
import time

import requests

MB = "http://localhost:3000/api"
EMAIL = os.environ.get("MB_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.environ.get("MB_ADMIN_PASSWORD", "Governance-demo-2026")
DB_NAME = "ERP warehouse"
DASHBOARD = "Supply Chain Performance"
S = requests.Session()

# Native SQL questions: OpenMetadata parses this SQL to draw table -> chart lineage.
QUESTIONS = [
    {
        "name": "OTIF by plant (monthly)",
        "description": "OTIF, on-time and in-full rate per plant and month. Target 95 %.",
        "display": "line",
        "sql": "SELECT measure_month, plant_id, otif_rate, on_time_rate, in_full_rate\n"
               "FROM analytics_marts.rpt_otif_monthly\nORDER BY measure_month, plant_id",
        "viz": {"graph.dimensions": ["measure_month", "plant_id"], "graph.metrics": ["otif_rate"]},
        "pos": (0, 0, 12, 8),
    },
    {
        "name": "Plan vs Actual by month",
        "description": "Consensus demand plan vs. actual order intake, with forecast accuracy.",
        "display": "bar",
        "sql": "SELECT plan_month, SUM(planned_qty) AS planned_qty, SUM(actual_qty) AS actual_qty,\n"
               "       ROUND(AVG(forecast_accuracy)::numeric, 3) AS avg_forecast_accuracy\n"
               "FROM analytics_marts.fct_plan_vs_actual\nGROUP BY plan_month ORDER BY plan_month",
        "viz": {"graph.dimensions": ["plan_month"], "graph.metrics": ["planned_qty", "actual_qty"]},
        "pos": (12, 0, 12, 8),
    },
    {
        "name": "Inventory health",
        "description": "Materials below safety stock and Days of Inventory by plant.",
        "display": "table",
        "sql": "SELECT i.plant_id, i.material_id, m.material_description, i.stock_qty, i.safety_stock_qty,\n"
               "       i.days_of_inventory, i.below_safety_stock\n"
               "FROM analytics_marts.fct_inventory_position i\n"
               "JOIN analytics_marts.dim_material m USING (material_plant_key)\n"
               "ORDER BY i.below_safety_stock DESC, i.days_of_inventory",
        "viz": {},
        "pos": (0, 8, 24, 8),
    },
]


def login():
    props = requests.get(f"{MB}/session/properties").json()
    if props.get("setup-token") and not props.get("has-user-setup"):
        r = requests.post(f"{MB}/setup", json={
            "token": props["setup-token"],
            "user": {"email": EMAIL, "password": PASSWORD, "first_name": "Demo", "last_name": "Admin",
                     "site_name": "Supply Chain BI"},
            "prefs": {"site_name": "Supply Chain BI", "allow_tracking": False}})
        r.raise_for_status()
        print("metabase: admin user created")
    r = S.post(f"{MB}/session", json={"username": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    S.headers["X-Metabase-Session"] = r.json()["id"]


def remove_samples():
    """Drop Metabase's bundled sample database and example dashboard so the catalogue stays clean."""
    for d in S.get(f"{MB}/dashboard").json():
        if d["name"] != DASHBOARD:
            S.delete(f"{MB}/dashboard/{d['id']}")
    for db in S.get(f"{MB}/database").json()["data"]:
        if db.get("is_sample"):
            S.delete(f"{MB}/database/{db['id']}")


def database_id() -> int:
    for db in S.get(f"{MB}/database").json()["data"]:
        if db["name"] == DB_NAME:
            return db["id"]
    r = S.post(f"{MB}/database", json={"engine": "postgres", "name": DB_NAME, "details": {
        "host": "openmetadata_postgresql", "port": 5432, "dbname": "erp",
        "user": "erp_reader", "password": "erp_reader", "schema-filters-type": "inclusion",
        "schema-filters-patterns": "analytics_marts"}})
    r.raise_for_status()
    db_id = r.json()["id"]
    for _ in range(30):  # wait for the first schema sync
        if S.get(f"{MB}/database/{db_id}/metadata").json().get("tables"):
            break
        time.sleep(2)
    print(f"metabase: connected '{DB_NAME}'")
    return db_id


def upsert_cards(db_id: int) -> list[tuple[int, tuple]]:
    existing = {c["name"]: c["id"] for c in S.get(f"{MB}/card").json()}
    out = []
    for q in QUESTIONS:
        body = {"name": q["name"], "description": q["description"], "display": q["display"],
                "dataset_query": {"type": "native", "database": db_id, "native": {"query": q["sql"]}},
                "visualization_settings": q["viz"]}
        if q["name"] in existing:
            cid = existing[q["name"]]
            S.put(f"{MB}/card/{cid}", json=body).raise_for_status()
        else:
            r = S.post(f"{MB}/card", json=body)
            r.raise_for_status()
            cid = r.json()["id"]
        out.append((cid, q["pos"]))
    print(f"metabase: {len(out)} questions")
    return out


def upsert_dashboard(cards):
    dash = next((d for d in S.get(f"{MB}/dashboard").json() if d["name"] == DASHBOARD), None)
    if not dash:
        r = S.post(f"{MB}/dashboard", json={
            "name": DASHBOARD,
            "description": "Monthly OTIF by plant, Plan vs Actual and inventory health. Used in the monthly S&OP review."})
        r.raise_for_status()
        dash = r.json()
    dashcards = [{"id": -(i + 1), "card_id": cid, "col": c, "row": r, "size_x": w, "size_y": h}
                 for i, (cid, (c, r, w, h)) in enumerate(cards)]
    S.put(f"{MB}/dashboard/{dash['id']}", json={"dashcards": dashcards}).raise_for_status()
    print(f"metabase: dashboard '{DASHBOARD}' (id {dash['id']}) -> http://localhost:3000/dashboard/{dash['id']}")


if __name__ == "__main__":
    login()
    remove_samples()
    upsert_dashboard(upsert_cards(database_id()))
