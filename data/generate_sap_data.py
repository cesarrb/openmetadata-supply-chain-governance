"""Generate a synthetic, SAP-style supply-chain dataset and load it into Postgres.

All data is fictitious and generated from a fixed seed, so every run produces
the same tables. Table and column names follow SAP ECC conventions (MARA, MARC,
LFA1, KNA1, EKKO/EKPO, VBAK/VBAP, LIKP/LIPS, MARD) so the catalogue looks like
a real ERP extract, plus a monthly demand plan (IBP/APO-style).

A few data-quality defects are injected on purpose (missing delivery dates,
negative stock, an orphan purchase-order line) so the quality tests have
something real to catch.

Usage:  uv run python data/generate_sap_data.py
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import random

import psycopg2
from psycopg2.extras import execute_values
import yaml

SEED = 42
rng = random.Random(SEED)

DSN = os.environ.get(
    "ERP_DSN", "host=localhost port=5432 dbname=erp user=erp_admin password=erp_admin"
)

PLANTS = {"CH10": "Bulle (CH)", "DE20": "Biberach (DE)", "FR30": "Colmar (FR)"}
START = dt.date(2026, 1, 1)
END = dt.date(2026, 10, 31)

MATERIAL_GROUPS = {
    "HYD": ("Hydraulics", ["Hydraulic pump", "Hydraulic cylinder", "Valve block", "Hose assembly"]),
    "ELE": ("Electrical", ["Control unit", "Wiring harness", "Sensor", "Display module"]),
    "STR": ("Structural", ["Boom section", "Slewing ring", "Counterweight", "Chassis frame"]),
    "DRV": ("Drivetrain", ["Gearbox", "Axle", "Final drive", "Track roller"]),
    "CON": ("Consumables", ["Filter kit", "Seal kit", "Lubricant 20L", "Bolt set"]),
}
COUNTRIES = ["CH", "DE", "FR", "IT", "AT", "PL", "CZ", "ES", "NL"]
CITIES = {"CH": "Zurich", "DE": "Stuttgart", "FR": "Lyon", "IT": "Milan", "AT": "Linz",
          "PL": "Wroclaw", "CZ": "Brno", "ES": "Zaragoza", "NL": "Eindhoven"}
FIRST = ["Anna", "Marc", "Lucia", "Jonas", "Elena", "Pierre", "Sofia", "Lukas", "Chiara", "Tomas"]
LAST = ["Meier", "Dubois", "Rossi", "Novak", "Keller", "Garcia", "Bauer", "Martin", "Weber", "Moreau"]


def rand_date(a: dt.date, b: dt.date) -> dt.date:
    return a + dt.timedelta(days=rng.randint(0, (b - a).days))


def person() -> tuple[str, str]:
    f, l = rng.choice(FIRST), rng.choice(LAST)
    return f"{f} {l}", f"{f.lower()}.{l.lower()}@example.com"


def build():
    # --- Material master (MARA) and plant data (MARC) ---
    mara, marc = [], []
    n = 0
    for grp, (_, names) in MATERIAL_GROUPS.items():
        for name in names:
            for variant in ("A", "B", "C"):
                n += 1
                matnr = f"MAT-{100000 + n}"
                mtart = "ROH" if grp in ("CON",) else rng.choice(["HALB", "FERT", "ROH"])
                mara.append((matnr, f"{name} type {variant}", mtart, grp, "PC" if grp != "CON" else "SET",
                             round(rng.uniform(0.5, 900), 2), rng.choice([True, True, True, False])))
                for werks in PLANTS:
                    if rng.random() < 0.8:
                        marc.append((matnr, werks, f"MRP{rng.randint(1, 6):02d}",
                                     rng.randint(5, 80), rng.randint(5, 60),
                                     round(rng.uniform(20, 4000), 2)))

    # --- Vendor master (LFA1) and customer master (KNA1): contain PII ---
    lfa1 = []
    for i in range(1, 21):
        land = rng.choice(COUNTRIES)
        contact, email = person()
        lfa1.append((f"V{200000 + i}", f"Supplier {chr(64 + i)} {rng.choice(['GmbH', 'SA', 'AG', 'Srl', 's.r.o.'])}",
                     land, CITIES[land], contact, email, f"+{rng.randint(30, 49)} {rng.randint(100, 999)} {rng.randint(1000000, 9999999)}",
                     f"{land}{rng.randint(10**9, 10**10 - 1)}"))
    kna1 = []
    for i in range(1, 31):
        land = rng.choice(COUNTRIES)
        contact, email = person()
        kna1.append((f"C{300000 + i}", f"Customer {i:02d} {rng.choice(['Construction', 'Mining', 'Rental', 'Logistics'])}",
                     land, CITIES[land], contact, email, rng.choice(["A", "B", "C"])))

    marc_keys = [(m[0], m[1]) for m in marc]
    price = {m[0]: m[5] for m in marc}

    # --- Purchase orders (EKKO header / EKPO item) ---
    ekko, ekpo = [], []
    for i in range(1, 401):
        ebeln = f"45{i:08d}"
        lifnr = rng.choice(lfa1)[0]
        bedat = rand_date(START, END - dt.timedelta(days=30))
        ekko.append((ebeln, lifnr, bedat, rng.choice(["NB", "NB", "UB"]), "EUR" if rng.random() < .7 else "CHF"))
        for pos in range(1, rng.randint(2, 5)):
            matnr, werks = rng.choice(marc_keys)
            eindt = bedat + dt.timedelta(days=rng.randint(7, 60))
            ekpo.append((ebeln, pos * 10, matnr, werks, rng.randint(1, 200),
                         round(price[matnr] * rng.uniform(.9, 1.1), 2), eindt))
    # injected defect: orphan PO line pointing to a material that is not in MARA
    ekpo.append((ekko[0][0], 990, "MAT-999999", "CH10", 5, 10.0, ekko[0][2] + dt.timedelta(days=14)))

    # --- Sales orders (VBAK / VBAP) and outbound deliveries (LIKP / LIPS) ---
    vbak, vbap, likp, lips = [], [], [], []
    dlv_n = 0
    for i in range(1, 1201):
        vbeln = f"10{i:08d}"
        kunnr = rng.choice(kna1)[0]
        # Orders stop on 31 Aug, so every requested date falls by 30 Sep and every line is shipped
        # by END: no partial last month and no survivorship bias (late deliveries silently missing).
        erdat = rand_date(START, dt.date(2026, 8, 31))
        vdatu = erdat + dt.timedelta(days=rng.randint(5, 30))  # requested delivery date
        auart = rng.choice(["OR", "OR", "OR", "RE"])
        vbak.append((vbeln, kunnr, erdat, vdatu, auart))
        for pos in range(1, rng.randint(2, 4)):
            matnr, werks = rng.choice(marc_keys)
            qty = rng.randint(1, 40)
            vbap.append((vbeln, pos * 10, matnr, werks, qty, round(price[matnr] * 1.35, 2)))
            if auart != "OR":
                continue  # returns (RE) are not shipped outbound
            # Delivery behaviour: ~78 % on time, ~88 % in full -> realistic OTIF ~70 %
            dlv_n += 1
            dlv = f"80{dlv_n:08d}"
            late = rng.random() > 0.78
            actual = vdatu + dt.timedelta(days=rng.randint(1, 12) if late else -rng.randint(0, 3))
            delivered = qty if rng.random() < 0.88 else max(0, qty - rng.randint(1, qty))
            if rng.random() < 0.01:
                actual = None  # injected defect: goods issue posted without date
            likp.append((dlv, vbeln, werks, actual))
            lips.append((dlv, 10, vbeln, pos * 10, matnr, delivered))

    # --- Stock (MARD) ---
    mard = []
    for matnr, werks in marc_keys:
        for lgort in ("0001", "0002"):
            labst = int(rng.expovariate(1 / 70))  # skewed: most items healthy, some below safety stock
            if rng.random() < 0.01:
                labst = -rng.randint(1, 20)  # injected defect: negative unrestricted stock
            mard.append((matnr, werks, lgort, labst))

    # --- Demand plan (IBP/APO style, monthly) ---
    plan = []
    actual_by = {}
    so_date = {h[0]: h[2] for h in vbak}
    so_type = {h[0]: h[4] for h in vbak}
    for v in vbap:
        if so_type[v[0]] != "OR":
            continue  # the plan forecasts customer demand, i.e. standard orders only
        m = so_date[v[0]].replace(day=1)
        actual_by[(v[2], v[3], m)] = actual_by.get((v[2], v[3], m), 0) + v[4]
    months = sorted({k[2] for k in actual_by})
    for matnr, werks in marc_keys:
        for m in months:
            a = actual_by.get((matnr, werks, m), 0)
            # Unbiased forecast error (about 30 % on average at material x plant x month, a realistic
            # level for spare parts); small plans where no order arrived.
            planned = max(0, round(a * rng.uniform(.5, 1.5) + rng.randint(-3, 3))) if a else rng.choice([0, 0, 0, 1, 2])
            plan.append((matnr, werks, m, planned, "V" + m.strftime("%Y%m")))

    return dict(mara=mara, marc=marc, lfa1=lfa1, kna1=kna1, ekko=ekko, ekpo=ekpo,
                vbak=vbak, vbap=vbap, likp=likp, lips=lips, mard=mard, demand_plan=plan)


DDL = """
DROP SCHEMA IF EXISTS sap_erp CASCADE;
CREATE SCHEMA sap_erp;

CREATE TABLE sap_erp.mara (matnr text PRIMARY KEY, maktx text, mtart text, matkl text, meins text, brgew numeric(10,2), is_active boolean);
CREATE TABLE sap_erp.marc (matnr text, werks text, dispo text, plifz int, eisbe int, stprs numeric(12,2), PRIMARY KEY (matnr, werks));
CREATE TABLE sap_erp.lfa1 (lifnr text PRIMARY KEY, name1 text, land1 text, ort01 text, contact_name text, contact_email text, contact_phone text, stceg text);
CREATE TABLE sap_erp.kna1 (kunnr text PRIMARY KEY, name1 text, land1 text, ort01 text, contact_name text, contact_email text, abc_class text);
CREATE TABLE sap_erp.ekko (ebeln text PRIMARY KEY, lifnr text, bedat date, bsart text, waers text);
CREATE TABLE sap_erp.ekpo (ebeln text, ebelp int, matnr text, werks text, menge int, netpr numeric(12,2), eindt date, PRIMARY KEY (ebeln, ebelp));
CREATE TABLE sap_erp.vbak (vbeln text PRIMARY KEY, kunnr text, erdat date, vdatu date, auart text);
CREATE TABLE sap_erp.vbap (vbeln text, posnr int, matnr text, werks text, kwmeng int, netpr numeric(12,2), PRIMARY KEY (vbeln, posnr));
CREATE TABLE sap_erp.likp (vbeln text PRIMARY KEY, vgbel text, werks text, wadat_ist date);
CREATE TABLE sap_erp.lips (vbeln text, posnr int, vgbel text, vgpos int, matnr text, lfimg int, PRIMARY KEY (vbeln, posnr));
CREATE TABLE sap_erp.mard (matnr text, werks text, lgort text, labst int, PRIMARY KEY (matnr, werks, lgort));
CREATE TABLE sap_erp.demand_plan (matnr text, werks text, plan_month date, planned_qty int, plan_version text, PRIMARY KEY (matnr, werks, plan_month));
"""

# Descriptions live in one place, the dbt sources file, and are written here as Postgres comments
# (which OpenMetadata ingests). dbt docs and the catalogue therefore show the same text.
SOURCES_YML = pathlib.Path(__file__).resolve().parents[1] / "dbt/models/staging/_sources.yml"


def load_comments() -> dict[str, tuple[str, dict[str, str]]]:
    src = yaml.safe_load(SOURCES_YML.read_text())["sources"][0]
    return {t["name"]: (t["description"].strip(), {c["name"]: c["description"].strip() for c in t.get("columns", [])})
            for t in src["tables"]}


def main():
    data = build()
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for table, rows in data.items():
            execute_values(cur, f"INSERT INTO sap_erp.{table} VALUES %s", rows)
            print(f"sap_erp.{table:12s} {len(rows):6d} rows")
        cur.execute("COMMENT ON SCHEMA sap_erp IS %s", (yaml.safe_load(SOURCES_YML.read_text())["sources"][0]["description"].strip(),))
        for table, (tdesc, cols) in load_comments().items():
            cur.execute(f"COMMENT ON TABLE sap_erp.{table} IS %s", (tdesc,))
            for col, cdesc in cols.items():
                cur.execute(f"COMMENT ON COLUMN sap_erp.{table}.{col} IS %s", (cdesc,))
        cur.execute("GRANT USAGE ON SCHEMA sap_erp TO erp_reader; GRANT SELECT ON ALL TABLES IN SCHEMA sap_erp TO erp_reader;")


if __name__ == "__main__":
    main()
