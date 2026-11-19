# Data Governance Operating Model

How the catalogue in this repository is meant to be run in a manufacturing company with an
SAP backbone. The model is deliberately light: federated ownership, a small central office,
and governance rules kept as code so every change is reviewed, validated in CI and auditable.

## 1. Principles

1. **The business owns the data, IT runs the platform.** Every certified asset has a business
   owner team; the Data Governance Office (DGO) owns standards, not datasets.
2. **One definition per KPI.** OTIF, Plan vs Actual or Days of Inventory are defined once in the
   glossary and linked to the exact column that computes them.
3. **Classify at the source, minimise downstream.** Personal data is tagged in the raw ERP layer
   and is *not* propagated to the analytics layer unless there is a documented purpose
   (GDPR / Swiss nFADP, the new Federal Act on Data Protection, data minimisation).
4. **Quality is a contract.** Each certified asset has a data contract and automated tests; a failing
   test opens an incident for the owner instead of an e-mail nobody reads.
5. **Governance as code.** Owners, domains, tags, glossary, contracts, policies and tests live in
   [`governance/`](../governance), are checked in CI on every pull request and applied through the
   API, so the catalogue can be rebuilt from Git.

## 2. Roles (RACI)

| Activity | Data Owner (business team) | Data Steward | Data Governance Office | Platform / IT |
|---|---|---|---|---|
| Define a KPI / glossary term | **A** | R | C (approves wording) | I |
| Classify a dataset (PII, confidentiality) | A | R | C | I |
| Review auto-classification proposals | I | **R/A** | C | I |
| Certify an asset (Gold) and sign its data contract | **A** | R | C | I |
| Fix a data-quality incident | A | **R** (in ERP) | I | C |
| Grant access to Restricted data | **A** | C | C | R (policy) |
| Run ingestion, profiler, test runner, CI | I | I | C | **R/A** |
| Onboard a new domain | C | C | **A/R** | R |

*R = Responsible, A = Accountable, C = Consulted, I = Informed.*

In this demo: `Supply Chain Planning`, `Procurement` and `Sales Operations` are owner teams;
`Data Governance Office` owns the glossary, which the `Supply Chain Planning` team reviews.

## 3. Domains and data products

| Domain | Type | Owner | What lives there |
|---|---|---|---|
| Supply Chain | Aggregate | Supply Chain Planning | Material master, stock, demand plan, KPI marts, the Metabase dashboard |
| Procurement | Source-aligned | Procurement | Vendor master (LFA1), purchase orders (EKKO/EKPO) |
| Sales & Customer | Source-aligned | Sales Operations | Customer master (KNA1), sales orders, deliveries |

**Data product** `Supply Chain Performance KPIs` packages the five mart tables and the *Supply Chain
Performance* dashboard (Metabase). Consumers find it in the Data Marketplace instead of asking
"which table is the right one?".

## 4. Classification policy

| Label | Meaning | Example in this repo | Access rule |
|---|---|---|---|
| `PII.Sensitive` | Identifies a person | Vendor/customer contact name, e-mail, phone | Raw layer only |
| `Confidentiality.Restricted` | Owner team only | `lfa1`, `kna1` (contain PII) | Enforced by policy (section 6) |
| `Confidentiality.Confidential` | Need-to-know | Purchase prices (`ekko`, `ekpo`), VAT IDs, inventory value | Domain members |
| `Confidentiality.Internal` | Any employee | Sales orders, most KPI marts | Default |
| `Tier.Tier1` | Business-critical | Masters and KPI marts | Owner, description and tests mandatory |
| `Tier.Tier2` | Important | Transaction tables | Owner and description mandatory |

**Automation proposes, the steward decides.** OpenMetadata's auto-classification scans column
names and sample values. In this repo it:

- correctly found 4 of the 5 personal-data columns;
- **missed** `lfa1.contact_phone`, which the steward adds in `governance.yaml`;
- raised **4 false positives**: business dates (`ekko.bedat`, `ekpo.eindt`, `vbak.erdat`,
  `demand_plan.plan_month`) flagged as personal data, probably read as dates of birth. The steward
  rejects them with `reject_auto: true`, and every re-run of `make governance` removes them again.

## 5. Certification and data contracts

An asset is certified **Gold** only when all of these are true (CI enforces the last three):

- business owner team and domain assigned, table and key columns described;
- lineage visible back to the ERP source;
- linked to an *Approved* glossary term;
- data-quality tests defined;
- a **data contract** exists and passes validation.

Each certified table carries a [data contract](../governance/contracts.yaml), the producer's promise to
its consumers. It is validated by OpenMetadata and exported in the Open Data Contract Standard (ODCS)
to [`contracts/`](../contracts):

| Contract part | Content in this repo | Validated by OpenMetadata |
|---|---|---|
| Schema | The columns consumers may rely on, with types | Columns still exist with the same type |
| Semantics | Metadata rules: has owner, has description, has domain | Rules evaluated on the table |
| Quality | The table's test cases (OpenMetadata and dbt) | All linked tests pass |
| SLA | Refreshed daily, available by 06:00, latency under 1 day, 3-year retention | Shown to consumers |
| Security and terms | Confidentiality label, terms of use | Shown to consumers |

Certified in this repo: `fct_otif`, `rpt_otif_monthly`, `fct_plan_vs_actual`, `fct_inventory_position`:
**4 contracts, 4 passing**.

## 6. Access control

Restricted tables (the vendor and customer masters, which hold personal data) can be *found* by
everyone, but only the owner team and the DGO can see their rows. One policy, written in
`governance.yaml`:

```
deny  ViewSampleData, ViewDataProfile, ViewQueries  on table
when  matchAnyTag('Confidentiality.Restricted') && !isOwner() && !inAnyTeam('data-governance-office')
```

`scripts/check_access.py` asks OpenMetadata what two demo personas may do:

| Table | Supply Chain Analyst | Procurement Steward |
|---|---|---|
| `lfa1` vendor master (owner: Procurement) | metadata yes, rows **no** | metadata yes, rows **yes** |
| `kna1` customer master (owner: Sales Ops) | metadata yes, rows **no** | metadata yes, rows **no** |
| `fct_otif` (Internal) | yes | yes |

Discoverability is never blocked, because a catalogue that hides what exists pushes people to shadow copies.

## 7. Data-quality management

Three complementary layers:

| Layer | Tool | Examples |
|---|---|---|
| Source (raw ERP) | OpenMetadata test runner | goods-issue date not null, stock not negative, PO material exists in material master, e-mail format |
| Transformation | dbt tests (results ingested into OpenMetadata) | unique / not null keys, referential integrity, accepted values, KPI between 0 and 1, forecast accuracy not degenerate |
| Pull request | GitHub Actions | rebuilds the warehouse, fails if a known defect stops being detected or anything else breaks, fails if any table or column lacks a description, validates governance YAML |

Three defects are injected on purpose in the synthetic data: 23 deliveries without goods-issue date,
4 storage locations with negative stock and 1 purchase-order line for a non-existent material.
Both layers catch all three: **31 tests, 25 passing, 6 failing**. Each failing test opens an
**incident** assigned to the owner team.

Why it matters to the business: the 23 deliveries without a goods-issue date silently drop out of
OTIF, so without the test the KPI would look better than it is.

**A real bug the tests now guard against.** Changing quantities from `numeric` to `integer` made
Postgres divide integers, and forecast accuracy came out at 97 % instead of 72 %. No range test
noticed, because 0.97 is a valid ratio. Building the Metabase dashboard exposed it. The fix casts to
`numeric`, and a new dbt test (`assert_forecast_accuracy_not_degenerate`) fails if accuracy is
implausibly high. The lesson for the operating model: plausibility tests matter as much as validity tests.

## 8. Onboarding a new domain (e.g. Quality Management, SAP QM)

1. **Intake (DGO, 30 min):** name the business owner and a steward; agree scope and Tier 1 assets.
2. **Connect:** add the schema to the ingestion filter (`ingestion/01_postgres_metadata.yaml`) and run it.
3. **Classify:** run auto-classification; the steward confirms or rejects proposals in `governance.yaml`.
4. **Define:** the steward proposes glossary terms (e.g. *First Pass Yield*, *Non-conformance*);
   the reviewer team approves them.
5. **Assure:** add quality tests for each Tier 1 table in `governance/data_quality.yaml`.
6. **Contract and certify:** write the data contract; when the Gold criteria in section 5 are met, set
   `certified: true`. CI blocks the pull request if the contract or tests are missing.
7. **Announce:** publish the data product in the marketplace; it appears in the scorecard.

Target lead time: **2 weeks** from intake to first certified asset.

## 9. Adoption KPIs

Measured from the live catalogue by `scripts/scorecard.py`, so they are not typed by hand. The latest
run is in [SCORECARD.md](SCORECARD.md). Headline values:

| KPI | Target | This demo |
|---|---|---|
| Tier 1 tables with owner, domain and description | 100 % | 100 % (9/9) |
| Glossary terms approved | 100 % | 100 % (13/13) |
| Tables with data-quality tests | ≥ 60 % | 69 % (18/26) |
| Data contracts passing | 100 % | 100 % (4/4) |
| Open data-quality incidents older than 10 days | 0 | 6, all from the 3 injected defects |
| Column-level lineage mappings | grows with coverage | 182 |

## 10. Cadence

- **Every pull request:** CI validates governance YAML, checks documentation coverage and rebuilds the warehouse.
- **Weekly (30 min):** stewards review new incidents, auto-classification proposals and pending glossary terms.
- **Monthly:** the DGO publishes the scorecard to the data council and prioritises the next domain.
- **Quarterly:** owners re-confirm certification, contracts and access to Restricted assets.
