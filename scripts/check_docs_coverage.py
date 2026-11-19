"""Documentation gate, run in CI after `dbt docs generate`.

Every source table, model, column (as built in the warehouse), project macro and singular test
must have a description. A new column without one fails the pull request, so the live dbt docs
and the OpenMetadata catalogue never drift back to "not currently documented".

Usage:  uv run python scripts/check_docs_coverage.py
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "dbt/target"
manifest = json.loads((TARGET / "manifest.json").read_text())
catalog = json.loads((TARGET / "catalog.json").read_text())
project = manifest["metadata"]["project_name"]

missing: list[str] = []
counts = {"tables": [0, 0], "columns": [0, 0], "macros": [0, 0], "tests": [0, 0]}


def tally(kind: str, ok: bool, label: str):
    counts[kind][1] += 1
    if ok:
        counts[kind][0] += 1
    else:
        missing.append(f"{kind[:-1]:6s} {label}")


def described(text: str | None) -> bool:
    return bool((text or "").strip())


nodes = [(k, v, catalog["nodes"]) for k, v in manifest["nodes"].items() if v["resource_type"] == "model"]
nodes += [(k, v, catalog["sources"]) for k, v in manifest["sources"].items()]
for uid, node, cat in nodes:
    label = node.get("identifier") or node["name"]
    tally("tables", described(node["description"]), f"{node['schema']}.{label}")
    # Columns as they really exist in the warehouse (catalog), not only those listed in YAML.
    for col in cat.get(uid, {}).get("columns", {}):
        doc = node["columns"].get(col.lower(), {}).get("description")
        tally("columns", described(doc), f"{node['schema']}.{label}.{col}")

for m in manifest["macros"].values():
    if m["package_name"] == project:
        tally("macros", described(m["description"]), m["name"])

for t in manifest["nodes"].values():
    if t["resource_type"] == "test" and not t.get("test_metadata"):  # singular tests
        tally("tests", described(t["description"]), t["name"])

summary = ", ".join(f"{k} {ok}/{n}" for k, (ok, n) in counts.items())
if missing:
    print(f"Documentation coverage FAILED ({summary}). Missing descriptions:")
    for m in missing:
        print("  -", m)
    sys.exit(1)
print(f"Documentation coverage 100 %: {summary}.")
