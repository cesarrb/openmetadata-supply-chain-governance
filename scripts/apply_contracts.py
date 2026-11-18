"""Create/update data contracts from governance/contracts.yaml, validate them and export ODCS YAML.

Usage:  uv run python scripts/apply_contracts.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
OM = "http://localhost:8585/api/v1"
PREFIX = "erp_postgres.erp."
S = requests.Session()
S.headers.update({"Authorization": f"Bearer {(ROOT / '.om_token').read_text().strip()}",
                  "Content-Type": "application/json"})
CFG = yaml.safe_load((ROOT / "governance" / "contracts.yaml").read_text())
OUT = ROOT / "contracts"


def req(method, path, **kw):
    r = S.request(method, OM + path, **kw)
    if r.status_code >= 400:
        sys.exit(f"{method} {path} -> {r.status_code}: {r.text[:600]}")
    return r


def team(name):
    t = req("GET", f"/teams/name/{name}").json()
    return {"id": t["id"], "type": "team"}


def test_cases_for(table_fqn: str) -> list[dict]:
    """All test cases (OpenMetadata-native and dbt) attached to the table or its columns."""
    link = f"<#E::table::{table_fqn}>"
    r = req("GET", "/dataQuality/testCases", params={"entityLink": link, "includeAllTests": "true", "limit": 100})
    return [{"id": t["id"], "type": "testCase"} for t in r.json()["data"]]


def apply():
    d = CFG["defaults"]
    OUT.mkdir(exist_ok=True)
    created = []
    for key, c in CFG["contracts"].items():
        fqn = PREFIX + key
        table = req("GET", f"/tables/name/{fqn}", params={"fields": "columns,tags"}).json()
        cols = [col for col in table["columns"] if col["name"] in c["columns"]]
        missing = set(c["columns"]) - {col["name"] for col in cols}
        if missing:
            sys.exit(f"{key}: contract columns not in table: {missing}")
        conf = next((t["tagFQN"] for t in table.get("tags", []) if t["tagFQN"].startswith("Confidentiality.")), None)
        tests = test_cases_for(fqn)
        name = f"{table['name']}_contract"
        body = {
            "name": name, "displayName": f"{table['name']} contract",
            "description": c["description"].strip(), "entityStatus": d["status"],
            "entity": {"id": table["id"], "type": "table"},
            "schema": [{"name": col["name"], "dataType": col["dataType"],
                        "description": col.get("description", "")} for col in cols],
            "semantics": [{**rule, "enabled": True} for rule in d["semantics"]],
            "qualityExpectations": tests,
            "owners": [team(d["owner"])], "reviewers": [team(d["reviewer"])],
            "termsOfUse": c.get("termsOfUse", ""),
            "sla": d["sla"],
            "security": {"dataClassification": conf} if conf else None,
        }
        body = {k: v for k, v in body.items() if v is not None}
        old = S.get(f"{OM}/dataContracts/entity", params={"entityId": table["id"], "entityType": "table"})
        if old.status_code == 200 and old.json().get("name") != name:  # one contract per table
            req("DELETE", f"/dataContracts/{old.json()['id']}", params={"hardDelete": "true"})
        contract = req("PUT", "/dataContracts", data=json.dumps(body)).json()
        (OUT / f"{table['name']}.odcs.yaml").write_text(req("GET", f"/dataContracts/{contract['id']}/odcs/yaml").text)
        created.append((name, contract["id"], len(cols), len(tests)))
    # Quality checks run as an Airflow pipeline that OpenMetadata deploys on save; give the
    # scheduler time to load it, then validate (schema + semantics + quality) and wait for the result.
    time.sleep(30)
    for name, cid, ncols, ntests in created:
        print(f"  {name:32s} columns={ncols:2d} tests={ntests:2d} {validate(cid)}")
    print(f"contracts: {len(created)} (ODCS exports in contracts/)")


def validate(cid: str, attempts: int = 3) -> str:
    for _ in range(attempts):
        req("POST", f"/dataContracts/{cid}/validate")
        for _ in range(30):
            time.sleep(5)
            r = req("GET", f"/dataContracts/{cid}/results/latest").json()
            if r.get("contractExecutionStatus") not in ("Running", "Queued"):
                break
        if r.get("contractExecutionStatus") != "Aborted":
            break
        time.sleep(20)
    part = lambda k: f"{r.get(k, {}).get('passed', 0)}/{r.get(k, {}).get('total', 0)}"
    return (f"-> {r.get('contractExecutionStatus')} (schema {part('schemaValidation')}, "
            f"semantics {part('semanticsValidation')}, quality {part('qualityValidation')})")


if __name__ == "__main__":
    apply()
