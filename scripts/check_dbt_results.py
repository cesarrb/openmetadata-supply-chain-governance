"""CI gate on dbt test results.

The synthetic data contains three deliberate defects. The build is green only when:
  * every test expected to catch a defect FAILS (the defect is still detected), and
  * every other test PASSES (nothing new is broken).

Usage:  uv run python scripts/check_dbt_results.py   (after `dbt test`)
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_FAILURES = {  # test name prefix -> injected defect it must catch
    "not_null_stg_delivery_line_actual_goods_issue_date": "25 deliveries without goods-issue date",
    "non_negative_stg_stock_unrestricted_stock_qty": "2 storage locations with negative stock",
    "relationships_stg_purchase_order_line_material_id": "1 purchase-order line for an unknown material",
}

results = json.loads((ROOT / "dbt/target/run_results.json").read_text())["results"]
tests = {r["unique_id"].split(".")[2]: r["status"] for r in results if r["unique_id"].startswith("test.")}
problems = []
for name, status in sorted(tests.items()):
    expected = next((d for p, d in EXPECTED_FAILURES.items() if name.startswith(p)), None)
    if expected and status != "fail":
        problems.append(f"defect no longer detected ({expected}): {name} -> {status}")
    elif not expected and status != "pass":
        problems.append(f"unexpected test result: {name} -> {status}")
    print(f"  {'expected-fail' if expected else 'pass         '}  {status:5s}  {name}")
missing = [p for p in EXPECTED_FAILURES if not any(n.startswith(p) for n in tests)]
problems += [f"expected test missing: {m}" for m in missing]
if problems:
    print("\n".join(["FAILED:"] + problems))
    sys.exit(1)
print(f"OK: {len(tests)} dbt tests, all 3 injected defects detected, no unexpected failures.")
