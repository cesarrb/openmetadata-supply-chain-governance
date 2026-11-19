"""Static checks on governance-as-code, run in CI on every pull request (no OpenMetadata needed).

Catches broken references before they reach the catalogue: an owner team that does not exist,
a glossary term with a typo, a contract column that is not in the model, and so on.
If dbt/target/catalog.json exists (after `dbt docs generate`), columns are checked against it.

Usage:  uv run python scripts/validate_governance.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOV = yaml.safe_load((ROOT / "governance/governance.yaml").read_text())
DQ = yaml.safe_load((ROOT / "governance/data_quality.yaml").read_text())
CON = yaml.safe_load((ROOT / "governance/contracts.yaml").read_text())
errors: list[str] = []


def check(cond: bool, msg: str):
    if not cond:
        errors.append(msg)


teams = {t["name"] for t in GOV["teams"]}
domains = {d["name"] for d in GOV["domains"]}
terms = {t["name"] for t in GOV["glossary"]["terms"]}
tags = {"Tier.Tier1", "Tier.Tier2", "Tier.Tier3", "Tier.Tier4", "Tier.Tier5", "PII.Sensitive", "PII.NonSensitive"}
tags |= {f"{c['name']}.{t['name']}" for c in GOV["classifications"] for t in c["tags"]}
roles = {r["name"] for r in GOV.get("roles", [])}
policies = {p["name"] for p in GOV.get("policies", [])} | {"DataConsumerPolicy", "DataStewardPolicy"}

# Columns per "schema.table": from the dbt catalog when available (models + sources).
catalog_cols: dict[str, set[str]] = {}
cat_file = ROOT / "dbt/target/catalog.json"
if cat_file.exists():
    cat = json.loads(cat_file.read_text())
    for node in list(cat["nodes"].values()) + list(cat["sources"].values()):
        m = node["metadata"]
        catalog_cols[f"{m['schema']}.{m['name']}"] = {c.lower() for c in node["columns"]}


def check_table(key: str, where: str):
    if catalog_cols:
        check(key in catalog_cols, f"{where}: table '{key}' not found in dbt catalog")


def check_column(key: str, col: str, where: str):
    if catalog_cols and key in catalog_cols:
        check(col in catalog_cols[key], f"{where}: column '{key}.{col}' not found")


# Glossary
for t in GOV["glossary"]["terms"]:
    for r in t.get("related", []):
        check(r in terms, f"glossary {t['name']}: related term '{r}' does not exist")
    check(bool(t.get("description", "").strip()), f"glossary {t['name']}: missing description")
check(GOV["glossary"]["owner"] in teams, "glossary owner team unknown")
check(GOV["glossary"]["reviewer"] in teams, "glossary reviewer team unknown")

# Domains and data products
for d in GOV["domains"]:
    check(d["owner"] in teams, f"domain {d['name']}: owner '{d['owner']}' unknown")
for dp in GOV["data_products"]:
    check(dp["domain"] in domains, f"data product {dp['name']}: domain unknown")
    for a in dp["assets"]:
        check(a in GOV["assets"], f"data product {dp['name']}: asset '{a}' is not governed")

# Table assignments
for key, a in GOV["assets"].items():
    where = f"asset {key}"
    check_table(key, where)
    check(a["owner"] in teams, f"{where}: owner '{a['owner']}' unknown")
    check(a["domain"] in domains, f"{where}: domain '{a['domain']}' unknown")
    check(f"Tier.{a['tier']}" in tags, f"{where}: tier '{a['tier']}' unknown")
    check(f"Confidentiality.{a['confidentiality']}" in tags, f"{where}: confidentiality unknown")
    for g in a.get("glossary", []):
        check(g in terms, f"{where}: glossary term '{g}' does not exist")
    if a.get("certified"):  # certification criteria from docs/GOVERNANCE_MODEL.md section 5
        check(a["tier"] == "Tier1", f"{where}: only Tier 1 assets can be certified")
        check(bool(a.get("glossary")), f"{where}: certified asset must link a glossary term")
        check(key in DQ["tests"], f"{where}: certified asset must have data-quality tests")
        check(key in CON["contracts"], f"{where}: certified asset must have a data contract")

# Column assignments
for key, c in GOV["columns"].items():
    tkey, col = key.rsplit(".", 1)
    check_column(tkey, col, f"column {key}")
    for t in c.get("tags", []):
        check(t in tags, f"column {key}: tag '{t}' unknown")
    for g in c.get("glossary", []):
        check(g in terms, f"column {key}: glossary term '{g}' does not exist")

# Data quality
for key, tests in DQ["tests"].items():
    check_table(key, f"quality {key}")
    names = [t["name"] for t in tests]
    check(len(names) == len(set(names)), f"quality {key}: duplicate test names")
    for t in tests:
        check(bool(t.get("why")), f"quality {t['name']}: missing business rationale ('why')")
        if t.get("column"):
            check_column(key, t["column"], f"quality {t['name']}")

# Contracts
for key, c in CON["contracts"].items():
    check(GOV["assets"].get(key, {}).get("certified", False), f"contract {key}: table is not certified")
    for col in c["columns"]:
        check_column(key, col, f"contract {key}")
check(CON["defaults"]["owner"] in teams, "contracts: default owner unknown")
check(CON["defaults"]["reviewer"] in teams, "contracts: default reviewer unknown")

# Access control
for r in GOV.get("roles", []):
    for p in r["policies"]:
        check(p in policies, f"role {r['name']}: policy '{p}' unknown")
for u in GOV.get("demo_users", []):
    check(u["team"] in teams, f"user {u['name']}: team unknown")
    check(u["role"] in roles, f"user {u['name']}: role unknown")

# dbt model metadata must mirror governance.yaml (the dbt docs demo shows it; drift would mislead)
display = {t.get("displayName", t["name"]): t["name"] for t in GOV["glossary"]["terms"]}
marts = yaml.safe_load((ROOT / "dbt/models/marts/_marts.yml").read_text())["models"]
for mdl in marts:
    key, where = f"analytics_marts.{mdl['name']}", f"dbt meta {mdl['name']}"
    a, cfg = GOV["assets"].get(key), mdl.get("config", {})
    meta = cfg.get("meta", {})
    if a is None:
        errors.append(f"{where}: model is not governed in governance.yaml")
        continue
    check(meta.get("owner_team") == a["owner"], f"{where}: owner_team differs from governance.yaml")
    check(meta.get("tier") == a["tier"], f"{where}: tier differs from governance.yaml")
    check(meta.get("confidentiality") == a["confidentiality"], f"{where}: confidentiality differs")
    dbt_terms = sorted(display.get(t.strip(), "?" + t.strip()) for t in meta.get("glossary_terms", "").split(", ") if t.strip())
    check(dbt_terms == sorted(a.get("glossary", [])), f"{where}: glossary terms {dbt_terms} differ from governance.yaml")
    certified = bool(a.get("certified"))
    check((meta.get("certification") == "Gold") == certified, f"{where}: certification differs from governance.yaml")
    check(cfg.get("contract", {}).get("enforced", False) == certified,
          f"{where}: certified models must enforce a dbt model contract (and only those)")

# Dashboard
d = GOV["dashboard"]
check(d["owner"] in teams and d["domain"] in domains, "dashboard: owner or domain unknown")
for g in d.get("glossary", []):
    check(g in terms, f"dashboard: glossary term '{g}' does not exist")

scope = "with dbt catalog" if catalog_cols else "references only (no dbt catalog)"
if errors:
    print(f"Governance validation FAILED ({len(errors)} issues, {scope}):")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"Governance validation passed ({scope}): {len(GOV['assets'])} assets, {len(GOV['columns'])} columns, "
      f"{len(terms)} terms, {sum(len(v) for v in DQ['tests'].values())} quality tests, {len(CON['contracts'])} contracts.")
