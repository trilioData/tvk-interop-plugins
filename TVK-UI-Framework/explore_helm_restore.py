"""Explore the helm restore transform on the 'helm-mysql' plan (the one the
codegen used). Find where 'Transform Name' + the values editor appear."""
import re
import pathlib
import yaml
from playwright.sync_api import sync_playwright

CFG = yaml.safe_load(open("config/example-config.yaml"))
TRILIO = CFG["cluster"]["trilio_url"]
USER = CFG["cluster"]["username"]
PWD = CFG["cluster"]["password"]
OUT = pathlib.Path("explore"); OUT.mkdir(exist_ok=True)
PLAN = "helm-mysql"   # the plan the codegen restored


def dump(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    (OUT / f"{name}.html").write_text(page.content(), encoding="utf-8")
    print(f"  dumped {name}")


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False, slow_mo=300)
        ctx = b.new_context(ignore_https_errors=True, viewport={"width":1600,"height":900})
        page = ctx.new_page(); page.set_default_timeout(60000)

        print("login...")
        page.goto(TRILIO, wait_until="domcontentloaded"); page.wait_for_timeout(2000)
        page.get_by_role("button", name=re.compile(r"sign[\s\-]*in\s*via\s*openshift", re.I)).click()
        page.wait_for_timeout(2000)
        page.locator("#inputUsername, input[name='username']").first.fill(USER)
        page.locator("#inputPassword, input[name='password']").first.fill(PWD)
        page.get_by_role("button", name=re.compile(r"log\s*in", re.I)).first.click()
        page.wait_for_timeout(4000)
        try:
            ag = page.get_by_role("button", name=re.compile(r"accept|agree", re.I)).first
            if ag.is_visible(timeout=4000): ag.click()
        except Exception: pass
        page.wait_for_timeout(3000)

        print("go to Backup Plans -> open helm plan restore...")
        page.get_by_role("link", name=re.compile(r"Backup\s*&?\s*Recovery", re.I)).first.click()
        page.wait_for_timeout(1500)
        page.get_by_role("link", name=re.compile(r"Backup Plans", re.I)).first.click()
        page.wait_for_timeout(2500)
        page.get_by_role("link", name=re.compile(rf"^{re.escape(PLAN)}$", re.I)).first.click()
        page.wait_for_timeout(2000)
        page.get_by_role("button", name=re.compile(r"View Backups", re.I)).first.click()
        page.wait_for_timeout(2000)
        page.get_by_role("button", name=re.compile(r"^\s*Restore\s*$", re.I)).first.click()
        page.wait_for_timeout(2500)
        dump(page, "hr-01-restore-open")

        # Fill name, expand Restore Flags
        page.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first.fill("explore-helm-trans")
        page.wait_for_timeout(500)
        page.get_by_role("button", name=re.compile(r"Restore Flags", re.I)).first.click()
        page.wait_for_timeout(1200)
        dump(page, "hr-02-restore-flags")

        # Look for a transform-related toggle / Transform Name appearing
        body = page.inner_text("body").lower()
        print("  'transform' present on Basic step:", "transform" in body)

        # Try toggling restoreStorageClass and others, dumping after each
        for flag in ["restoreStorageClass", "retainHelmReleaseName", "patchIfAlreadyExists"]:
            try:
                lbl = page.get_by_text(re.compile(rf"^\s*{flag}\s*$", re.I)).first
                sw = lbl.locator("xpath=following::*[self::label or contains(@class,'switch')][1]")
                sw.click(); page.wait_for_timeout(1500)
                dump(page, f"hr-03-toggled-{flag}")
                if page.get_by_role("textbox", name=re.compile(r"Transform Name", re.I)).first.is_visible(timeout=1500):
                    print(f"  >>> Transform Name appeared after toggling {flag}")
                    break
            except Exception as e:
                print(f"  toggle {flag} failed: {e}")

        # also check the Transform Components step
        try:
            page.get_by_text(re.compile(r"Transform Components", re.I)).first.click()
            page.wait_for_timeout(2000)
            dump(page, "hr-04-transform-components")
        except Exception:
            pass

        print("Done. Browser stays open 90s.")
        page.wait_for_timeout(90000)
        ctx.close(); b.close()


if __name__ == "__main__":
    main()
