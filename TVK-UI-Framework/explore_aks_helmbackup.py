"""Why is 'Create Backup' unavailable for a Helm backup plan on this build?

helm_transform fails in BackupPlansPage.trigger_backup: after the plan row is
selected, 'Create Backup' appears greyed while 'Create Snapshot' is enabled, no
dialog opens, and the wait for the name field times out. This selects an
existing Helm plan and reports the real DOM state of the action buttons, so we
can tell a genuinely disabled control from one that only looks disabled.

  .venv\\Scripts\\python.exe explore_aks_helmbackup.py <helm-plan-name>
"""
import pathlib
import sys

import yaml
from playwright.sync_api import sync_playwright

from config.settings import FrameworkConfig
from pages.login_page import get_login_page
from pages.backupplans_page import BackupPlansPage

CONFIG = "config/aks-sanitytestns-config.yaml"
PLAN = sys.argv[1] if len(sys.argv) > 1 else "helm-bp-cjj"
OUT = pathlib.Path("explore"); OUT.mkdir(exist_ok=True)


def build_cfg(path):
    c = FrameworkConfig()
    data = yaml.safe_load(open(path)) or {}
    for section, val in data.items():
        obj = getattr(c, section, None)
        if obj is not None and isinstance(val, dict):
            for k, v in val.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
        elif hasattr(c, section):
            setattr(c, section, val)
    c.run_suffix = "dbg"
    return c


def main():
    cfg = build_cfg(CONFIG)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        print("login...")
        get_login_page(page, cfg).login()

        bp = BackupPlansPage(page, cfg)
        print("opening Backup Plans...")
        bp.open()
        page.wait_for_timeout(2500)

        print(f"selecting row '{PLAN}'...")
        row = page.locator("tr, [role='row']").filter(has_text=PLAN).first
        row.scroll_into_view_if_needed()
        cb = row.locator("input[type='checkbox'], [role='checkbox']").first
        cb.check()
        page.wait_for_timeout(1500)

        page.screenshot(path=str(OUT / "helmplan-selected.png"), full_page=True)
        (OUT / "helmplan-selected.html").write_text(page.content(), encoding="utf-8")

        info = page.evaluate("""() => {
          const wanted = ['Create Backup','Create Snapshot','Create Restore'];
          return [...document.querySelectorAll('button')]
            .map(e => ({
              text: (e.innerText||'').replace(/\\s+/g,' ').trim(),
              disabledAttr: e.hasAttribute('disabled'),
              domDisabled: e.disabled === true,
              ariaDisabled: e.getAttribute('aria-disabled'),
              cls: (e.className||''),
              pointerEvents: getComputedStyle(e).pointerEvents,
              opacity: getComputedStyle(e).opacity,
              visible: e.offsetParent !== null,
            }))
            .filter(b => wanted.some(w => b.text === w));
        }""")

        print("\n=== action button state ===")
        for b in info:
            print(f"  '{b['text']}'")
            print(f"      disabled attr : {b['disabledAttr']}")
            print(f"      .disabled     : {b['domDisabled']}")
            print(f"      aria-disabled : {b['ariaDisabled']}")
            print(f"      pointerEvents : {b['pointerEvents']}   opacity: {b['opacity']}")
            print(f"      class         : {b['cls'][:70]}")

        # Now actually click it and see what the app does.
        print("\nclicking 'Create Backup'...")
        page.get_by_role("button", name="Create Backup", exact=True).click()
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "helmplan-after-click.png"), full_page=True)

        after = page.evaluate("""() => {
          const vis = e => e.offsetParent !== null;
          const texts = sel => [...document.querySelectorAll(sel)]
            .filter(vis).map(e => (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,180))
            .filter(Boolean);
          return {
            dialogs: texts("[role=dialog], .modal-dialog, .modal-popup:not(.d-none)"),
            toasts: texts(".toast, .notification, [class*=alert i], [class*=error i]"),
            inputs: [...document.querySelectorAll('input')].filter(vis)
              .map(e => `placeholder='${e.placeholder||''}' id='${e.id||''}'`),
            url: location.hash,
          };
        }""")
        print("\n=== after clicking Create Backup ===")
        print("url hash :", after["url"])
        print("dialogs  :", after["dialogs"] or "(none opened)")
        print("toasts   :", after["toasts"] or "(none)")
        print("inputs   :", after["inputs"][:10])

        # Exact structure of the inputs inside the CREATE NEW BACKUP dialog,
        # so the name field can be located without placeholder/label.
        dlg = page.evaluate("""() => {
          const d = [...document.querySelectorAll("[role=dialog], .modal-dialog, .modal-content")]
            .find(e => (e.innerText||'').includes('CREATE NEW BACKUP'));
          if (!d) return {found: false};
          return {
            found: true,
            inputs: [...d.querySelectorAll('input')].map(e => ({
              type: e.type, id: e.id, name: e.name, placeholder: e.placeholder,
              cls: (e.className||'').slice(0,60),
              visible: e.offsetParent !== null,
              inReactSelect: !!e.closest('[class*=select i]'),
              labelFor: (() => {
                const l = [...d.querySelectorAll('label')].find(x => x.htmlFor && x.htmlFor === e.id);
                return l ? l.innerText.trim() : null;
              })(),
              prevText: (e.parentElement && e.parentElement.previousElementSibling)
                ? (e.parentElement.previousElementSibling.innerText||'').trim().slice(0,30) : null,
            })),
            html: d.innerHTML.replace(/\\s+/g,' ').slice(0, 700),
          };
        }""")
        print("\n=== CREATE NEW BACKUP dialog inputs ===")
        if not dlg.get("found"):
            print("  dialog not found")
        else:
            for i in dlg["inputs"]:
                print(f"  type={i['type']} vis={i['visible']} reactSelect={i['inReactSelect']} "
                      f"id='{i['id']}' placeholder='{i['placeholder']}' label={i['labelFor']} "
                      f"prev='{i['prevText']}' cls={i['cls']}")
            print("\n-- dialog html (trimmed) --")
            print(dlg["html"])

        print("\nfiles: explore/helmplan-selected.png, helmplan-after-click.png")
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
