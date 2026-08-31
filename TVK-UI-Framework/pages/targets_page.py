"""Targets page object — create and verify backup targets (NFS / ObjectStore).

Selectors verified against Playwright codegen of the CREATE TARGET form:
  Namespace*  -> react-select ('Select Namespace'); the app namespace
  VENDOR DETAILS: NFS (default) | ObjectStore  (inside form-wizard-children)
    ObjectStore: Vendor* ('Select Option' -> AWS), Bucket Name*, Region, URL
    Credentials: 'Create New' -> Enter Secret Name / Access Key / Secret Key
                 -> Create  -> (secret auto-selected)
  Continue -> name popup -> Create Target
"""
import re

from pages.base_page import BasePage


class TargetsPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("targets")

    # ---------- react-select helper (options live in form-wizard-children) ----

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

    # ---------- create ----------

    def create_target(self):
        t = self.cfg.target
        p = self.page
        # Integrated -> app namespace; standalone -> configured target namespace
        ns = self.cfg.res_ns(self.cfg.target.namespace)

        self.open()
        self.click_create_new()
        p.get_by_text(re.compile(r"^\s*create\s*target\s*$", re.I)).first.wait_for(
            state="visible", timeout=15000)
        self.shot("target-create-form")

        # 1. Namespace (react-select) — the app namespace
        self._react_select(r"^Select Namespace$", ns, type_filter=ns)
        self.shot("target-namespace-selected")

        if t.type.lower() in ("s3", "objectstore", "object-store", "object_store"):
            # 2. ObjectStore tab — must be clicked inside form-wizard-children
            p.get_by_test_id("form-wizard-children").get_by_text(
                "ObjectStore", exact=True).click()
            p.wait_for_timeout(800)
            self.shot("target-objectstore-tab")

            # 3. Vendor: 'Select Option' -> AWS
            self._react_select(r"^Select Option$", t.vendor)

            # 4. Bucket Name, Region, URL
            p.get_by_role("textbox", name=re.compile(r"Bucket Name", re.I)).fill(t.bucket)
            if t.region:
                p.get_by_role("textbox", name=re.compile(r"^Region", re.I)).fill(t.region)
            try:
                url_box = p.get_by_role("textbox", name=re.compile(r"URL", re.I)).first
                if t.s3_url and url_box.is_visible(timeout=1500):
                    url_box.fill(t.s3_url)
            except Exception:
                pass
            self.shot("target-objectstore-filled")

            # 5. Object store credentials -> create a new secret
            self._create_secret(t)
        else:
            p.get_by_placeholder(re.compile(r"enter\s*export", re.I)).fill(t.nfs_path)
            self.shot("target-nfs-filled")

        # Enable Browsing toggle (needed for restore transforms) if configured
        self._enable_browsing_if_configured()

        self.shot("target-form-filled")

        # 6. Continue -> name popup -> Create Target
        self.advance_wizard_to_create(name_prefix="target", fill_name=t.name)

    def _enable_browsing_if_configured(self):
        """Turn ON the 'Enable Browsing' toggle on the target form when
        cfg.target.enable_browsing is True (required for restore transforms).
        Clicks the toggle up to a few times; aborts if it never engages."""
        if not self.cfg.target.enable_browsing:
            return
        ok = self._click_enable_browsing_toggle(self.page)
        self.shot("target-enable-browsing")
        if not ok:
            raise AssertionError(
                "Could not enable 'Enable Browsing' on the target — see "
                f"{self.cfg.screenshot_dir}/target-enable-browsing.png")
        print("[target] Enable Browsing turned ON")

    @staticmethod
    def _click_enable_browsing_toggle(p, attempts: int = 6) -> bool:
        """Click the 'Enable Browsing' toggle knob until it reads ON.
        Returns True if enabled."""
        lbl = p.get_by_text(re.compile(r"^\s*Enable Browsing\s*$", re.I)).first
        try:
            lbl.scroll_into_view_if_needed()
        except Exception:
            pass
        row = lbl.locator("xpath=ancestor::*[contains(@class,'d-flex')][1]")

        def is_on() -> bool:
            # checkbox state
            try:
                inp = row.locator("input[type='checkbox']").first
                if inp.count() and inp.is_checked():
                    return True
            except Exception:
                pass
            # class on the switch (color change)
            try:
                cls = (row.locator(".c-switch-container .switch").first.get_attribute("class")
                       or "").lower()
                if any(k in cls for k in ("checked", "active", "enabled", "on ")):
                    return True
            except Exception:
                pass
            return False

        candidates = [
            row.locator(".c-switch-container .switch span").first,
            row.locator(".c-switch-container .switch div").first,
            row.locator(".c-switch-container").first,
            p.locator(".c-switch-container > .switch > div > span").first,
        ]
        for _ in range(attempts):
            if is_on():
                return True
            for el in candidates:
                try:
                    el.click(timeout=3000, force=True)
                    p.wait_for_timeout(800)
                    if is_on():
                        return True
                    break
                except Exception:
                    continue
        return is_on()

    def _create_secret(self, t):
        """Object store credentials: open the create-secret form, fill secret
        name + keys, Create. Then ensure the new secret is selected.

        The button label depends on whether the namespace already has secrets:
          - no existing secrets -> 'Create New Secret'
          - existing secrets    -> 'Create New' (next to the secret selector)
        """
        p = self.page
        secret_name = f"{t.name}-secret"

        btn = p.get_by_role("button", name=re.compile(r"^\s*Create New Secret\s*$", re.I)).first
        if not btn.is_visible(timeout=2000):
            # existing secrets present -> the button is just 'Create New'.
            # The credentials step holds TWO of them — one under 'Object store
            # credentials', one under 'Certificate ConfigMap' — plus a page-level
            # 'Create New' sitting behind the modal. Scope to the dialog and take
            # the first: that is the credentials one. '.last' opens the ConfigMap
            # sub-form instead, and the secret fields never appear.
            dialog = p.locator(".modal-dialog, [role='dialog']").first
            btn = dialog.get_by_role("button", name="Create New", exact=True).first
        btn.click()
        p.wait_for_timeout(1000)
        self.shot("target-secret-form")

        print(f"[targets] secret '{secret_name}' using config creds "
              f"(access_key len={len(t.access_key)}, secret_key len={len(t.secret_key)})")
        p.get_by_role("textbox", name=re.compile(r"Enter Secret Name|Secret Name", re.I)).fill(
            secret_name)
        p.get_by_role("textbox", name=re.compile(r"Access Key", re.I)).fill(t.access_key)
        p.get_by_role("textbox", name=re.compile(r"Secret Key", re.I)).fill(t.secret_key)
        self.shot("target-secret-filled")

        # Create the secret (its own Create button), returns to the main form
        p.get_by_role("button", name="Create", exact=True).click()
        p.wait_for_timeout(2000)
        self.shot("target-secret-created")

        # When the namespace already had secrets, the new one is NOT
        # auto-selected — select it explicitly and wait for the tick.
        self._ensure_secret_selected(secret_name)

    def _secret_selected(self) -> bool:
        """Selected when the 'credential required' error is gone and Continue
        is enabled (the green tick in front of the secret)."""
        p = self.page
        try:
            if p.get_by_text(re.compile(r"credential.*required", re.I)).first.is_visible(
                    timeout=800):
                return False
        except Exception:
            pass
        return self.find_enabled_button(r"^\s*continue\s*$") is not None

    def _ensure_secret_selected(self, secret_name: str):
        """If the new secret isn't auto-selected (other secrets exist), click
        it and wait for the selection tick (Continue enabling)."""
        p = self.page
        if self._secret_selected():
            print(f"[targets] Secret '{secret_name}' auto-selected")
            return

        pat = re.compile(rf"^\s*{re.escape(secret_name)}\s*$", re.I)
        for attempt in range(4):
            try:
                entry = p.get_by_text(pat).last
                if not entry.is_visible(timeout=2000):
                    # expand the namespace group in the secret list
                    grp = p.get_by_text(re.compile(r"^\s*Namespace:", re.I)).last
                    if grp.is_visible(timeout=1500):
                        grp.scroll_into_view_if_needed()
                        grp.click()
                        p.wait_for_timeout(800)
                    entry = p.get_by_text(pat).last
                entry.scroll_into_view_if_needed()
                entry.click()
                # wait for the tick / Continue to enable
                for _ in range(8):
                    p.wait_for_timeout(1000)
                    if self._secret_selected():
                        self.shot("target-secret-selected")
                        print(f"[targets] Secret '{secret_name}' selected")
                        return
            except Exception:
                pass
            self.shot(f"target-secret-select-{attempt + 1}")
            print(f"[targets] secret select attempt {attempt + 1} not confirmed — retrying")
        print(f"[targets] WARNING: could not confirm selection of '{secret_name}'")

    def verify_target_available(self):
        self.open()
        self.wait_for_status(self.cfg.target.name, "Available", timeout_s=600)
        self.shot("target-available")
        if self.cfg.target.enable_browsing:
            self.verify_browsing_enabled()

    def verify_browsing_enabled(self, timeout_s: int = 600):
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
                    self.shot("target-browsing-enabled")
                    print(f"[target] '{name}' browsing column shows Enabled")
                    return
            except Exception:
                pass
            remaining = int(deadline - time.time())
            print(f"[target] waiting for browsing to show Enabled... {remaining}s left")
            p.wait_for_timeout(10000)
        self.shot("target-browsing-not-enabled")
        raise AssertionError(
            f"Target '{name}' browsing did not show Enabled within {timeout_s}s")
