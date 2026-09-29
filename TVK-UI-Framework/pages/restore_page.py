"""Restore page object — restore from backup."""
import re
import time

from pages.base_page import BasePage, settle


class RestorePage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def start_restore_from_backup(self):
        """Restore -> name -> namespace -> Create / Create Restore."""
        self._open_restore_name_and_namespace()
        self._submit_restore_create()

    def start_restore_excluding_configmap(self):
        """Namespace restore: name -> namespace -> Next -> exclude
        configmap/cassandra-config -> Create."""
        self._open_restore_name_and_namespace()
        self._click_restore_next()
        self._wait_restore_resources_ready("Excluded Resources")
        self._add_specific_object_under(
            "Excluded Resources", "configmap", "cassandra-config")
        self._submit_restore_create()

    def start_restore_including_configmap(self):
        """Namespace restore: name -> namespace -> Next -> include
        configmap/cassandra-config -> Create."""
        self._open_restore_name_and_namespace()
        self._click_restore_next()
        self._wait_restore_resources_ready("Included Resources")
        self._add_specific_object_under(
            "Included Resources", "configmap", "cassandra-config")
        self._submit_restore_create()

    def _open_restore_name_and_namespace(self):
        """Backup Plans -> plan caret -> Restore -> fill name + namespace."""
        c = self.cfg
        p = self.page
        plan = c.restore_from_plan or c.backup_from_plan or c.backupplan_name

        self.open()

        from pages.backupplans_page import BackupPlansPage
        bp = BackupPlansPage(p, c)
        try:
            bp._close_status_popup()
        except Exception:
            pass

        bp_namespace = c.res_ns(c.backup_namespace)
        if bp_namespace:
            bp._filter_by_namespace(bp_namespace)

        row = p.locator("tr, [role='row']").filter(has_text=plan).first
        row.wait_for(state="visible", timeout=15000)
        row.scroll_into_view_if_needed()
        self.shot("restore-plan-row")
        row.locator("button").last.click()
        p.wait_for_timeout(800)
        self.shot("restore-menu")

        try:
            p.get_by_role("button", name=re.compile(r"^\s*Restore\s*$", re.I)).click(timeout=5000)
        except Exception:
            p.get_by_text(re.compile(r"^\s*Restore\s*$", re.I)).last.click()
        p.wait_for_timeout(1500)
        self.shot("restore-form")

        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        if not name_box.is_visible(timeout=3000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(c.restore_name)
        self.shot("restore-name-filled")

        target_ns = c.restore_ns()
        try:
            self.select_react_dropdown(
                r"select\s*namespace", target_ns, type_filter=target_ns,
                shot_name="restore-namespace-selected")
        except Exception:
            try:
                ns_trigger = p.get_by_text(re.compile(r"select\s*namespace", re.I)).last
                ns_trigger.click()
                p.wait_for_timeout(600)
                rs = p.locator("input[id^='react-select'][id$='-input']").last
                if rs.is_visible(timeout=1500):
                    rs.fill(target_ns)
                    p.wait_for_timeout(800)
                opt = p.locator("[role='option']").filter(
                    has_text=re.compile(rf"^{re.escape(target_ns)}$", re.I)).first
                if opt.is_visible(timeout=2500):
                    opt.click()
                else:
                    p.keyboard.press("Enter")
                self.shot("restore-namespace-selected")
            except Exception:
                print(f"[restore] Could not select namespace '{target_ns}' — using default")

        self.shot("restore-form-filled")

    def _click_restore_next(self):
        p = self.page
        wizard = p.get_by_test_id("restore-wizard-container")
        scope = wizard if wizard.is_visible(timeout=2000) else p
        try:
            scope.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click(
                timeout=8000)
        except Exception:
            p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(1500)
        self.shot("restore-next")

    def _heading_visible(self, heading: str) -> bool:
        try:
            return self.page.get_by_text(
                re.compile(rf"^\s*{re.escape(heading)}\s*$", re.I)).first.is_visible(
                timeout=1000)
        except Exception:
            return False

    def _browsing_needed(self) -> bool:
        try:
            return self.page.get_by_text(re.compile(
                r"Please enable target browsing|Toggle to enable browsing",
                re.I)).first.is_visible(timeout=1500)
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

    def _enable_restore_browsing_toggle(self):
        """Turn on the Resource Selector browsing toggle if it is still off."""
        p = self.page
        if not self._browsing_needed() or self._browsing_syncing():
            return
        candidates = [
            p.locator("[data-testid='toggle-button-container'] .switch div span").first,
            p.locator("[data-testid='toggle-button-container'] .switch span").first,
            p.locator("[data-testid='toggle-button-container'] .switch").first,
            p.locator("[data-testid='toggle-button-container']").first,
            p.locator(".c-switch-container > .switch > div > span").first,
            p.get_by_text(re.compile(r"Toggle to enable browsing", re.I)).first,
        ]
        for attempt in range(6):
            if self._browsing_syncing() or not self._browsing_needed():
                break
            for el in candidates:
                try:
                    el.click(timeout=3000, force=True)
                    p.wait_for_timeout(1500)
                    break
                except Exception:
                    continue
            self.shot(f"restore-browsing-toggle-{attempt + 1}")
            print(f"[restore] enable browsing toggle attempt {attempt + 1}")
        if self._browsing_syncing():
            print("[restore] target browser is syncing")
        elif self._browsing_needed():
            print("[restore] browsing toggle still off — waiting anyway")

    def _refresh_resource_selector(self):
        """Back -> Next so the Resource Selector re-renders after a sync."""
        p = self.page
        try:
            p.get_by_role("button", name=re.compile(r"^\s*Back\s*$", re.I)).first.click(
                timeout=4000)
            p.wait_for_timeout(1500)
            p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click(
                timeout=4000)
            p.wait_for_timeout(2500)
            self.shot("restore-browsing-refresh")
        except Exception:
            pass

    def _wait_restore_resources_ready(self, heading: str, timeout_s: int | None = None):
        """Wait through target-browser sync until heading is visible.

        The UI may show 'Please enable target browsing' then
        'The Target browser is syncing the details... try after some time'.
        Sync often needs several minutes and may not auto-refresh.
        """
        p = self.page
        timeout_s = timeout_s or self.cfg.operation_timeout_s
        self._enable_restore_browsing_toggle()
        deadline = time.time() + timeout_s
        cycle = 0
        while time.time() < deadline:
            if self._heading_visible(heading):
                self.shot(f"restore-{heading.lower().replace(' ', '-')}")
                print(f"[restore] {heading} is visible")
                return
            remaining = int(deadline - time.time())
            if self._browsing_syncing():
                print(f"[restore] target browser syncing ({remaining}s left)")
            elif self._browsing_needed():
                print(f"[restore] browsing not enabled yet ({remaining}s left)")
                self._enable_restore_browsing_toggle()
            else:
                print(f"[restore] waiting for {heading} ({remaining}s left)")
            cycle += 1
            if cycle % 3 == 0:
                self._refresh_resource_selector()
            else:
                p.wait_for_timeout(15000)
        self.shot("restore-browsing-timeout")
        raise TimeoutError(
            f"{heading} did not appear within {timeout_s}s "
            "(target browsing still syncing)")

    def _add_specific_object_under(self, heading: str, kind: str, object_name: str):
        """heading -> Add resources -> Resource -> Search kind
        -> SpecificObject -> name -> Apply -> Add.

        heading is 'Included Resources' or 'Excluded Resources' so the
        correct Add resources is clicked. Reuses the Cassandra picker.
        """
        from pages.cassandra_backupplan_page import CassandraBackupPlanPage

        p = self.page
        section = p.get_by_text(re.compile(rf"^\s*{re.escape(heading)}\s*$", re.I)).first
        section.wait_for(state="visible", timeout=10000)
        add = section.locator(
            "xpath=following::*[normalize-space()='Add resources' "
            "or normalize-space()='Add Resources'][1]")
        add.click()
        p.wait_for_timeout(800)
        self.shot(f"restore-{heading.lower().replace(' ', '-')}-add-resources")

        p.get_by_text(re.compile(r"^\s*Resource\s*$", re.I)).first.click()
        p.wait_for_timeout(800)
        self.shot(f"restore-{heading.lower().replace(' ', '-')}-resource")

        cass = CassandraBackupPlanPage(p, self.cfg)
        cass._search_and_add_specific_object(kind, object_name)
        cass._click_named_button(r"^\s*Add\s*$")
        p.wait_for_timeout(800)
        self.shot(f"restore-{heading.lower().replace(' ', '-')}-added")

    def _submit_restore_create(self):
        p = self.page
        wizard = p.get_by_test_id("restore-wizard-container")
        scope = wizard if wizard.is_visible(timeout=2000) else p
        for label in (r"^\s*Create\s*$", r"^\s*Create Restore\s*$"):
            try:
                btn = scope.get_by_role("button", name=re.compile(label, re.I)).first
                if btn.is_visible(timeout=4000):
                    btn.click()
                    p.wait_for_timeout(1500)
            except Exception:
                continue
        settle(p)
        self.shot("restore-started")

    def _restore_finished(self) -> bool:
        """True only when NO step is still 'InProgress' AND the restore's
        Status header shows Completed/Available. Each step (MetadataRestore,
        DataRestore, ...) shows 'Completed' as it finishes, so the InProgress
        guard prevents declaring completion mid-run — mirrors the backup."""
        p = self.page
        # Still running if ANY 'InProgress' is visible
        try:
            if p.get_by_text(re.compile(r"In\s*Progress", re.I)).first.is_visible(timeout=800):
                return False
        except Exception:
            pass
        # Status header shows Completed / Available
        try:
            if p.get_by_text(re.compile(r"Status\s*\|?\s*(Completed|Available)", re.I)).first \
                    .is_visible(timeout=500):
                return True
        except Exception:
            pass
        try:
            if p.get_by_text(re.compile(r"\b(Completed|Available)\b", re.I)).first.is_visible(
                    timeout=500):
                return True
        except Exception:
            pass
        return False

    def wait_restore_done(self):
        """Poll the restore STATUS LOG popup until it reaches Completed/
        Available (not just a per-step 'Completed'), then close it."""
        import time
        p = self.page
        deadline = time.time() + self.cfg.operation_timeout_s
        fail_pat = re.compile(r"failed|error", re.I)
        while time.time() < deadline:
            if self._restore_finished():
                self.shot("restore-complete-popup")
                self.close_status_popup()
                return
            try:
                if p.get_by_text(fail_pat).first.is_visible(timeout=1000):
                    self.shot("restore-failed")
                    raise AssertionError("Restore reported a failure — see "
                                         f"{self.cfg.screenshot_dir}/restore-failed.png")
            except AssertionError:
                raise
            except Exception:
                pass
            remaining = int(deadline - time.time())
            print(f"[restore] waiting for restore to complete... {remaining}s left")
            p.wait_for_timeout(15000)
        self.shot("restore-wait-timeout")
        self.close_status_popup()
        print(f"[restore] timed out after {self.cfg.operation_timeout_s}s — continuing")

    def close_status_popup(self):
        """Close the CREATE RESTORE status popup. Unlike the backup STATUS LOG
        popup (× icon), this one closes via its 'Finish' button."""
        p = self.page
        for pat in (r"^\s*Finish\s*$", r"^\s*Done\s*$", r"^\s*Close\s*$",
                    r"^\s*OK\s*$"):
            try:
                btn = p.get_by_role("button", name=re.compile(pat, re.I)).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    p.wait_for_timeout(1000)
                    self.shot("restore-popup-closed")
                    return
            except Exception:
                continue
        # × close icon
        try:
            x = p.get_by_test_id("close-svg").last
            if x.is_visible(timeout=1500):
                x.click(timeout=4000)
                p.wait_for_timeout(800)
                return
        except Exception:
            pass
        # last resort: reload to clear the modal
        try:
            print("[restore] popup wouldn't close — reloading page")
            p.reload(wait_until="networkidle")
            p.wait_for_timeout(1500)
        except Exception:
            pass

    def verify_restore_complete(self):
        self.open()
        self.wait_for_status(self.cfg.restore_name, "Completed|Success|Available")
        self.shot("restore-complete")
