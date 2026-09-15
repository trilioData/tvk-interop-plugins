"""Custom-transformation restore page — SEPARATE from restore_page.py and
restore_helm_trans_page.py. It SUBCLASSES RestoreHelmTransPage purely to reuse
the (already working) helpers: open(), _select_namespace(), the target-browsing
enable+sync wait, and the create-restore-with-confirm walk. Nothing in the helm
page is modified.

Custom transform applies to a NAMESPACE-based backup (not Helm). Flow
(per custom-trans-click-test.spec.ts + UI guidance):
  Backup Plans -> open plan -> View Backups -> Restore
  Basic: Name + Restore Namespace -> Next -> (Resource Selector) Next ->
  Transform Components (3rd step)
  Enable target browsing (if needed) and WAIT for the sync to finish.
  Add Transform Components -> ensure type 'Custom' (default) ->
  search 'pers' -> select 'PersistentVolumeClaim' -> click the '+' add icon ->
  fill Transform Name -> Path dropdown '/spec/storageClassName' ->
  Value = "<storage-class>" (in double quotes) -> Apply -> Apply ->
  walk to Create Restore (+ confirmation dialog).
"""
import re
import time

from pages.base_page import settle
from pages.restore_helm_trans_page import RestoreHelmTransPage


class RestoreCustomTransPage(RestoreHelmTransPage):

    def restore_with_transform(self, storage_class: str, resource: str = "PersistentVolumeClaim",
                               path: str = "/spec/storageClassName"):
        c = self.cfg
        p = self.page
        plan = c.restore_from_plan or c.backupplan_name
        restore_ns = c.restore_target_namespace or c.restore_ns()

        self.open()

        # Open the plan -> View Backups -> Restore (same as the helm flow)
        p.get_by_role("link", name=re.compile(rf"^{re.escape(plan)}$", re.I)).first.click()
        p.wait_for_timeout(1500)
        p.get_by_role("button", name=re.compile(r"View Backups", re.I)).first.click()
        p.wait_for_timeout(1500)
        p.get_by_role("button", name=re.compile(r"^\s*Restore\s*$", re.I)).first.click()
        p.wait_for_timeout(2500)
        self.shot("crt-restore-open")

        # Basic: Name + Restore Namespace (no helm-only retain flag here)
        p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first.fill(c.restore_name)
        self._select_namespace(restore_ns)

        # Next -> Resource Selector -> Next -> Transform Components
        p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(2000)
        p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(2500)
        self.shot("crt-transform-step")

        # Enable target browsing + wait for sync (reused from the helm page)
        self._enable_browsing_and_wait()

        # Add Transform Components
        add = (p.get_by_role("link", name=self._ADD_TF).first
               if p.get_by_role("link", name=self._ADD_TF).count()
               else p.get_by_text(self._ADD_TF).first)
        try:
            add.click(timeout=8000)
        except Exception:
            add.click(timeout=8000, force=True)
        p.wait_for_timeout(1500)
        self.shot("crt-add-transform")

        # Ensure the transformation type is 'Custom' (it is the default; the
        # helm flow switches it to Helm). Best-effort — if there is no type
        # dropdown for a namespace backup, the search box appears directly.
        self._ensure_type_custom()

        # Search for the resource kind and select it
        search = p.get_by_test_id("restore-wizard-container").get_by_role(
            "textbox", name=re.compile(r"Search", re.I)).first
        search.click()
        search.fill(resource[:4].lower())   # 'pers'
        p.wait_for_timeout(1200)
        p.get_by_role("cell", name=re.compile(rf"^\s*{re.escape(resource)}\s*$", re.I)).first.click()
        p.wait_for_timeout(800)
        self.shot("crt-resource-selected")

        # Click the '+' add-transform icon to open the transform-details panel
        try:
            p.locator(".c-pointer.fg-primary.add-transform-icon > path").first.click(timeout=6000)
        except Exception:
            p.locator(".add-transform-icon").first.click(timeout=6000, force=True)
        p.wait_for_timeout(1200)
        self.shot("crt-transform-panel")

        # Transform Name
        tn = p.get_by_role("textbox", name=re.compile(r"Transform Name", re.I)).first
        tn.wait_for(state="visible", timeout=10000)
        tn.click()
        tn.fill(c.transform_name)
        p.wait_for_timeout(400)
        if (tn.input_value() or "").strip() != c.transform_name:
            tn.fill(c.transform_name)
        print(f"[custom_trans] transform name = '{tn.input_value()}'")

        # Path dropdown ('/spec/storageClassName'). Options load async, so open
        # the dropdown, type to filter, and wait for the option before clicking.
        self._select_path(path)

        # Value = the storage class name, wrapped in DOUBLE QUOTES (per UI)
        val = f'"{storage_class}"'
        vbox = p.get_by_role("textbox", name=re.compile(r"^\s*Value\s*$", re.I)).first
        vbox.click()
        vbox.fill(val)
        p.wait_for_timeout(400)
        if (vbox.input_value() or "").strip() != val:
            vbox.fill(val)
        self.shot("crt-value-filled")
        print(f"[custom_trans] path='{path}' value={val}")
        # re-assert the name in case focus changes reset it
        if (tn.input_value() or "").strip() != c.transform_name:
            tn.fill(c.transform_name)

        # Apply (transform detail) -> Apply (add the component)
        for _ in range(2):
            btn = self.find_enabled_button(r"^\s*Apply\s*$")
            if btn is None:
                break
            try:
                btn.click(timeout=5000)
            except Exception:
                btn.click(timeout=5000, force=True)
            p.wait_for_timeout(1500)
        self.shot("crt-applied")

        # Commit the component if an 'Add' button is present, then walk to
        # Create Restore (reuse the helm page's confirm-dialog walk).
        btn = self.find_enabled_button(r"^\s*Add\s*$")
        if btn is not None:
            try:
                btn.click(timeout=5000)
                p.wait_for_timeout(1500)
            except Exception:
                pass
        self.shot("crt-transform-added")

        self._walk_to_create_restore()

    # ---------- helpers (custom-specific) ----------

    def _ensure_type_custom(self):
        """Make sure the Transformation Type is 'Custom'. For a namespace
        backup it is the default, so this is best-effort — open the type
        dropdown only if one is present and pick Custom."""
        p = self.page
        try:
            # if 'Custom' already shows as the selected type, nothing to do
            if p.get_by_test_id("restore-wizard-container").get_by_text(
                    re.compile(r"^\s*Custom\s*$", re.I)).first.is_visible(timeout=1500):
                self.shot("crt-type-custom")
                return
        except Exception:
            pass
        try:
            p.locator("div").filter(has_text=re.compile(r"^Helm$")).nth(2).click(timeout=3000)
            p.wait_for_timeout(500)
            p.get_by_test_id("restore-wizard-container").get_by_text(
                "Custom", exact=True).click(timeout=3000)
            p.wait_for_timeout(800)
            self.shot("crt-type-custom")
        except Exception as e:
            print(f"[custom_trans] type dropdown not needed/visible ({e})")

    def _path_input(self):
        """The react-select INPUT for the 'Path' field inside JSON PATCHES.
        Anchored to the 'Path' label so we never grab the 'Objects' dropdown
        at the top of the panel."""
        p = self.page
        lbl = p.get_by_text(re.compile(r"^\s*Path\s*\*?\s*$", re.I)).last
        # the react-select control sits in the same row as the label; its input
        # is the next react-select input following the label in the DOM
        inp = lbl.locator(
            "xpath=following::input[starts-with(@id,'react-select')][1]")
        return inp

    def _path_selected(self, path: str) -> bool:
        """True once `path` is the selected value of the Path field. The value
        renders inside the react-select control (not as a plain text node and
        not necessarily as an input value), so check several ways.

        Accepts the leaf key as well as the full JSON-pointer: some builds list
        and display the options as '/spec/storageClassName', others as just
        'storageClassName'. Only matching the full form reports 'not selected'
        even when the console has committed the choice."""
        p = self.page
        tail = path.split("/")[-1]
        forms = [f for f in (path, tail) if f]

        for form in forms:
            # 1) selected value shown as text somewhere (single-value div)
            try:
                if p.get_by_text(form, exact=True).first.is_visible(timeout=800):
                    return True
            except Exception:
                pass
            # 2) the Path input carries the value
            try:
                if (self._path_input().input_value() or "").strip() == form:
                    return True
            except Exception:
                pass
        # 3) the JSON PATCHES panel text contains the path (either form)
        try:
            panel = p.get_by_text(re.compile(r"JSON PATCHES", re.I)).locator(
                "xpath=ancestor::*[self::div][2]")
            text = panel.inner_text(timeout=1500) or ""
            if any(f in text for f in forms):
                return True
        except Exception:
            pass
        return False

    def _wait_for_options(self, tail: str, timeout_s: int = 20):
        """Wait for the react-select menu to actually populate.

        The Path/Value option lists are fetched asynchronously and can take
        several seconds. A fixed sleep races that: if the menu is still empty
        (react-select renders 'No options') there is nothing to click and Enter
        commits nothing, so the field silently stays unset. Returns the matching
        option locator, or None if the menu never filled."""
        p = self.page
        import time as _t
        deadline = _t.time() + timeout_s
        while _t.time() < deadline:
            try:
                if p.get_by_text(re.compile(r"^\s*No options\s*$", re.I)).first.is_visible(
                        timeout=400):
                    p.wait_for_timeout(1000)
                    continue
            except Exception:
                pass
            opt = p.locator(
                "[class*='option' i], [role='option']").filter(
                    has_text=re.compile(re.escape(tail), re.I)).last
            try:
                if opt.is_visible(timeout=600):
                    return opt
            except Exception:
                pass
            p.wait_for_timeout(800)
        return None

    def _select_path(self, path: str):
        """Open the JSON-path react-select for the Path field and pick `path`.
        Options load async, so retry. We type the full key tail (e.g.
        'storageClassName') to filter precisely, then click the exact option
        (falling back to keyboard Enter on the highlighted match)."""
        p = self.page
        tail = path.split("/")[-1]          # 'storageClassName'
        for attempt in range(6):
            if self._path_selected(path):
                self.shot("crt-path-selected")
                print(f"[custom_trans] path '{path}' already selected")
                return
            try:
                inp = self._path_input()
                inp.wait_for(state="attached", timeout=4000)
                inp.click(timeout=4000)
                p.wait_for_timeout(500)
                inp.fill("")
                inp.type(tail, delay=30)    # filter to the exact key
                # Wait for the menu to fill instead of sleeping a fixed amount:
                # these options load async and can lag several seconds.
                menu_opt = self._wait_for_options(tail)
                # the menu is in a portal — prefer the exact full-path option
                opt = p.get_by_text(path, exact=True).last
                if opt.is_visible(timeout=1500):
                    opt.click(timeout=4000)
                elif menu_opt is not None:
                    menu_opt.click(timeout=4000)
                else:
                    # last resort: the filtered match may be highlighted
                    inp.press("Enter")
                p.wait_for_timeout(800)
                if self._path_selected(path):
                    self.shot("crt-path-selected")
                    print(f"[custom_trans] selected path '{path}'")
                    return
            except Exception as e:
                print(f"[custom_trans] path-select attempt {attempt + 1} ({e})")
            p.wait_for_timeout(1500)
        self.shot("crt-path-select-failed")
        raise AssertionError(
            f"Could not select transform path '{path}' — see "
            f"{self.cfg.screenshot_dir}/crt-path-select-failed.png")

    def _walk_to_create_restore(self):
        """Next -> Hook Confirmation -> Create Restore (+ confirm dialog).
        Same robust walk as the helm flow."""
        p = self.page
        deadline = time.time() + 120
        created = False
        while time.time() < deadline:
            cr = (self.find_enabled_button(r"^\s*Create Restore\s*$")
                  or self.find_enabled_button(r"^\s*Create\s*$"))
            if cr is not None:
                cr.click()
                p.wait_for_timeout(1500)
                self.shot("crt-create-clicked")
                for _ in range(5):
                    confirm = self.find_enabled_button(r"^\s*Create Restore\s*$")
                    if confirm is not None:
                        confirm.click()
                        p.wait_for_timeout(1500)
                        self.shot("crt-create-confirmed")
                        break
                    p.wait_for_timeout(1000)
                created = True
                break
            nxt = self.find_enabled_button(r"^\s*Next\s*$")
            if nxt is not None:
                nxt.click()
                p.wait_for_timeout(1500)
                continue
            p.wait_for_timeout(1500)
        settle(p)
        self.shot("crt-restore-started")
        if not created:
            raise AssertionError(
                "Restore was NOT started — 'Create Restore' never became "
                f"clickable. See {self.cfg.screenshot_dir}/crt-restore-started.png")
