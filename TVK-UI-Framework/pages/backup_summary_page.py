"""Backup Summary page object (separate from backups_page.py).

Opens the monitoring 'View Backup & Restore Summary' for a specific backup
plan via the robust per-plan path (search plan -> expand row -> open summary)
and confirms the BACKUP SUMMARY card shows no Failed and >=1 Available.
"""
import re
import time

from pages.base_page import BasePage


class BackupSummaryPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def _open_plan_summary(self, plan: str) -> bool:
        """Search the plan, expand its row, open 'View Backup & Restore
        Summary' (the monitoring popup)."""
        p = self.page
        try:
            search = p.get_by_test_id("search-input").first
            if not search.is_visible(timeout=2000):
                search = p.get_by_placeholder(re.compile(r"search", re.I)).first
            search.click()
            search.fill(plan)
            p.wait_for_timeout(1500)
            exp = p.get_by_test_id("react-table-container").get_by_role(
                "button").filter(has_text=re.compile(r"^$")).first
            exp.click(timeout=5000)
            p.wait_for_timeout(800)
        except Exception as e:
            print(f"[backup_summary] plan search/expand skipped ({e})")
        try:
            btn = p.get_by_role("button", name=re.compile(
                r"View Backup\s*&?\s*Restore Summary", re.I)).first
            if not btn.is_visible(timeout=3000):
                btn = p.get_by_text(re.compile(
                    r"View Backup\s*&?\s*Restore Summary", re.I)).first
            btn.click(timeout=8000)
            p.wait_for_timeout(1500)
            self.shot("backup-summary")
            return True
        except Exception as e:
            print(f"[backup_summary] could not open summary ({e})")
            return False

    def _read_backup_summary(self):
        """Return (available, failed) from the BACKUP SUMMARY card, or
        (None, None) if not readable yet."""
        p = self.page
        try:
            heading = p.get_by_text(re.compile(r"BACKUP SUMMARY", re.I)).first
            if not heading.is_visible(timeout=2000):
                return None, None
            for level in range(1, 7):
                t = heading.locator(f"xpath=ancestor::*[{level}]").inner_text(timeout=1500)
                if "Available(" in t and "Failed(" in t:
                    av = re.search(r"Available\((\d+)\)", t)
                    fl = re.search(r"Failed\((\d+)\)", t)
                    return (int(av.group(1)) if av else 0,
                            int(fl.group(1)) if fl else 0)
        except Exception:
            pass
        return None, None

    def _monitoring_open(self) -> bool:
        try:
            return self.page.get_by_text(
                re.compile(r"^\s*MONITORING\s*$", re.I)).first.is_visible(timeout=1000)
        except Exception:
            return False

    def _close_monitoring(self):
        """Close the MONITORING summary popup so it doesn't overlay the page.
        A loading div.overlay can intercept the × click, so wait for it to
        clear, force-click, retry, and finally reload."""
        p = self.page
        if not self._monitoring_open():
            return
        # wait for any loading overlay to clear first
        try:
            p.locator("div.overlay").first.wait_for(state="hidden", timeout=15000)
        except Exception:
            pass
        for _ in range(3):
            # close-svg icon
            try:
                x = p.get_by_test_id("close-svg").last
                if x.is_visible(timeout=1500):
                    x.click(timeout=4000, force=True)
                    p.wait_for_timeout(800)
                    if not self._monitoring_open():
                        return
            except Exception:
                pass
            # × glyph next to the MONITORING title
            try:
                title = p.get_by_text(re.compile(r"^\s*MONITORING\s*$", re.I)).first
                x = title.locator(
                    "xpath=ancestor::*[self::div][1]//*[name()='svg' or self::button]").last
                if x.is_visible(timeout=1000):
                    x.click(timeout=4000, force=True)
                    p.wait_for_timeout(800)
                    if not self._monitoring_open():
                        return
            except Exception:
                pass
            # Escape
            try:
                p.keyboard.press("Escape")
                p.wait_for_timeout(600)
            except Exception:
                pass
            if not self._monitoring_open():
                return
        # last resort: reload to clear the modal
        try:
            print("[backup_summary] MONITORING popup wouldn't close — reloading")
            p.reload(wait_until="networkidle")
            p.wait_for_timeout(1500)
        except Exception:
            pass

    def verify(self, plan: str):
        """Open the plan's backup summary and confirm Failed==0, Available>=1.
        Polls (the global count lags after a backup completes)."""
        self.open()
        deadline = time.time() + 300
        last = (None, None)
        while time.time() < deadline:
            if self._open_plan_summary(plan):
                n_avail, n_failed = self._read_backup_summary()
                last = (n_avail, n_failed)
                print(f"[backup_summary] BACKUP SUMMARY -> "
                      f"Available({n_avail}) Failed({n_failed})")
                if n_failed:
                    self.shot("backup-summary-failed")
                    raise AssertionError(f"Backup summary reports {n_failed} failed")
                if n_avail and n_avail >= 1:
                    self.shot("backup-summary-ok")
                    print("[backup_summary] backup confirmed Available")
                    self._close_monitoring()
                    return
            # close popup + retry (count lags)
            try:
                self.page.get_by_role("button").filter(
                    has_text=re.compile(r"^$")).last.click(timeout=2000)
            except Exception:
                pass
            self.page.wait_for_timeout(15000)
            self.open()
        self.shot("backup-summary-timeout")
        raise AssertionError(
            f"BACKUP SUMMARY did not show an Available backup in time (last={last})")
