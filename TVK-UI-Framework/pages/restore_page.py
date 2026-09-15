"""Restore page object — restore from backup."""
import re

from pages.base_page import BasePage, settle


class RestorePage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def start_restore_from_backup(self):
        """
        Restore the chosen backup plan's backup into the restore namespace.

        Flow (from codegen): Backup Plans -> the plan row's caret (next to
        'Edit') -> 'Restore' -> fill Name -> Select Namespace -> Create ->
        Create Restore.

        Plan = restore_from_plan (config) if set, else backup_from_plan, else
        the run's backupplan_name.
        """
        c = self.cfg
        p = self.page
        plan = c.restore_from_plan or c.backup_from_plan or c.backupplan_name

        self.open()  # Backup Plans

        # Dismiss any lingering STATUS LOG popup that could overlay the page
        from pages.backupplans_page import BackupPlansPage
        bp = BackupPlansPage(p, c)
        try:
            bp._close_status_popup()
        except Exception:
            pass

        # Filter by namespace so the plan row is easy to find
        bp_namespace = c.res_ns(c.backup_namespace)
        if bp_namespace:
            bp._filter_by_namespace(bp_namespace)

        # Locate the plan row and expand the caret (▾) next to its Edit button
        row = p.locator("tr, [role='row']").filter(has_text=plan).first
        row.wait_for(state="visible", timeout=15000)
        row.scroll_into_view_if_needed()
        self.shot("restore-plan-row")
        # the caret is the last button in the row (right of 'Edit')
        row.locator("button").last.click()
        p.wait_for_timeout(800)
        self.shot("restore-menu")

        # Click 'Restore' in the opened menu
        try:
            p.get_by_role("button", name=re.compile(r"^\s*Restore\s*$", re.I)).click(timeout=5000)
        except Exception:
            p.get_by_text(re.compile(r"^\s*Restore\s*$", re.I)).last.click()
        p.wait_for_timeout(1500)
        self.shot("restore-form")

        # Restore Name
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        if not name_box.is_visible(timeout=3000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(c.restore_name)
        self.shot("restore-name-filled")

        # Select Namespace (target). Use the configured restore namespace
        # (which the test ensures exists), else the first available option.
        target_ns = c.restore_ns()
        try:
            ns_trigger = p.get_by_text(re.compile(r"select\s*namespace", re.I)).last
            ns_trigger.click()
            p.wait_for_timeout(600)
            # type to filter (react-select)
            rs = p.locator("input[id^='react-select'][id$='-input']").last
            try:
                if rs.is_visible(timeout=1500):
                    rs.fill(target_ns[:8])
                    p.wait_for_timeout(800)
            except Exception:
                pass
            opt = p.get_by_text(target_ns, exact=True).last
            if not opt.is_visible(timeout=2500):
                opt = p.locator("[role='option'], .ant-select-item, li").first
            opt.click()
            p.wait_for_timeout(500)
            self.shot("restore-namespace-selected")
        except Exception:
            print(f"[restore] Could not select namespace '{target_ns}' — using default")

        self.shot("restore-form-filled")

        # Finish: 'Create' then 'Create Restore' inside the restore wizard
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
