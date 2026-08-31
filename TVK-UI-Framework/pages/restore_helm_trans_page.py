"""Helm-transformation restore page — fully separate from restore_page.py.

Flow (per helm_trans_rest.spec.js + UI guidance):
  Backup Plans -> open plan -> View Backups -> Restore
  Basic: Name, Restore Namespace, expand 'Restore Flags' -> enable
         'retainHelmReleaseName'
  Next -> Resource Selector -> Next -> Transform Components (3rd page)
  Enable target browsing (if not enabled) and WAIT for the sync to finish
  (can take 10-15 min). Then 'Add Transform' -> Transformation Type = Helm ->
  Transform Name + values editor (Monaco) -> Apply.
  Walk to 'Create Restore'.
"""
import re
import time

from pages.base_page import BasePage, settle


class RestoreHelmTransPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def restore_with_transform(self):
        c = self.cfg
        p = self.page
        plan = c.restore_from_plan or c.backupplan_name
        restore_ns = c.restore_target_namespace or c.restore_ns()

        self.open()

        # Open the plan -> View Backups -> Restore
        p.get_by_role("link", name=re.compile(rf"^{re.escape(plan)}$", re.I)).first.click()
        p.wait_for_timeout(1500)
        p.get_by_role("button", name=re.compile(r"View Backups", re.I)).first.click()
        p.wait_for_timeout(1500)
        p.get_by_role("button", name=re.compile(r"^\s*Restore\s*$", re.I)).first.click()
        p.wait_for_timeout(2500)
        self.shot("hrt-restore-open")

        # Basic: Name + Restore Namespace
        p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first.fill(c.restore_name)
        self._select_namespace(restore_ns)

        # Restore Flags -> enable retainHelmReleaseName
        try:
            p.get_by_role("button", name=re.compile(r"Restore Flags", re.I)).first.click()
            p.wait_for_timeout(1000)
            lbl = p.get_by_text(re.compile(r"^\s*retainHelmReleaseName\s*$", re.I)).first
            sw = lbl.locator("xpath=following::*[self::label or @role='switch' "
                             "or contains(@class,'switch')][1]")
            sw.click()
            p.wait_for_timeout(800)
            self.shot("hrt-retain-enabled")
        except Exception as e:
            print(f"[helm_trans] retainHelmReleaseName toggle issue ({e})")

        # Next -> Resource Selector -> Next -> Transform Components
        p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(2000)
        p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(2500)
        self.shot("hrt-transform-step")

        # Enable target browsing + wait for sync (10-15 min)
        self._enable_browsing_and_wait()

        # Add Transform Components -> Transformation Type = Helm (anchored
        # match so it doesn't hit the 'to add Transform Component' message)
        add = (p.get_by_role("link", name=self._ADD_TF).first
               if p.get_by_role("link", name=self._ADD_TF).count()
               else p.get_by_text(self._ADD_TF).first)
        try:
            add.click(timeout=8000)
        except Exception:
            add.click(timeout=8000, force=True)
        p.wait_for_timeout(1500)
        self.shot("hrt-add-transform")
        self._pick_type_helm()

        # Transform Name — appears after the helm accordion expands; wait for
        # it, fill, and verify it took.
        tn = p.get_by_role("textbox", name=re.compile(r"Transform Name", re.I)).first
        tn.wait_for(state="visible", timeout=10000)
        tn.click()
        tn.fill(c.transform_name)
        p.wait_for_timeout(400)
        if (tn.input_value() or "").strip() != c.transform_name:
            tn.fill(c.transform_name)
        self.shot("hrt-transform-name")
        print(f"[helm_trans] transform name = '{tn.input_value()}'")

        # The editor loads the chart values asynchronously (spinner). WAIT for
        # it to finish (view-lines populated) before setting our value — else
        # the load overwrites whatever we set.
        import time as _t
        edl = _t.time() + 120
        loaded = False
        while _t.time() < edl:
            try:
                txt = p.locator(".view-lines").first.inner_text(timeout=2000)
                if txt and len(txt.strip()) > 10 and ":" in txt:
                    loaded = True
                    break
            except Exception:
                pass
            print("[helm_trans] waiting for values editor to load...")
            p.wait_for_timeout(3000)
        if not loaded:
            self.shot("hrt-editor-not-loaded")
            raise AssertionError("Values editor did not load the chart values in time")
        self.shot("hrt-editor-loaded")

        # Set the value. Prefer the Monaco API (exact text). If window.monaco
        # isn't exposed, focus the hidden textbox (focus() avoids the token-span
        # click interception) and use keyboard.insertText, which inserts the
        # whole string in ONE event — no per-key auto-indent (unlike type()),
        # so the YAML stays valid.
        set_ok = False
        try:
            set_ok = p.evaluate(
                """(val) => {
                    const m = window.monaco;
                    if (m && m.editor && m.editor.getModels) {
                        const models = m.editor.getModels();
                        if (models && models.length) {
                            models[models.length - 1].setValue(val);
                            return true;
                        }
                    }
                    return false;
                }""", c.transform_helm_values)
        except Exception as e:
            print(f"[helm_trans] monaco setValue failed ({e})")
        if not set_ok:
            # PASTE the value — Monaco preserves pasted indentation, whereas
            # type()/fill()/insert_text() all trigger auto-indent and corrupt
            # the YAML. Put the value on the clipboard, then Ctrl+A + Ctrl+V.
            try:
                p.context.grant_permissions(["clipboard-read", "clipboard-write"])
            except Exception:
                pass
            try:
                p.evaluate("(v) => navigator.clipboard.writeText(v)",
                           c.transform_helm_values)
                editor = p.get_by_role("textbox", name=re.compile(r"Editor content", re.I)).first
                editor.focus()
                p.wait_for_timeout(200)
                p.keyboard.press("ControlOrMeta+a")
                p.keyboard.press("Delete")
                p.keyboard.press("ControlOrMeta+v")
            except Exception as e:
                print(f"[helm_trans] editor paste failed ({e})")
        p.wait_for_timeout(800)

        # Verify the edit actually landed, and fall back if not. Both routes
        # above can silently no-op: window.monaco isn't exposed on every build,
        # and navigator.clipboard only exists in a secure context — plain http on
        # a non-localhost origin (e.g. a port-forward to a VM) leaves it
        # undefined. When that happens the console keeps the original chart
        # values, treats the YAML as unedited, and never enables 'Create
        # Restore'. insert_text needs neither: it delivers the whole string in a
        # single event, so Monaco's per-key auto-indent can't corrupt the YAML.
        marker = ""
        for line in reversed(c.transform_helm_values.strip().splitlines()):
            if line.strip():
                marker = line.strip()
                break

        def _editor_text():
            # The page hosts more than one Monaco instance (the transform editor
            # plus the read-only 'View YAML' one), and '.first' is not reliably
            # the visible transform editor — checking only that one reports the
            # edit as missing even after it landed. Concatenate them all.
            try:
                loc = p.locator(".view-lines")
                n = min(loc.count(), 6)
                parts = []
                for i in range(n):
                    try:
                        parts.append(loc.nth(i).inner_text(timeout=1500) or "")
                    except Exception:
                        continue
                return " ".join(parts)
            except Exception:
                return ""

        if marker and marker.replace('"', "") not in _editor_text().replace('"', ""):
            print("[helm_trans] editor unchanged after setValue/paste — "
                  "falling back to insert_text")
            try:
                editor = p.get_by_role("textbox", name=re.compile(r"Editor content", re.I)).first
                editor.focus()
                p.wait_for_timeout(200)
                p.keyboard.press("ControlOrMeta+a")
                p.keyboard.press("Delete")
                p.keyboard.insert_text(c.transform_helm_values)
                p.wait_for_timeout(800)
            except Exception as e:
                print(f"[helm_trans] editor insert_text failed ({e})")

        # Advisory only. Reading Monaco's rendered text is unreliable — it
        # virtualises lines and the page hosts several editor instances — so a
        # negative result here does NOT mean the edit failed. The authoritative
        # gate is whether the console enables Apply / 'Create Restore', which is
        # checked below; don't fail the run on this signal alone.
        if marker and marker.replace('"', "") not in _editor_text().replace('"', ""):
            self.shot("hrt-editor-readback-empty")
            print(f"[helm_trans] note: could not read '{marker}' back from the "
                  "editor DOM; relying on the console's own validation")
        else:
            print(f"[helm_trans] values editor now contains '{marker}'")

        # re-assert the Transform Name in case the editor edit reset it
        if (tn.input_value() or "").strip() != c.transform_name:
            tn.fill(c.transform_name)
        self.shot("hrt-transform-filled")

        # Bail out clearly if the YAML is still flagged invalid (so we don't
        # claim the restore started when it can't).
        try:
            if p.get_by_text(re.compile(r"not in the supported format", re.I)).first.is_visible(
                    timeout=2000):
                self.shot("hrt-yaml-invalid")
                raise AssertionError(
                    "Transform YAML rejected ('not in the supported format') — see "
                    f"{self.cfg.screenshot_dir}/hrt-yaml-invalid.png")
        except AssertionError:
            raise
        except Exception:
            pass

        # Apply (TRANSFORM CONFIGURATION -> back to Add Transform Component)
        btn = self.find_enabled_button(r"^\s*Apply\s*$")
        if btn is not None:
            btn.click()
            p.wait_for_timeout(1500)
        self.shot("hrt-applied")

        # Add (commit the transform component -> back to Transform Components)
        btn = self.find_enabled_button(r"^\s*Add\s*$")
        if btn is not None:
            btn.click()
            p.wait_for_timeout(1500)
        self.shot("hrt-transform-added")

        # Next -> Hook Confirmation -> Create Restore. Poll so a disabled
        # button (briefly) doesn't make us give up.
        import time as _t
        deadline = _t.time() + 120
        created = False
        while _t.time() < deadline:
            cr = (self.find_enabled_button(r"^\s*Create Restore\s*$")
                  or self.find_enabled_button(r"^\s*Create\s*$"))
            if cr is not None:
                cr.click()
                p.wait_for_timeout(1500)
                self.shot("hrt-create-clicked")
                # A confirmation dialog appears: "Are you sure you want to
                # create restore?" -> click its 'Create Restore' button.
                for _ in range(5):
                    confirm = self.find_enabled_button(r"^\s*Create Restore\s*$")
                    if confirm is not None:
                        confirm.click()
                        p.wait_for_timeout(1500)
                        self.shot("hrt-create-confirmed")
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
        self.shot("hrt-restore-started")
        if not created:
            raise AssertionError(
                "Restore was NOT started — 'Create Restore' never became "
                f"clickable. See {self.cfg.screenshot_dir}/hrt-restore-started.png")

    # ---------- helpers ----------

    def _select_namespace(self, namespace):
        """Select the restore namespace. The dropdown loads its options
        asynchronously (shows a spinner) and is disabled until ready, so wait
        for it to be enabled, then type-to-filter and pick the option. Retries."""
        p = self.page
        ns_trigger = p.get_by_text(re.compile(r"select\s*namespace", re.I)).last
        # wait until the dropdown control is actually enabled (spinner gone)
        import time as _t
        deadline = _t.time() + 60
        while _t.time() < deadline:
            try:
                if ns_trigger.is_visible(timeout=1500) and ns_trigger.is_enabled():
                    break
            except Exception:
                pass
            p.wait_for_timeout(2000)
        for attempt in range(4):
            try:
                ns_trigger.click(timeout=5000)
                p.wait_for_timeout(700)
                rs = p.locator("input[id^='react-select'][id$='-input']").last
                if rs.is_visible(timeout=1500):
                    rs.fill(namespace[:8])
                    p.wait_for_timeout(900)
                opt = p.get_by_text(namespace, exact=True).last
                if not opt.is_visible(timeout=2500):
                    opt = p.locator("[role='option'], .ant-select-item, li").first
                opt.click(timeout=5000)
                p.wait_for_timeout(500)
                self.shot("hrt-namespace-selected")
                return
            except Exception as e:
                print(f"[helm_trans] namespace select attempt {attempt + 1} ({e})")
                p.wait_for_timeout(2000)
        print(f"[helm_trans] WARNING: could not select namespace '{namespace}'")

    # 'Add Transform Component(s)' control — anchored so it does NOT match the
    # message 'Please enable target browsing to add Transform Component'.
    _ADD_TF = re.compile(r"^\s*Add Transform\s*Components?\s*$", re.I)

    def _browsing_needed(self) -> bool:
        try:
            return self.page.get_by_text(
                re.compile(r"Please enable target browsing", re.I)).first.is_visible(timeout=1500)
        except Exception:
            return False

    def _add_transform_ready(self) -> bool:
        try:
            return self.page.get_by_text(self._ADD_TF).first.is_visible(timeout=1500)
        except Exception:
            return False

    def _browsing_syncing(self) -> bool:
        try:
            return self.page.get_by_text(re.compile(
                r"browsing is in progress|Target browser is syncing|"
                r"syncing the details|try after some time",
                re.I)).first.is_visible(timeout=1500)
        except Exception:
            return False

    def _enable_browsing_and_wait(self):
        """Two cases:
          - browsing already enabled -> 'Add Transform' control is present.
          - not enabled -> toggle to enable (often needs TWO clicks), the target
            syncs (5-10 min); wait for 'Add Transform' before aborting.
        """
        p = self.page
        if self._add_transform_ready() and not self._browsing_needed():
            self.shot("hrt-browsing-already")
            return

        # Click the toggle KNOB (span inside .switch) — same structure that
        # works for the target 'Enable Browsing' toggle. Retry a few times.
        candidates = [
            p.locator("[data-testid='toggle-button-container'] .switch div span").first,
            p.locator("[data-testid='toggle-button-container'] .switch span").first,
            p.locator("[data-testid='toggle-button-container'] .switch").first,
            p.locator("[data-testid='toggle-button-container']").first,
            p.locator(".c-switch-container > .switch > div > span").first,
        ]
        for attempt in range(6):
            if self._browsing_syncing() or self._add_transform_ready():
                break
            for el in candidates:
                try:
                    el.click(timeout=3000, force=True)
                    p.wait_for_timeout(1500)
                    break
                except Exception:
                    continue
            self.shot(f"hrt-browsing-toggle-{attempt + 1}")
            print(f"[helm_trans] toggle click attempt {attempt + 1}")
            if self._browsing_syncing() or self._add_transform_ready():
                break
        if not (self._browsing_syncing() or self._add_transform_ready()):
            self.shot("hrt-browsing-toggle-failed")
            raise AssertionError(
                "Could not enable target browsing (toggle did not engage). The "
                "target likely needs 'Enable Browsing' set at creation time — "
                f"see {self.cfg.screenshot_dir}/hrt-browsing-toggle-failed.png")

        # Wait for the sync to finish. The page shows "syncing... try after
        # some time" and may NOT auto-refresh, so every ~45s re-render the
        # Transform Components step (Back -> Next) and re-check for Add Transform.
        deadline = time.time() + self.cfg.operation_timeout_s
        cycle = 0
        while time.time() < deadline:
            if self._add_transform_ready() and not self._browsing_needed():
                self.shot("hrt-browsing-done")
                return
            cycle += 1
            if cycle % 3 == 0:   # ~ every 45s, refresh the step view
                try:
                    p.get_by_role("button", name=re.compile(r"^\s*Back\s*$", re.I)).first.click(timeout=4000)
                    p.wait_for_timeout(1500)
                    p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click(timeout=4000)
                    p.wait_for_timeout(2500)
                    self.shot("hrt-browsing-refresh")
                except Exception:
                    pass
            remaining = int(deadline - time.time())
            print(f"[helm_trans] waiting for target browsing to sync... {remaining}s left")
            p.wait_for_timeout(15000)
        raise TimeoutError("Target browsing did not finish — cannot add helm transform")

    def _pick_type_helm(self):
        """Per codegen: open the Transformation Type dropdown (shows 'Custom'),
        pick 'Helm' inside restore-wizard-container, then expand the helm
        component accordion to reveal the Transform Name + values editor."""
        p = self.page
        # open the dropdown (the control shows 'Custom')
        try:
            p.locator("div").filter(
                has_text=re.compile(r"^Custom$")).nth(2).click(timeout=5000)
        except Exception:
            try:
                p.get_by_text(re.compile(r"^\s*Custom\s*$", re.I)).first.click(timeout=5000)
            except Exception as e:
                print(f"[helm_trans] could not open Transformation Type ({e})")
        p.wait_for_timeout(700)
        # pick 'Helm' inside the restore wizard container
        try:
            p.get_by_test_id("restore-wizard-container").get_by_text(
                "Helm", exact=True).click(timeout=5000)
        except Exception:
            p.get_by_text(re.compile(r"^\s*Helm\s*$", re.I)).last.click(timeout=5000, force=True)
        p.wait_for_timeout(1200)
        self.shot("hrt-type-helm")
        # expand the helm component accordion -> reveals Transform Name + editor
        try:
            p.locator(
                ".helm-component-accordion > .d-flex > .icon-container > .c-pointer"
            ).first.click(timeout=5000)
            p.wait_for_timeout(1200)
        except Exception:
            # fallback: click the release row / any accordion toggle
            try:
                p.locator(".helm-component-accordion .c-pointer").first.click(timeout=4000)
                p.wait_for_timeout(1200)
            except Exception as e:
                print(f"[helm_trans] could not expand helm component accordion ({e})")
        self.shot("hrt-helm-accordion")
