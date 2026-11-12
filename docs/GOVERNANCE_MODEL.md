# Data Governance Operating Model

How the catalogue in this repository is meant to be run in a manufacturing company with an
SAP backbone. The model is deliberately light: federated ownership, a small central office,
and governance rules kept as code so every change is reviewed and auditable.

## 1. Principles

1. **The business owns the data, IT runs the platform.** Every certified asset has a business
   owner team; the Data Governance Office (DGO) owns standards, not datasets.
2. **One definition per KPI.** OTIF, Plan vs Actual or Days of Inventory are defined once in the
   glossary and linked to the exact column that computes them.
3. **Classify at the source, minimise downstream.** Personal data is tagged in the raw ERP layer
   and is *not* propagated to the analytics layer unless there is a documented purpose
   (GDPR / Swiss nFADP data minimisation).
4. **Quality is a contract.** Each Tier 1 asset has automated tests; a failing test opens an
   incident for the owner instead of an e-mail nobody reads.
5. **Governance as code.** Owners, domains, tags, glossary and tests live in
   [`governance/`](../governance) and are applied through the API, so the catalogue can be
   rebuilt from Git.

## 2. Roles (RACI)

| Activity | Data Owner (business team) | Data Steward | Data Governance Office | Platform / IT |
|---|---|---|---|---|
| Define a KPI / glossary term | **A** | R | C (approves wording) | I |
| Classify a dataset (PII, confidentiality) | A | R | C | I |
| Certify an asset (Gold) | **A** | R | C | I |
| Fix a data-quality incident | A | **R** (in ERP) | I | C |
| Run ingestion, profiler, test runner | I | I | C | **R/A** |
| Onboard a new domain | C | C | **A/R** | R |

*R = Responsible, A = Accountable, C = Consulted, I = Informed.*

In this demo: `Supply Chain Planning`, `Procurement` and `Sales Operations` are owner teams;
`Data Governance Office` owns the glossary and reviews terms through the `Supply Chain Planning` reviewer team.

## 3. Domains and data products

| Domain | Type | Owner | What lives there |
|---|---|---|---|
| Supply Chain | Aggregate | Supply Chain Planning | Material master, stock, demand plan, all KPI marts |
| Procurement | Source-aligned | Procurement | Vendor master (LFA1), purchase orders (EKKO/EKPO) |
| Sales & Customer | Source-aligned | Sales Operations | Customer master (KNA1), sales orders, deliveries |

**Data product** `Supply Chain Performance KPIs` packages the five certified mart tables that feed the
*Supply Chain Performance* dashboard. Consumers find it in the Data Marketplace instead of asking
"which table is the right one?".

## 4. Classification policy

| Label | Meaning | Example in this repo | Access rule |
|---|---|---|---|
| `PII.Sensitive` | Identifies a person | Vendor/customer contact name, e-mail, phone | Raw layer only, masked for non-owners |
| `Confidentiality.Restricted` | Named people only | `lfa1`, `kna1` (contain PII) | Owner approval |
| `Confidentiality.Confidential` | Need-to-know | Purchase prices (`ekko`, `ekpo`), VAT IDs, inventory value | Domain members |
| `Confidentiality.Internal` | Any employee | Sales orders, KPI marts | Default |
| `Tier.Tier1` | Business-critical | Masters and KPI marts | Tests + owner + description mandatory |
| `Tier.Tier2` | Important | Transaction tables | Owner + description mandatory |

PII is first detected by OpenMetadata's **auto-classification** (it found 4 of the 5 personal columns);
the steward then confirms and completes it in `governance.yaml` (it missed `contact_phone`).
Human-in-the-loop is the point: automation proposes, the steward decides.

## 5. Certification criteria (Gold)

An asset is certified **Gold** only when all of these are true:

- business owner team and domain assigned;
- table and key columns described, KPI columns linked to an *Approved* glossary term;
- lineage visible back to the ERP source;
- data-quality tests defined and passing on the KPI columns;
- classification applied (Tier + Confidentiality).

Certified in this repo: `fct_otif`, `rpt_otif_monthly`, `fct_plan_vs_actual`, `fct_inventory_position`.

## 6. Data-quality management

Two complementary layers, both visible in the same OpenMetadata screen:

| Layer | Tool | Examples |
|---|---|---|
| Source (raw ERP) | OpenMetadata test runner | goods-issue date not null, stock not negative, PO material exists in material master, e-mail format |
| Transformation | dbt tests (results ingested) | unique / not null keys, referential integrity, accepted values, KPI between 0 and 1 |

Three defects are injected on purpose in the synthetic data (25 deliveries without goods-issue date,
2 negative stock rows, 1 PO line for a non-existent material). Both layers catch all three:
**28 tests, 22 passing, 6 failing**. A failing test creates an **incident** assigned to the owner team.

Why it matters to the business: the 25 deliveries without a goods-issue date silently drop out of
OTIF. Without the test, the KPI would look better than reality.

## 7. Onboarding a new domain (e.g. Quality Management, SAP QM)

1. **Intake (DGO, 30 min):** name the business owner and a steward; agree scope and Tier 1 assets.
2. **Connect:** add the schema to the ingestion filter (`ingestion/01_postgres_metadata.yaml`) and run it.
3. **Classify:** run auto-classification; steward confirms PII and confidentiality in `governance.yaml`.
4. **Define:** steward proposes glossary terms (e.g. *First Pass Yield*, *Non-conformance*);
   reviewer team approves.
5. **Assure:** add quality tests for each Tier 1 table in `governance/data_quality.yaml`.
6. **Certify:** when the Gold criteria in §5 are met, set `certified: true` via pull request.
7. **Announce:** publish the data product in the marketplace and add it to the adoption dashboard.

Target lead time: **2 weeks** from intake to first certified asset.

## 8. Adoption KPIs

What the DGO reports monthly (all available from OpenMetadata's Insights / API):

| KPI | Target | This demo |
|---|---|---|
| Tier 1 assets with owner | 100 % | 100 % (17/17 governed tables) |
| Tier 1 assets with description | 100 % | 100 % |
| KPI columns linked to an approved glossary term | 100 % | 100 % |
| Data-quality test coverage of tables | ≥ 60 % | 65 % (17 of 26 tables) |
| Open data-quality incidents older than 10 days | 0 | 6 open, all from the 3 injected defects (1 false positive resolved) |
| Monthly active catalogue users | grows quarter on quarter | n/a (single-user demo) |

## 9. Cadence

- **Weekly (30 min):** stewards review new incidents and pending glossary terms.
- **Monthly:** DGO reports adoption KPIs to the data council; prioritises the next domain.
- **Quarterly:** owners re-confirm certification and access to Restricted assets.
