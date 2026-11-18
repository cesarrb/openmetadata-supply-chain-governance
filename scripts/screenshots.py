"""Capture README screenshots of the OpenMetadata UI with headless Chromium.

Usage:  uv run --with playwright python scripts/screenshots.py [name ...]
Logs in with the local default admin account (OM_ADMIN_EMAIL / OM_ADMIN_PASSWORD).
"""
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
BASE = "http://localhost:8585"
T = "erp_postgres.erp"
PAGES = {
    "01_lineage_end_to_end": f"/table/{T}.analytics_marts.fct_otif/lineage",
    "02_table_governed_pii": f"/table/{T}.sap_erp.lfa1/schema",
    "03_glossary": "/glossary/SupplyChainGlossary",
    "04_glossary_term_otif": "/glossary/SupplyChainGlossary.OTIF",
    "05_certified_kpi_table": f"/table/{T}.analytics_marts.fct_otif/schema",
    "06_data_quality": f"/table/{T}.sap_erp.likp/profiler/data-quality",
    "07_data_quality_overview": "/data-quality/test-cases",
    "08_domain": "/domain/SupplyChain/assets",
    "09_data_product": "/dataProduct/SupplyChainKPIs/assets",
    "10_dashboard": "/dashboard/metabase_bi.2",
    "11_column_profile": f"/table/{T}.sap_erp.mard/profiler/column-profile",
    "12_data_contract": f"/table/{T}.analytics_marts.fct_otif/contract",
    "13_access_policy": "/settings/access/policies/RestrictedDataAccess",
    "14_lineage_to_dashboard": "/dashboard/metabase_bi.2/lineage",
}
METABASE = {"15_metabase_dashboard": "/dashboard/2"}


def main(only):
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")  # uses the installed Google Chrome, headless
        page = b.new_page(viewport={"width": 1800, "height": 1050}, device_scale_factor=1)
        page.goto(BASE + "/signin")
        page.fill("input#email", os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org"))
        page.fill("input#password", os.environ.get("OM_ADMIN_PASSWORD", "admin"))
        page.keyboard.press("Enter")
        page.wait_for_url(lambda u: "signin" not in u, timeout=30000)
        for name, path in PAGES.items():
            if only and name not in only:
                continue
            page.goto(BASE + path)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3500)
            if "lineage" in path:  # full-screen canvas, then fit the whole graph
                page.get_by_role("button", name="Full Screen View").first.click()
                page.wait_for_timeout(1500)
                page.get_by_test_id("fit-screen").click()
                page.get_by_text("Fit to screen").click()
                page.mouse.move(5, 500)
                page.wait_for_timeout(1500)
            page.screenshot(path=OUT / f"{name}.png")
            print("saved", name)
        if not only or any(n in only for n in METABASE):
            page = b.new_page(viewport={"width": 1800, "height": 1050})
            page.goto("http://localhost:3000/auth/login")
            page.fill("input[name=username]", os.environ.get("MB_ADMIN_EMAIL", "admin@example.com"))
            page.fill("input[name=password]", os.environ.get("MB_ADMIN_PASSWORD", "Governance-demo-2026"))
            page.keyboard.press("Enter")
            page.wait_for_url(lambda u: "login" not in u, timeout=30000)
            for name, path in METABASE.items():
                page.goto("http://localhost:3000" + path)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(5000)
                page.screenshot(path=OUT / f"{name}.png")
                print("saved", name)
        b.close()


if __name__ == "__main__":
    main(sys.argv[1:])
