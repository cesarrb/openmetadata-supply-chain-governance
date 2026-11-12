"""Create OpenMetadata data-quality test cases from governance/data_quality.yaml and run them.

Usage:  uv run python scripts/data_quality.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
OM = "http://localhost:8585/api/v1"
PREFIX = "erp_postgres.erp."
S = requests.Session()
S.headers.update({"Authorization": f"Bearer {(ROOT / '.om_token').read_text().strip()}"})
CFG = yaml.safe_load((ROOT / "governance" / "data_quality.yaml").read_text())

WORKFLOW = """
source:
  type: TestSuite
  serviceName: erp_postgres
  sourceConfig:
    config:
      type: TestSuite
      entityFullyQualifiedName: {fqn}
processor:
  type: orm-test-runner
  config: {{}}
sink:
  type: metadata-rest
  config: {{}}
workflowConfig:
  loggerLevel: INFO
  openMetadataServerConfig:
    hostPort: http://openmetadata_server:8585/api
    authProvider: openmetadata
    securityConfig:
      jwtToken: "${{OM_JWT}}"
"""


def create_tests():
    n = 0
    for table, tests in CFG["tests"].items():
        fqn = PREFIX + table
        for t in tests:
            link = f"<#E::table::{fqn}" + (f"::columns::{t['column']}>" if t.get("column") else ">")
            body = {"name": t["name"], "entityLink": link, "testDefinition": t["definition"],
                    "description": t["why"],
                    "parameterValues": [{"name": k, "value": str(v)} for k, v in t.get("params", {}).items()]}
            r = S.put(f"{OM}/dataQuality/testCases", json=body)
            if r.status_code >= 400:
                sys.exit(f"{t['name']}: {r.status_code} {r.text[:400]}")
            n += 1
    print(f"test cases defined: {n}")


def run_tests():
    tmp = ROOT / "logs"
    tmp.mkdir(exist_ok=True)
    for table in CFG["tests"]:
        cfg = tmp / "dq_workflow.yaml"
        cfg.write_text(WORKFLOW.format(fqn=PREFIX + table))
        out = subprocess.run([str(ROOT / "scripts/run_ingestion.sh"), str(cfg), "test"], capture_output=True, text=True)
        ok = "Workflow Success %" in out.stdout
        print(f"  ran tests on {table}: {'ok' if ok else 'CHECK LOG'}")
        if not ok:
            print(out.stdout[-1500:], out.stderr[-500:])
        cfg.unlink()


def summary():
    r = S.get(f"{OM}/dataQuality/testCases", params={"fields": "testCaseResult", "limit": 100}).json()
    rows = sorted((tc.get("testCaseResult", {}).get("testCaseStatus", "-"), tc["name"]) for tc in r["data"])
    for status, name in rows:
        print(f"  {status:8s} {name}")


if __name__ == "__main__":
    create_tests()
    run_tests()
    summary()
