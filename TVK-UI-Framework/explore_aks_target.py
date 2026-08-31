"""Dump the real DOM of the CREATE TARGET credentials step on a non-OCP cluster.

test_create_target fails on AKS inside TargetsPage._create_secret: after the
'Create New' fallback is clicked the console shows the 'New ConfigMap' sub-form,
so the 'Enter Secret Name' textbox never appears. This script walks the same
path and dumps every button/textbox (in DOM order) plus the dialog HTML at the
exact point of failure, so the selector can be fixed against evidence.

  .venv\\Scripts\\python.exe explore_aks_target.py <existing-namespace>
"""
import pathlib
import sys

import yaml
from playwright.sync_api import sync_playwright

from config.settings import FrameworkConfig
from pages.login_page import get_login_page
from pages.targets_page import TargetsPage

CONFIG = "config/aks-sanitytestns-config.yaml"
OUT = pathlib.Path("explore"); OUT.mkdir(exist_ok=True)
NAMESPACE = sys.argv[1] if len(sys.argv) > 1 else None


def build_cfg(path):
    """Mirror conftest's merge: defaults <- yaml."""
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
    c.target.name = f"{c.target.name}-dbg"
    if NAMESPACE:
        # Reuse a namespace that already exists so we skip the app install.
        c.app.namespace = NAMESPACE
        c.app_installed = True
    return c


def dump(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    (OUT / f"{name}.html").write_text(page.content(), encoding="utf-8")

    info = page.evaluate("""() => {
      const vis = e => e.offsetParent !== null;
      const dialog = document.querySelector("[role=dialog], .modal-dialog, .modal");
      return {
        buttons: [...document.querySelectorAll('button')].map((e, i) => ({
          i, text: (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,40),
          visible: vis(e), inDialog: dialog ? dialog.contains(e) : false,
          cls: (e.className||'').slice(0,50)
        })),
        textboxes: [...document.querySelectorAll('input[type=text], input:not([type]), input[type=password]')].map((e, i) => ({
          i, placeholder: e.placeholder||'', name: e.name||'', id: e.id||'',
          aria: e.getAttribute('aria-label')||'', visible: vis(e)
        })),
        headings: [...document.querySelectorAll('h1,h2,h3,h4,h5,.title,.breadcrumb,.modal-title')]
          .map(e => (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,60)).filter(Boolean).slice(0,12)
      };
    }""")

    print(f"\n===== {name} =====")
    print("-- headings/breadcrumb --")
    for h in info["headings"]:
        print("   ", h)
    print("-- buttons (DOM order) --")
    for b in info["buttons"]:
        if b["visible"]:
            print(f"   [{b['i']:>2}] dialog={str(b['inDialog']):<5} '{b['text']}'  .{b['cls']}")
    print("-- visible textboxes --")
    for t in info["textboxes"]:
        if t["visible"]:
            print(f"   [{t['i']:>2}] placeholder='{t['placeholder']}' aria='{t['aria']}' id='{t['id']}'")
    print(f"-- files written: explore/{name}.png / .html")


class DebugTargetsPage(TargetsPage):
    """Same flow, but dump the DOM instead of trying to fill the secret form."""

    def _create_secret(self, t):
        # State right before the framework clicks 'Create New Secret'/'Create New'.
        dump(self.page, "aks-target-01-before-create-secret")

        btn = self.page.get_by_role(
            "button", name="Create New Secret", exact=True).first
        used = "Create New Secret"
        if not btn.is_visible(timeout=2000):
            btn = self.page.get_by_role("button", name="Create New", exact=True).last
            used = "Create New (.last fallback)"
        print(f"\n[debug] clicking: {used}")
        btn.click()
        self.page.wait_for_timeout(1500)

        # State after the click — this is where 'New ConfigMap' showed up.
        dump(self.page, "aks-target-02-after-create-secret-click")
        raise SystemExit("\n[debug] dumps complete — inspect explore/ output above")


def main():
    cfg = build_cfg(CONFIG)
    print(f"namespace in use: {cfg.res_ns()}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        print("login (kubeconfig upload)...")
        get_login_page(page, cfg).login()

        print("walking the create-target flow...")
        DebugTargetsPage(page, cfg).create_target()

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
