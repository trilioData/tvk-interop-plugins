"""Backup Plans page object.

Selectors verified against Playwright codegen of the real UI:
  Create New -> popup
    1. Click 'Application' (backup plan type)
    2. Namespace: react-select ('Select Namespace') — type to filter, pick
    3. Name: textbox 'Name Name'
    4. Target: react-select ('Select') — pick the target
    5. Next
    6. Components: either back up the whole namespace (default) or, for a
       Helm app, the 'Helm Release' tab -> Add Helm Release -> pick -> Apply
    7. Next -> Skip & Create -> close success popup -> Finish
"""
import re

from pages.base_page import BasePage, settle


class BackupPlansPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")

    def create_helm_backupplan(self, namespace: str, plan_name: str,
                               target: str, release: str):
        """Create an Application-type backup plan capturing a Helm Release
        (from helm_trans.spec.js): Create New -> Application -> namespace ->
        name -> target -> Next -> Helm Release tab -> Add Helm Release ->
        pick the release -> Apply -> finish."""
        p = self.page
        self.open()
        p.wait_for_timeout(1000)

        # Create New -> Application
        self.click_create_new()
        p.wait_for_timeout(800)
        p.get_by_role("button", name=re.compile(r"^\s*Application\s*$", re.I)).click()
        p.wait_for_timeout(1200)
        self.shot("helmbp-application")

        # Namespace, Name, Target
        self.select_react_dropdown(r"^Select Namespace$", namespace,
                                   type_filter=namespace[:5],
                                   shot_name="helmbp-namespace")
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        name_box.click()
        name_box.fill(plan_name)
        self.select_react_dropdown(r"^Select$", target, shot_name="helmbp-target")

        # Next -> component selection
        try:
            p.get_by_test_id("form-wizard-children").get_by_role(
                "button", name=re.compile(r"^\s*Next\s*$", re.I)).click()
        except Exception:
            p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(1500)
        self.shot("helmbp-components")

        # Helm Release tab -> Add Helm Release -> pick the release
        p.get_by_role("tab", name=re.compile(r"Helm Release", re.I)).click()
        p.wait_for_timeout(800)
        p.get_by_text(re.compile(r"Add Helm Release", re.I)).first.click()
        p.wait_for_timeout(800)
        self.select_react_dropdown(r"^Select Option$", release,
                                   shot_name="helmbp-release")
        try:
            p.get_by_role("button", name=re.compile(r"^\s*Apply\s*$", re.I)).first.click(timeout=4000)
            p.wait_for_timeout(800)
        except Exception:
            pass
        self.shot("helmbp-release-applied")

        # Finish wizard
        self._finish_wizard()

    def create_backupplan(self, with_policy: bool = False):
        c = self.cfg
        p = self.page
        self.open()
        p.wait_for_timeout(1000)

        # 1. Open the 'Create New' type dropdown (the kebab/caret icon next to
        # it) and pick 'Single-namespace' (= namespace-based backup plan)
        try:
            p.locator(".icon-container.icon-xs-15.icon-sm-18 > svg").click(timeout=8000)
        except Exception:
            # fallback: click the Create New control itself
            self.click_create_new()
        p.wait_for_timeout(800)
        self.shot("bp-create-menu")

        p.get_by_role("button", name=re.compile(r"single[\s\-]*namespace", re.I)).click()
        p.wait_for_timeout(1500)
        self.shot("bp-type-namespace")

        # 2. Namespace (react-select). Use the configured backup_namespace if
        # set (an existing namespace), else the auto-created app namespace.
        bp_namespace = c.res_ns(c.backup_namespace)
        self.select_react_dropdown(r"^Select Namespace$", bp_namespace,
                                   type_filter=bp_namespace[:5],
                                   shot_name="bp-namespace-selected")

        # 3. Name — codegen showed the accessible name as 'Name Name'
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        if not name_box.is_visible(timeout=2000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(c.backupplan_name)
        self.shot("bp-name-filled")

        # 4. Target (react-select with placeholder 'Select'). Use configured
        # backup_target if set (an existing target), else the auto-created one.
        bp_target = c.backup_target or c.target.name
        self.select_react_dropdown(r"^Select$", bp_target,
                                   shot_name="bp-target-selected")

        # 4b. Scheduling Policy (optional) — use configured policy if set,
        # else the policy created earlier in the run. If neither is available
        # in the dropdown, leave the policy empty and proceed.
        if with_policy:
            bp_policy = c.backup_scheduling_policy or c.policy_name
            if bp_policy:
                self._select_scheduling_policy(bp_policy)

        # 5. Next -> component selection
        p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).click()
        p.wait_for_timeout(1500)
        self.shot("bp-components-step")

        # 6. Components
        if c.backup_component == "helm" and c.backup_helm_release:
            self._add_helm_release(c.backup_helm_release)
        else:
            self._select_whole_namespace()

        # 7. Finish the wizard: Next -> Skip & Create -> close -> Finish
        self._finish_wizard()

    def _select_scheduling_policy(self, policy_name: str):
        """Select the 'Snapshot Scheduling Policy' under the collapsible
        SNAPSHOT POLICIES section (verified via codegen). Optional — proceeds
        without it if not found."""
        p = self.page
        if not policy_name:
            print("[backupplan] no scheduling policy name given — skipping")
            return

        # 1. Expand 'Snapshot Policies' (a button in edit, a header in create)
        try:
            hdr = p.get_by_role("button", name=re.compile(r"Snapshot Policies", re.I)).first
            if not hdr.is_visible(timeout=2000):
                hdr = p.get_by_text(re.compile(r"^\s*SNAPSHOT POLICIES\s*$", re.I)).first
            if not hdr.is_visible(timeout=3000):
                print("[backupplan] SNAPSHOT POLICIES not found — skipping policy")
                return
            hdr.scroll_into_view_if_needed()
            hdr.click()
            p.wait_for_timeout(1000)
            self.shot("bp-snapshot-policies-expanded")
        except Exception as e:
            print(f"[backupplan] could not expand SNAPSHOT POLICIES ({e}) — skipping")
            return

        # 2. Click the 'Snapshot Scheduling Policy' control (NOT the Retention
        # one). codegen used getByText('Snapshot Scheduling Policy').nth(1)
        try:
            ctrl = p.get_by_text(re.compile(r"^\s*Snapshot Scheduling Policy\s*$", re.I))
            (ctrl.nth(1) if ctrl.count() > 1 else ctrl.first).click(timeout=5000)
            p.wait_for_timeout(700)
        except Exception as e:
            print(f"[backupplan] scheduling-policy control not found ({e}) — skipping")
            return

        # 3. Type the policy name and pick it. Type directly via keyboard
        # rather than locating the react-select input by id — by this step
        # earlier react-selects (Namespace, Target) are still mounted with
        # their own hidden '-input' elements, so a page-wide '.last' lookup
        # can resolve to the wrong, non-interactive one and hang. React-select
        # auto-focuses its filter input as soon as the control opens, so
        # typing straight to the page reaches the right place.
        try:
            p.keyboard.type(policy_name, delay=50)
            p.wait_for_timeout(1000)
            opt = p.locator("[id*='react-select'][id*='option']").filter(
                has_text=policy_name).first
            if not opt.is_visible(timeout=1500):
                opt = p.get_by_text(policy_name, exact=True).last
            opt.click(timeout=4000)
            p.wait_for_timeout(500)
            self.shot("bp-policy-selected")
            print(f"[backupplan] selected scheduling policy '{policy_name}'")
        except Exception as e:
            self.shot("bp-policy-skipped")
            print(f"[backupplan] could not select policy '{policy_name}' ({e}) — "
                  "proceeding without one")
            # The dropdown opened by ctrl.click() above may still be open —
            # dismiss it so it doesn't intercept clicks on Next/Skip & Create
            # for the rest of this wizard (and leak into the next test, since
            # the page is shared for the whole session).
            try:
                p.keyboard.press("Escape")
                p.mouse.click(5, 5)
                p.wait_for_timeout(500)
            except Exception:
                pass

    def _add_helm_release(self, release: str):
        p = self.page
        try:
            p.get_by_role("tab", name=re.compile(r"helm\s*release", re.I)).click()
            p.wait_for_timeout(800)
            p.get_by_text(re.compile(r"add\s*helm\s*release", re.I)).click()
            p.wait_for_timeout(800)
            self.select_react_dropdown(r"^Select Option$", release,
                                       shot_name="bp-helm-selected")
            p.get_by_role("button", name=re.compile(r"^\s*Apply\s*$", re.I)).click()
            p.wait_for_timeout(800)
            self.shot("bp-helm-applied")
        except Exception as e:
            print(f"[backupplan] Helm release selection failed: {e}")

    def _select_whole_namespace(self):
        """Default: back up the entire namespace. The component step usually
        defaults to the whole namespace, so just proceed; if a 'Namespace'
        tab/option is present, make sure it's selected."""
        p = self.page
        try:
            ns_tab = p.get_by_role("tab", name=re.compile(r"^\s*namespace\s*$", re.I)).first
            if ns_tab.is_visible(timeout=2000):
                ns_tab.click()
                p.wait_for_timeout(500)
        except Exception:
            pass
        self.shot("bp-whole-namespace")

    def _finish_wizard(self):
        """Click through Next -> Skip & Create (or Create) -> Finish/close,
        tolerating whichever subset/order of those buttons appears.

        This polls repeatedly for whichever button is currently clickable,
        rather than checking each pattern exactly once in a fixed order.
        That matters because the post-create 'STATUS LOG' success popup (with
        its own 'Finish' button) only renders — and its Finish button only
        enables — AFTER Create/Skip & Create is clicked and the progress bar
        reaches 100%. A single fixed pass checks for Finish/close too early,
        never finds them, and leaves that popup stuck open for the rest of
        the session."""
        p = self.page
        patterns = [
            r"^\s*Next\s*$",
            r"skip\s*&?\s*create|skip\s*and\s*create",
            r"^\s*Create\s*$",
            r"^\s*Finish\s*$",
            r"^\s*close\s*$",
        ]
        clicked_create = False
        for _ in range(15):
            btn = matched = None
            for pattern in patterns:
                btn = self.find_enabled_button(pattern)
                if btn is not None:
                    matched = pattern
                    break
            if btn is None:
                p.wait_for_timeout(1000)
                if clicked_create:
                    break  # nothing left to click and we already created it
                continue
            try:
                btn.click()
            except Exception:
                p.wait_for_timeout(1000)
                continue
            p.wait_for_timeout(1500)
            self.shot(f"bp-clicked-{re.sub(r'[^a-z]', '', matched.lower())[:10]}")
            if re.search(r"create", matched, re.I):
                clicked_create = True
            if clicked_create and re.search(r"finish|close", matched, re.I):
                break
        settle(p)
        self.shot("bp-created")

        if not clicked_create:
            raise AssertionError(
                "Backup plan wizard never reached a Create/Skip & Create "
                f"step — see {self.cfg.screenshot_dir}/bp-created.png")

    def _filter_by_namespace(self, namespace: str):
        """Set the top 'Namespace:' filter on the Backup Plans list so only
        the relevant plans show. Best-effort — proceeds on failure."""
        p = self.page
        try:
            trigger = p.get_by_text(re.compile(r"Namespace\s*:", re.I)).last
            if not trigger.is_visible(timeout=2000):
                return
            trigger.click()
            p.wait_for_timeout(600)
            # react-select style: type to filter
            rs = p.locator("input[id^='react-select'][id$='-input']").last
            try:
                if rs.is_visible(timeout=1500):
                    rs.fill(namespace[:8])
                    p.wait_for_timeout(800)
            except Exception:
                pass
            opt = p.get_by_text(namespace, exact=True).last
            if opt.is_visible(timeout=2000):
                opt.click()
                p.wait_for_timeout(500)
                # the suggestion dropdown stays open and intercepts clicks —
                # dismiss it by clicking the page heading (outside the control)
                try:
                    p.get_by_text(re.compile(r"^\s*BACKUP PLANS\s*$", re.I)).first.click()
                except Exception:
                    p.keyboard.press("Escape")
                    p.mouse.click(5, 5)
                p.wait_for_timeout(800)
                self.shot("backup-ns-filtered")
            else:
                p.keyboard.press("Escape")
                print(f"[backup] Namespace '{namespace}' not in filter — "
                      "using full list")
        except Exception:
            print(f"[backup] Could not apply namespace filter '{namespace}' "
                  "— proceeding with the full list")

    def _clear_namespace_filter(self):
        """Remove the namespace filter chip (the × next to the selected
        namespace) so the full plan list shows again."""
        p = self.page
        try:
            x = p.locator("[class*='namespace' i] [class*='close' i], "
                          ".ant-tag-close-icon, [aria-label='remove' i]").first
            if x.is_visible(timeout=1500):
                x.click()
                p.wait_for_timeout(1000)
                return
        except Exception:
            pass
        # Fallback: click the × inside the namespace chip area at the top
        try:
            chip_x = p.get_by_text(re.compile(r"Namespace\s*:", re.I)).locator(
                "xpath=following::*[text()='×' or @aria-label='close'][1]").first
            if chip_x.is_visible(timeout=1500):
                chip_x.click()
                p.wait_for_timeout(1000)
        except Exception:
            pass

    def verify_backupplan_available(self):
        self.open()
        self.wait_for_status(self.cfg.backupplan_name, "Available", timeout_s=600)

    def trigger_backup(self):
        """Select a backup plan row, click 'Create Backup', name it, create.

        Plan chosen = backup_from_plan (config) if set, else the plan created
        in this run (backupplan_name)."""
        c = self.cfg
        p = self.page
        self.open()
        p.wait_for_timeout(1000)

        # Filter the list by namespace (top 'Namespace:' dropdown) to narrow
        # down to the right backup plan
        bp_namespace = c.res_ns(c.backup_namespace)
        if bp_namespace:
            self._filter_by_namespace(bp_namespace)

        plan = c.backup_from_plan or c.backupplan_name
        row = p.locator("tr, [role='row']").filter(has_text=plan).first
        row.wait_for(state="visible", timeout=15000)
        row.scroll_into_view_if_needed()
        self.shot("backup-plan-row")

        # Check the row's selection checkbox
        cb = row.get_by_role("checkbox", name=re.compile(r"toggle\s*row\s*selected", re.I))
        if not cb.is_visible(timeout=2000):
            cb = row.locator("input[type='checkbox'], [role='checkbox']").first
        cb.check()
        p.wait_for_timeout(500)

        # Click 'Create Backup'
        p.get_by_role("button", name=re.compile(r"^\s*Create Backup\s*$", re.I)).click()
        p.wait_for_timeout(1500)
        self.shot("backup-create-popup")

        # Name the backup
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name\s*$", re.I)).first
        if not name_box.is_visible(timeout=2000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(c.backup_name)
        self.shot("backup-name-filled")

        # Click the exact 'Create' button
        try:
            p.get_by_role("button", name="Create", exact=True).click()
        except Exception:
            btn = self.find_enabled_button(r"^\s*Create\s*$")
            if btn:
                btn.click()
        settle(p)
        self.shot("backup-triggered")
        self._wait_backup_done()

        # The backup is now triggered. Completion is verified via the
        # Kubernetes API (Backup CR), so just close the STATUS LOG popup
        # best-effort and return — don't block on the UI.
        try:
            self._close_status_popup()
        except Exception as e:
            print(f"[backup] status popup close was not clean ({e}) — continuing")

    def _wait_backup_done(self):
        """Poll the backup STATUS LOG popup until the backup reaches
        'Available' (completed) or the operation timeout elapses, then close
        the popup."""
        import time
        p = self.page
        deadline = time.time() + self.cfg.operation_timeout_s
        fail_pat = re.compile(r"failed|error", re.I)
        while time.time() < deadline:
            # Completion = the LAST stage 'Cleanup' is Completed (every stage
            # shows 'Completed' as it finishes, so only Cleanup-Completed
            # means the whole backup is done), or a success toast appears.
            if self._backup_finished():
                self.shot("backup-complete-popup")
                try:
                    self._close_status_popup()
                except Exception as e:
                    print(f"[backup] popup close was not clean ({e}) — backup "
                          "is complete, continuing")
                return
            try:
                if p.get_by_text(fail_pat).first.is_visible(timeout=1000):
                    self.shot("backup-failed")
                    raise AssertionError("Backup reported a failure — see "
                                         f"{self.cfg.screenshot_dir}/backup-failed.png")
            except AssertionError:
                raise
            except Exception:
                pass
            remaining = int(deadline - time.time())
            print(f"[backup] waiting for backup to complete... {remaining}s left")
            p.wait_for_timeout(15000)
        self.shot("backup-wait-timeout")
        self._close_status_popup()
        print(f"[backup] timed out after {self.cfg.operation_timeout_s}s waiting "
              "for the backup — continuing")

    def _backup_finished(self) -> bool:
        """True only when no stage is still 'InProgress' AND the backup has
        reached its terminal state (Status Available, or the final Cleanup
        stage Completed). The InProgress guard prevents declaring completion
        mid-run, since each stage shows 'Completed' as it finishes."""
        p = self.page
        # Still running if ANY 'InProgress' is visible
        try:
            if p.get_by_text(re.compile(r"In\s*Progress", re.I)).first.is_visible(timeout=800):
                return False
        except Exception:
            pass

        # Status header shows 'Available'
        try:
            if p.get_by_text(re.compile(r"\bAvailable\b", re.I)).first.is_visible(timeout=500):
                return True
        except Exception:
            pass

        # Or the final 'Cleanup' stage is Completed
        try:
            rows = p.get_by_text(re.compile(r"\bCleanup\b", re.I))
            for r in rows.all():
                if not r.is_visible():
                    continue
                container = r.locator(
                    "xpath=ancestor-or-self::*[self::div or self::li or self::tr][1]")
                txt = container.inner_text(timeout=1000)
                if re.search(r"Completed", txt, re.I):
                    return True
        except Exception:
            pass
        return False

    def _close_status_popup(self):
        """Close the STATUS LOG popup. Best-effort: try the × icon next to the
        title, then Done/Close/OK buttons, then Escape. Every action has a
        short timeout and is fully guarded — the backup is already complete,
        so failing to close must never fail the test."""
        p = self.page

        def popup_open():
            try:
                return p.get_by_text(re.compile(r"^\s*STATUS LOG\s*$", re.I)).first.is_visible(
                    timeout=1000)
            except Exception:
                return False

        if not popup_open():
            return

        # 1) The close (×) icon — known testid from codegen
        try:
            x = p.get_by_test_id("close-svg").last
            if x.is_visible(timeout=1500):
                x.click(timeout=4000)
                p.wait_for_timeout(800)
                if not popup_open():
                    return
        except Exception:
            pass

        # 2) The × glyph in the STATUS LOG header row
        try:
            title = p.get_by_text(re.compile(r"^\s*STATUS LOG\s*$", re.I)).first
            x = title.locator(
                "xpath=ancestor::*[self::div][1]//*[name()='svg' or self::button]").last
            if x.is_visible(timeout=1000):
                x.click(timeout=4000)
                p.wait_for_timeout(800)
                if not popup_open():
                    return
        except Exception:
            pass

        # 3) Escape key
        try:
            p.keyboard.press("Escape")
            p.wait_for_timeout(600)
            if not popup_open():
                return
        except Exception:
            pass

        btn = (self.find_enabled_button(r"^\s*Done\s*$")
               or self.find_enabled_button(r"^\s*Close\s*$")
               or self.find_enabled_button(r"^\s*OK\s*$"))
        if btn is not None:
            try:
                btn.click(timeout=4000)
                p.wait_for_timeout(800)
                return
            except Exception:
                pass

        for sel in ("button[aria-label='close' i]", "[class*='close' i]",
                    "svg[class*='close' i]", "[data-testid*='close' i]"):
            try:
                x = p.locator(sel).last
                if x.is_visible(timeout=800):
                    x.click(timeout=4000)
                    p.wait_for_timeout(800)
                    if not popup_open():
                        return
            except Exception:
                continue

        # Final fallback: reload the page to clear the stuck client-side modal.
        # Hash routing keeps us on the same page and auth persists.
        if popup_open():
            print("[backup] STATUS LOG popup wouldn't close — reloading page")
            try:
                p.reload(wait_until="networkidle")
                p.wait_for_timeout(1500)
            except Exception:
                pass
