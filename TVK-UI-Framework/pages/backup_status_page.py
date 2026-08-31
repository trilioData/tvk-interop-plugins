"""Backup Status page object.

Standalone-friendly UI check that confirms a backup is in the 'Available'
state. Verified against Playwright codegen:
  Backup Plans -> open the plan -> 'View Backups' -> the backup row shows
  'Available' in the react-table.

Run independently with:  pytest -m backup_status
"""
import re
import time

from pages.base_page import BasePage


class BackupStatusPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def _open_backup_list(self, plan: str):
        """Backup Plans list -> open plan -> View Backups."""
        c = self.cfg
        p = self.page
        self.open()

        # Defensively dismiss any lingering STATUS LOG popup that could overlay
        # the page (e.g. left open by the preceding backup step)
        from pages.backupplans_page import BackupPlansPage
        bp = BackupPlansPage(p, c)
        try:
            bp._close_status_popup()
        except Exception:
            pass

        # Filter by namespace so the plan link is easy to find
        bp_namespace = c.res_ns(c.backup_namespace)
        if bp_namespace:
            bp._filter_by_namespace(bp_namespace)

        # Open the backup plan
        plan_link = p.get_by_role("link", name=plan).first
        if not plan_link.is_visible(timeout=5000):
            plan_link = p.get_by_text(plan, exact=True).last
        plan_link.click()
        p.wait_for_timeout(1500)
        self.shot("bstatus-plan-opened")

        # View Backups
        p.get_by_role("button", name=re.compile(r"View Backups", re.I)).click()
        p.wait_for_timeout(1500)
        self.shot("bstatus-backup-list")

    def verify_backup_available(self, timeout_s: int = 120):
        """Open the backup plan -> View Backups -> confirm the backup row
        shows 'Available'.

        Backup = backup_check_name (config) if set, else the backup created in
        this run (backup_name). Plan = backup_from_plan or the run's
        backupplan_name.

        By the time this runs, the backend Backup CR is already confirmed
        complete (test_trigger_backup waits on it via the Kubernetes API) —
        but this UI table can lag behind that and briefly still show a stale
        'InProgress' row. Poll/reload for up to timeout_s instead of failing
        on a single stale read.
        """
        c = self.cfg
        p = self.page
        plan = c.backup_from_plan or c.backupplan_name
        backup = c.backup_check_name or c.backup_name

        self._open_backup_list(plan)

        deadline = time.time() + timeout_s
        txt = ""
        while time.time() < deadline:
            table = p.get_by_test_id("react-table-container")
            scope = table if table.is_visible(timeout=3000) else p
            row = scope.locator("tr, [role='row']").filter(has_text=backup).first
            try:
                row.wait_for(state="visible", timeout=15000)
                row.scroll_into_view_if_needed()
                txt = row.inner_text(timeout=3000)
            except Exception:
                self.shot("bstatus-notfound")
                raise AssertionError(
                    f"Backup '{backup}' not found under plan '{plan}' — see "
                    f"{self.cfg.screenshot_dir}/bstatus-notfound.png")

            if re.search(r"\bAvailable\b", txt, re.I):
                self.shot("bstatus-status")
                print(f"[backup_status] UI confirms backup '{backup}' is Available")
                return
            if re.search(r"\bFailed\b", txt, re.I):
                self.shot("bstatus-failed")
                raise AssertionError(f"Backup '{backup}' entered Failed state: {txt}")

            print(f"[backup_status] backup '{backup}' still shows "
                  f"'{txt.strip()[:60]}' — reloading and retrying...")
            time.sleep(5)
            self._open_backup_list(plan)

        self.shot("bstatus-timeout")
        raise AssertionError(
            f"Backup '{backup}' did not show Available within {timeout_s}s "
            f"— last row: {txt}")
