"""Apply governance/governance.yaml to OpenMetadata through its REST API.

Idempotent: every call is a create-or-update (PUT) or a JSON Patch, so the script can be
re-run after any change to the YAML and the catalogue converges to what the file says.

Usage:  uv run python scripts/apply_governance.py
"""
from __future__ import annotations

import base64
import os
import pathlib
import secrets
import sys

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
OM = "http://localhost:8585/api/v1"
SERVICE, DB = "erp_postgres", "erp"
TOKEN = (ROOT / ".om_token").read_text().strip()
S = requests.Session()
S.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
CFG = yaml.safe_load((ROOT / "governance" / "governance.yaml").read_text())


def call(method: str, path: str, body=None, patch=False, ok404=False):
    headers = {"Content-Type": "application/json-patch+json"} if patch else {}
    r = S.request(method, OM + path, json=body, headers=headers)
    if ok404 and r.status_code == 404:
        return None
    if r.status_code >= 400:
        sys.exit(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def get(path: str):
    return call("GET", path, ok404=True)


def table_fqn(key: str) -> str:
    return f"{SERVICE}.{DB}.{key}"


def team_ref(name):
    t = get(f"/teams/name/{name}")
    return {"id": t["id"], "type": "team"}


def tag_label(fqn: str, source="Classification") -> dict:
    return {"tagFQN": fqn, "source": source, "labelType": "Manual", "state": "Confirmed"}


def term_fqn(term: str) -> str:
    return f"{CFG['glossary']['name']}.{term}"


# --------------------------------------------------------------------------- teams
def apply_teams():
    for t in CFG["teams"]:
        call("PUT", "/teams", {"name": t["name"], "displayName": t["displayName"],
                               "description": t["description"], "teamType": "Group"})
    print(f"teams: {len(CFG['teams'])}")


# ------------------------------------------------------------------- classification
def apply_classifications():
    n = 0
    for c in CFG["classifications"]:
        call("PUT", "/classifications", {"name": c["name"], "description": c["description"],
                                         "mutuallyExclusive": c.get("mutuallyExclusive", False)})
        for t in c["tags"]:
            call("PUT", "/tags", {"name": t["name"], "description": t["description"], "classification": c["name"]})
            n += 1
    print(f"classification tags: {n}")


# ------------------------------------------------------------------------- domains
def apply_domains():
    for d in CFG["domains"]:
        call("PUT", "/domains", {"name": d["name"], "displayName": d["displayName"],
                                 "domainType": d["domainType"], "description": d["description"],
                                 "owners": [team_ref(d["owner"])]})
    print(f"domains: {len(CFG['domains'])}")


# ------------------------------------------------------------------------ glossary
def apply_glossary():
    g = CFG["glossary"]
    call("PUT", "/glossaries", {"name": g["name"], "displayName": g["displayName"], "description": g["description"],
                                "owners": [team_ref(g["owner"])], "reviewers": [team_ref(g["reviewer"])]})
    # first pass: create terms; second pass: add related terms (they must exist first)
    for t in g["terms"]:
        call("PUT", "/glossaryTerms", {"glossary": g["name"], "name": t["name"], "displayName": t["displayName"],
                                       "description": t["description"].strip(), "synonyms": t.get("synonyms", [])})
    for t in g["terms"]:
        if t.get("related"):
            call("PUT", "/glossaryTerms", {"glossary": g["name"], "name": t["name"], "displayName": t["displayName"],
                                           "description": t["description"].strip(), "synonyms": t.get("synonyms", []),
                                           "relatedTerms": [term_fqn(r) for r in t["related"]]})
    # approve terms that are still in Draft (the reviewer team approves them in a real workflow)
    for t in g["terms"]:
        term = get(f"/glossaryTerms/name/{term_fqn(t['name'])}")
        if term and term.get("entityStatus", term.get("status")) not in ("Approved",):
            field = "entityStatus" if "entityStatus" in term else "status"
            S.patch(f"{OM}/glossaryTerms/{term['id']}", json=[{"op": "add", "path": f"/{field}", "value": "Approved"}],
                    headers={"Content-Type": "application/json-patch+json"})
    print(f"glossary terms: {len(g['terms'])}")


# -------------------------------------------------------------------------- assets
def patch_entity(kind: str, ent: dict, ops: list):
    if ops:
        call("PATCH", f"/{kind}/{ent['id']}", ops, patch=True)


def apply_assets():
    for key, a in CFG["assets"].items():
        t = get(f"/tables/name/{table_fqn(key)}?fields=owners,tags,domains")
        if not t:
            print(f"  ! table not found: {key}")
            continue
        manual = [x for x in t.get("tags", []) if not x["tagFQN"].startswith(("Tier.", "Confidentiality.", CFG["glossary"]["name"]))]
        labels = manual + [tag_label(f"Tier.{a['tier']}"), tag_label(f"Confidentiality.{a['confidentiality']}")]
        labels += [tag_label(term_fqn(g), "Glossary") for g in a.get("glossary", [])]
        dom = get(f"/domains/name/{a['domain']}")
        ops = [{"op": "add", "path": "/owners", "value": [team_ref(a["owner"])]},
               {"op": "add", "path": "/tags", "value": labels},
               {"op": "add", "path": "/domains", "value": [{"id": dom["id"], "type": "domain"}]}]
        patch_entity("tables", t, ops)
        if a.get("certified"):
            S.patch(f"{OM}/tables/{t['id']}", headers={"Content-Type": "application/json-patch+json"},
                    json=[{"op": "add", "path": "/certification", "value": {"tagLabel": tag_label("Certification.Gold")}}])
    print(f"tables governed: {len(CFG['assets'])}")


def apply_columns():
    by_table: dict[str, dict] = {}
    for key, c in CFG["columns"].items():
        tkey, col = key.rsplit(".", 1)
        by_table.setdefault(tkey, {})[col] = c
    for tkey, cols in by_table.items():
        t = get(f"/tables/name/{table_fqn(tkey)}?fields=columns,tags")
        ops = []
        for i, column in enumerate(t["columns"]):
            if column["name"] not in cols:
                continue
            c = cols[column["name"]]
            existing = [x for x in column.get("tags", []) if x.get("source") == "Classification"
                        and not (c.get("reject_auto") and x.get("labelType") == "Generated")]
            wanted = existing + [tag_label(x) for x in c.get("tags", []) if x not in {e["tagFQN"] for e in existing}]
            wanted += [tag_label(term_fqn(g), "Glossary") for g in c.get("glossary", [])]
            ops.append({"op": "add", "path": f"/columns/{i}/tags", "value": wanted})
        patch_entity("tables", t, ops)
    print(f"columns tagged: {len(CFG['columns'])}")


# --------------------------------------------------------------------- data product
def apply_data_products():
    for dp in CFG["data_products"]:
        call("PUT", "/dataProducts", {"name": dp["name"], "displayName": dp["displayName"],
                                      "description": dp["description"], "domains": [dp["domain"]],
                                      "owners": [team_ref(dp["owner"])]})
        assets = [{"id": get(f"/tables/name/{table_fqn(a)}")["id"], "type": "table"} for a in dp["assets"]]
        call("PUT", f"/dataProducts/{dp['name']}/assets/add", {"assets": assets})
    print(f"data products: {len(CFG['data_products'])}")


# ------------------------------------------------------------- dashboard + lineage
def apply_dashboard():
    d = CFG["dashboard"]
    for legacy in d.get("legacy_services", []):
        svc = get(f"/services/dashboardServices/name/{legacy}")
        if svc:
            call("DELETE", f"/services/dashboardServices/{svc['id']}?recursive=true&hardDelete=true")
            print(f"  removed legacy dashboard service {legacy}")
    found = call("GET", f"/dashboards?service={d['service']}&limit=100&fields=charts")["data"]
    dash = next((x for x in found if x.get("displayName") == d["displayName"]), None)
    if not dash:
        print(f"  ! dashboard '{d['displayName']}' not ingested yet (run ingestion/05_metabase.yaml)")
        return
    dom = get(f"/domains/name/{d['domain']}")
    tags = [tag_label(f"Tier.{d['tier']}")] + [tag_label(term_fqn(g), "Glossary") for g in d.get("glossary", [])]
    patch_entity("dashboards", dash, [
        {"op": "add", "path": "/owners", "value": [team_ref(d["owner"])]},
        {"op": "add", "path": "/tags", "value": tags},
        {"op": "add", "path": "/domains", "value": [{"id": dom["id"], "type": "domain"}]}])
    for ch in dash["charts"]:
        chart = get(f"/charts/{ch['id']}?fields=owners,domains")
        patch_entity("charts", chart, [
            {"op": "add", "path": "/owners", "value": [team_ref(d["owner"])]},
            {"op": "add", "path": "/domains", "value": [{"id": dom["id"], "type": "domain"}]}])
    if d.get("data_product"):
        call("PUT", f"/dataProducts/{d['data_product']}/assets/add",
             {"assets": [{"id": dash["id"], "type": "dashboard"}]})
    print(f"dashboard: {d['displayName']} ({len(dash['charts'])} Metabase charts) governed")


# ------------------------------------------------------------------ access control
def admin_headers() -> dict:
    """Creating users needs an admin principal (the ingestion bot is not one): log in as the local admin."""
    email = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
    pw = base64.b64encode(os.environ.get("OM_ADMIN_PASSWORD", "admin").encode()).decode()
    r = requests.post(f"{OM}/users/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def apply_access_control():
    for pol in CFG.get("policies", []):
        call("PUT", "/policies", {"name": pol["name"], "displayName": pol["displayName"],
                                  "description": pol["description"], "rules": pol["rules"]})
    for role in CFG.get("roles", []):
        call("PUT", "/roles", {"name": role["name"], "displayName": role["displayName"],
                               "description": role["description"], "policies": role["policies"]})
    for u in CFG.get("demo_users", []):
        existing = get(f"/users/name/{u['name']}?fields=teams,roles")
        team_id = get(f"/teams/name/{u['team']}")["id"]
        role_id = get(f"/roles/name/{u['role']}")["id"]
        if not existing:
            pw = secrets.token_urlsafe(12) + "A1!"  # never used: demo personas don't log in
            r = requests.post(f"{OM}/users", headers=admin_headers(), json={
                "name": u["name"], "displayName": u["displayName"], "email": f"{u['name']}@example.com",
                "teams": [team_id], "roles": [role_id],
                "createPasswordType": "ADMIN_CREATE", "password": pw, "confirmPassword": pw})
            if r.status_code >= 400:
                sys.exit(f"create user {u['name']}: {r.status_code} {r.text[:300]}")
        else:
            requests.patch(f"{OM}/users/{existing['id']}", headers={**admin_headers(),
                           "Content-Type": "application/json-patch+json"}, json=[
                {"op": "add", "path": "/teams", "value": [{"id": team_id, "type": "team"}]},
                {"op": "add", "path": "/roles", "value": [{"id": role_id, "type": "role"}]}]).raise_for_status()
    print(f"access control: {len(CFG.get('policies', []))} policy, {len(CFG.get('roles', []))} role, "
          f"{len(CFG.get('demo_users', []))} demo users")


if __name__ == "__main__":
    apply_teams()
    apply_classifications()
    apply_domains()
    apply_glossary()
    apply_assets()
    apply_columns()
    apply_data_products()
    apply_dashboard()
    apply_access_control()
    print("Governance applied.")
