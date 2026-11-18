"""Prove the access policy: ask OpenMetadata what each demo persona may do on each table.

Usage:  uv run python scripts/check_access.py
"""
import base64
import os

import requests

OM = "http://localhost:8585/api/v1"
PW = base64.b64encode(os.environ.get("OM_ADMIN_PASSWORD", "admin").encode()).decode()
TOKEN = requests.post(f"{OM}/users/login", json={"email": os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org"),
                                                 "password": PW}).json()["accessToken"]
H = {"Authorization": f"Bearer {TOKEN}"}
USERS = ["sc.analyst", "procurement.steward"]
TABLES = {"sap_erp.lfa1": "vendor master (Restricted, owner Procurement)",
          "sap_erp.kna1": "customer master (Restricted, owner Sales Ops)",
          "analytics_marts.fct_otif": "OTIF fact (Internal)"}
OPS = ["ViewBasic", "ViewSampleData", "ViewDataProfile"]

print(f"{'table':28s} {'user':22s} " + " ".join(f"{o:15s}" for o in OPS))
for t, label in TABLES.items():
    for u in USERS:
        r = requests.get(f"{OM}/permissions/table/name/erp_postgres.erp.{t}", params={"user": u}, headers=H)
        r.raise_for_status()
        acc = {p["operation"]: p["access"] for p in r.json()["permissions"]}
        print(f"{t:28s} {u:22s} " + " ".join(f"{acc.get(o, '?'):15s}" for o in OPS))
