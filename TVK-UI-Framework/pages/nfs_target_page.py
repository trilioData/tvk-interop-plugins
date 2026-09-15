"""NFS target page object — kept separate so the ObjectStore target code in
targets_page.py stays intact. Used when cfg.target.type == 'nfs'.

Selectors verified against Playwright codegen:
  Targets -> Create New
  Namespace (react-select 'Select Namespace') -> the app/target namespace
  NFS is the default vendor tab -> Export* = nfs_path
  Continue -> name popup ('What would be the name of...') -> Create Target
"""
import re

from pages.base_page import BasePage


class NFSTargetPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("targets")

    def _react_select(self, placeholder_regex: str, option_text: str,
                      type_filter: str | None = None):
        p = self.page
        p.get_by_text(re.compile(placeholder_regex)).last.click()
        p.wait_for_timeout(600)
        if type_filter:
            rs = p.locator("input[id^='react-select'][id$='-input']").last
            try:
                if rs.is_visible(timeout=1500):
                    rs.fill(type_filter[:12])
                    p.wait_for_timeout(800)
            except Exception:
                pass
        opt = p.get_by_test_id("form-wizard-children").get_by_text(option_text, exact=True)
        if not opt.is_visible(timeout=2000):
            opt = p.get_by_text(option_text, exact=True).last
        opt.click()
        p.wait_for_timeout(500)

    def create_target(self):
        t = self.cfg.target
        p = self.page
        # Integrated -> app namespace; standalone -> configured target namespace
        ns = self.cfg.res_ns(t.namespace)

        self.open()
        self.click_create_new()
        p.get_by_text(re.compile(r"^\s*create\s*target\s*$", re.I)).first.wait_for(
            state="visible", timeout=15000)
        self.shot("nfs-target-create-form")

        # 1. Namespace (react-select)
        self._react_select(r"^Select Namespace$", ns, type_filter=ns)
        self.shot("nfs-target-namespace-selected")

        # 2. NFS is the default vendor tab -> Export* = nfs_path
        p.get_by_role("textbox", name=re.compile(r"^Export", re.I)).fill(t.nfs_path)
        self.shot("nfs-target-export-filled")

        # Enable Browsing toggle (needed for restore transforms) if configured
        if self.cfg.target.enable_browsing:
            from pages.targets_page import TargetsPage
            ok = TargetsPage._click_enable_browsing_toggle(p)
            self.shot("nfs-target-enable-browsing")
            if not ok:
                raise AssertionError(
                    "Could not enable 'Enable Browsing' on the NFS target — see "
                    f"{self.cfg.screenshot_dir}/nfs-target-enable-browsing.png")
            print("[nfs_target] Enable Browsing turned ON")

        # 3. Continue -> name popup -> Create Target
        self.advance_wizard_to_create(name_prefix="nfs-target", fill_name=t.name)

    def verify_target_available(self):
        self.open()
        self.wait_for_status(self.cfg.target.name, "Available", timeout_s=600)
        self.shot("nfs-target-available")
        # Only verify the Browsing column when browsing was requested for this
        # target (helm flow). Normal targets skip this check.
        if self.cfg.target.enable_browsing:
            self._verify_browsing_enabled()

    def _verify_browsing_enabled(self, timeout_s: int = 600):
        """Wait for the target row's 'Browsing' column to show Enabled."""
        import time
        p = self.page
        name = self.cfg.target.name
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.open()
            row = p.locator("tr, [role='row']").filter(has_text=name).first
            try:
                txt = row.inner_text(timeout=3000)
                if re.search(r"\bEnabled\b", txt, re.I) and not re.search(
                        r"\bDisabled\b", txt, re.I):
                    self.shot("nfs-target-browsing-enabled")
                    print(f"[nfs_target] '{name}' browsing column shows Enabled")
                    return
            except Exception:
                pass
            remaining = int(deadline - time.time())
            print(f"[nfs_target] waiting for browsing to show Enabled... {remaining}s left")
            p.wait_for_timeout(10000)
        self.shot("nfs-target-browsing-not-enabled")
        raise AssertionError(
            f"NFS target '{name}' browsing did not show Enabled within {timeout_s}s")
