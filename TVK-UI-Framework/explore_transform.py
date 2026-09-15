"""Headed exploration of the restore TRANSFORM UI (Helm).

Logs in, opens a Helm backup plan's Restore wizard, walks to where the
transform controls appear, and dumps screenshots + HTML at each step so we can
read the real selectors. Run on a machine that can reach the cluster:

  .venv\\Scripts\\python.exe explore_transform.py
"""
import re
import pathlib

import yaml
from playwright.sync_api import sync_playwright

CFG = yaml.safe_load(open("config/example-config.yaml"))
TRILIO = CFG["cluster"]["trilio_url"]
USER = CFG["cluster"]["username"]
PWD = CFG["cluster"]["password"]
OUT = pathlib.Path("explore"); OUT.mkdir(exist_ok=True)

# A Helm-type backup plan to restore from (transform applies to helm/custom).
HELM_PLAN = "trilio-helm-prometheus-testback"


def dump(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    (OUT / f"{name}.html").write_text(page.content(), encoding="utf-8")
    print(f"  dumped {name}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=300)
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        print("login...")
        page.goto(TRILIO, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name=re.compile(r"sign[\s\-]*in\s*via\s*openshift", re.I)).click()
        page.wait_for_timeout(2000)
        try:
            ka = page.get_by_role("link", name=re.compile("kube:admin", re.I)).first
            if ka.is_visible(timeout=4000):
                ka.click()
        except Exception:
            pass
        page.locator("#inputUsername, input[name='username']").first.fill(USER)
        page.locator("#inputPassword, input[name='password']").first.fill(PWD)
        page.get_by_role("button", name=re.compile(r"log\s*in", re.I)).first.click()
        page.wait_for_timeout(4000)
        # accept EULA if present
        try:
            ag = page.get_by_role("button", name=re.compile(r"accept|agree", re.I)).first
            if ag.is_visible(timeout=4000):
                ag.click()
        except Exception:
            pass
        page.wait_for_timeout(3000)
        dump(page, "01-after-login")

        print("go to Backup Plans...")
        page.get_by_role("link", name=re.compile(r"Backup\s*&?\s*Recovery", re.I)).first.click()
        page.wait_for_timeout(1500)
        page.get_by_role("link", name=re.compile(r"Backup Plans", re.I)).first.click()
        page.wait_for_timeout(2500)
        dump(page, "02-backup-plans")

        print(f"find helm plan '{HELM_PLAN}' and open Restore...")
        try:
            search = page.get_by_test_id("search-input").first
            search.fill(HELM_PLAN)
            page.wait_for_timeout(1500)
        except Exception:
            pass
        row = page.locator("tr, [role='row']").filter(has_text=HELM_PLAN).first
        row.scroll_into_view_if_needed()
        row.locator("button").last.click()   # caret next to Edit
        page.wait_for_timeout(800)
        dump(page, "03-row-menu")
        page.get_by_role("button", name=re.compile(r"^\s*Restore\s*$", re.I)).first.click()
        page.wait_for_timeout(2500)
        dump(page, "04-restore-config")

        print("fill restore name, walk to Transform Components...")
        page.get_by_role("textbox", name=re.compile(r"Name", re.I)).first.fill("explore-restore")
        page.wait_for_timeout(500)

        # Step 1 -> 2 (Resource Selector)
        page.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        page.wait_for_timeout(2000)
        dump(page, "07-resource-selector")

        # Step 2 -> 3 (Transform Components)
        page.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        page.wait_for_timeout(2500)
        dump(page, "08-transform-components")

        # Wait for any loading overlay to clear before interacting
        try:
            page.locator("div.overlay").first.wait_for(state="hidden", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

        # Dump the toggle's surrounding HTML so we can see its exact markup
        try:
            html = page.evaluate(
                """() => {
                    const el = [...document.querySelectorAll('*')].find(
                        e => e.textContent && e.textContent.trim() === 'Toggle to enable browsing');
                    return el ? el.parentElement.outerHTML : 'NOT FOUND';
                }""")
            (OUT / "toggle.html").write_text(html, encoding="utf-8")
            print("  wrote toggle.html")
        except Exception as e:
            print(f"  toggle html dump failed: {e}")

        # Click the toggle switch (the checkbox input)
        try:
            page.locator("[data-testid='toggle-button-input']").first.click(force=True)
            page.wait_for_timeout(3000)
            dump(page, "09-browsing-enabled")
        except Exception as e:
            print(f"  could not enable browsing: {e}")

        # Browsing loads the target resource tree — "This might take several
        # minutes". Poll until the 'Add Transform' control appears (up to 5 min)
        add = None
        for i in range(30):
            try:
                cand = page.get_by_text(re.compile(r"add\s*transform", re.I)).first
                if cand.is_visible(timeout=2000):
                    add = cand
                    print(f"  Add Transform appeared after ~{i*10}s")
                    break
            except Exception:
                pass
            print(f"  waiting for browsing to finish... {i*10}s")
            page.wait_for_timeout(10000)
        dump(page, "10-browsing-done")

        if add is not None:
            add.click()
            page.wait_for_timeout(2000)
            dump(page, "11-transform-add-clicked")

            # --- CUSTOM sub-flow: click 'Add Custom Resource' -> GVKO fields ---
            try:
                acr = page.get_by_text(re.compile(r"Add Custom Resource", re.I)).first
                if acr.is_visible(timeout=4000):
                    acr.click()
                    page.wait_for_timeout(2000)
                    dump(page, "12-add-custom-resource")
                    (OUT / "12-custom.html").write_text(page.content(), encoding="utf-8")
                    t = page.eval_on_selector_all(
                        "button, label, a, span, [placeholder]",
                        "els=>els.filter(e=>e.offsetParent).map(e=>e.innerText.trim()||e.getAttribute('placeholder')).filter(Boolean).slice(0,150)")
                    (OUT / "12-custom-texts.txt").write_text("\n".join(t), encoding="utf-8")
                    print("  wrote 12-custom.*")
            except Exception as e:
                print(f"  add-custom-resource explore failed: {e}")

            # --- HELM sub-flow: switch Transformation Type to Helm ---
            try:
                # go Back to the Add Transform Component screen
                back = page.get_by_text(re.compile(r"^\s*Back\s*$", re.I)).first
                if back.is_visible(timeout=2000):
                    back.click(); page.wait_for_timeout(1500)
                # Transformation Type is a react-select; click it via its label
                lbl = page.get_by_text(re.compile(r"Transformation Type", re.I)).first
                ctrl = lbl.locator("xpath=following::*[contains(@class,'select') or @role='combobox' or .//input[contains(@id,'react-select')]][1]")
                ctrl.click()
                page.wait_for_timeout(700)
                page.get_by_text("Helm", exact=True).last.click()
                page.wait_for_timeout(2500)
                dump(page, "13-helm-type")
                (OUT / "13-helm.html").write_text(page.content(), encoding="utf-8")
                t = page.eval_on_selector_all(
                    "button, label, a, span, [placeholder], input",
                    "els=>els.filter(e=>e.offsetParent).map(e=>e.innerText && e.innerText.trim() || e.getAttribute('placeholder') || e.getAttribute('name')).filter(Boolean).slice(0,180)")
                (OUT / "13-helm-texts.txt").write_text("\n".join(t), encoding="utf-8")
                # also dump react-select/input names for helm
                sel = page.evaluate("""() => [...document.querySelectorAll('input,select,[id^=react-select]')].map(e=>({tag:e.tagName,id:e.id,name:e.getAttribute('name'),ph:e.getAttribute('placeholder')})).filter(o=>o.id||o.name||o.ph)""")
                (OUT / "13-helm-fields.txt").write_text("\n".join(str(s) for s in sel), encoding="utf-8")
                print("  wrote 13-helm.*")
            except Exception as e:
                print(f"  helm-type explore failed: {e}")
        else:
            print("  'Add Transform' never appeared")

        # Dump all visible button/label texts on the transform step for selectors
        texts = page.eval_on_selector_all(
            "button, label, [role='tab'], a, span",
            "els => els.filter(e=>e.offsetParent).map(e=>e.innerText.trim()).filter(Boolean).slice(0,120)")
        (OUT / "08-transform-texts.txt").write_text("\n".join(texts), encoding="utf-8")
        print("  wrote 08-transform-texts.txt")

        print("Done. Inspect the ./explore folder. Browser stays open 90s.")
        page.wait_for_timeout(90000)
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
