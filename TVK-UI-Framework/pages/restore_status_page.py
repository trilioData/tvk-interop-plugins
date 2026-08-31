"""Restore Status page object.

Standalone-friendly UI check that confirms a restore completed. Based on the
codegen flow: Backup Plans -> 'View Backup & Restore Summary' -> RESTORE
SUMMARY card -> Details -> the restore's status shows 'Completed'.

Run independently with:  pytest -m restore_status
"""
import re

from pages.base_page import BasePage


class RestoreStatusPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def _read_restore_summary(self):
        """Return (completed, failed) from the RESTORE SUMMARY card, or
        (None, None) if it can't be read yet."""
        p = self.page
        try:
            heading = p.get_by_text(re.compile(r"RESTORE SUMMARY", re.I)).first
            if not heading.is_visible(timeout=2000):
                return None, None
            for level in range(1, 7):
                t = heading.locator(f"xpath=ancestor::*[{level}]").inner_text(timeout=1500)
                if "Completed(" in t and "Failed(" in t:
                    failed = re.search(r"Failed\((\d+)\)", t)
                    completed = re.search(r"Completed\((\d+)\)", t)
                    return (int(completed.group(1)) if completed else 0,
                            int(failed.group(1)) if failed else 0)
        except Exception:
            pass
        return None, None

    def _open_plan_summary(self, plan: str):
        """Codegen path: search the plan, expand its row, open the summary."""
        p = self.page
        try:
            search = p.get_by_test_id("search-input").first
            if not search.is_visible(timeout=2000):
                search = p.get_by_placeholder(re.compile(r"search", re.I)).first
            search.click()
            search.fill(plan)
            p.wait_for_timeout(1500)
            # the row expander is the empty-text button in the table row
            exp = p.get_by_test_id("react-table-container").get_by_role(
                "button").filter(has_text=re.compile(r"^$")).first
            exp.click(timeout=5000)
            p.wait_for_timeout(800)
        except Exception as e:
            print(f"[restore_status] plan search/expand skipped ({e})")
        # Now click 'View Backup & Restore Summary'
        try:
            p.get_by_role("button", name=re.compile(
                r"View Backup\s*&?\s*Restore Summary", re.I)).first.click(timeout=8000)
            p.wait_for_timeout(1500)
            self.shot("rstatus-summary")
            return True
        except Exception as e:
            print(f"[restore_status] could not open summary ({e})")
            return False

    def verify_restore_completed(self):
        """Confirm the restore completed via the RESTORE SUMMARY. The global
        summary count lags after the restore finishes, so poll it (re-opening
        the per-plan summary) until Completed>=1 / Failed==0."""
        import time
        c = self.cfg
        p = self.page
        plan = c.restore_from_plan or c.backup_from_plan or c.backupplan_name

        self.open()
        # Dismiss any lingering CREATE RESTORE popup
        try:
            from pages.restore_page import RestorePage
            RestorePage(p, c).close_status_popup()
        except Exception:
            pass

        deadline = time.time() + 300  # poll up to 5 min for the count to update
        last = (None, None)
        while time.time() < deadline:
            if not self._open_plan_summary(plan):
                # fall back to the global summary button
                try:
                    p.get_by_role("button", name=re.compile(
                        r"View Backup\s*&?\s*Restore Summary", re.I)).first.click(timeout=5000)
                    p.wait_for_timeout(1500)
                except Exception:
                    pass
            n_completed, n_failed = self._read_restore_summary()
            last = (n_completed, n_failed)
            print(f"[restore_status] RESTORE SUMMARY -> Completed({n_completed}) "
                  f"Failed({n_failed})")
            if n_failed:
                self.shot("rstatus-failed")
                raise AssertionError(f"Restore summary reports {n_failed} failed restore(s)")
            if n_completed and n_completed >= 1:
                self.shot("rstatus-status")
                print("[restore_status] restore confirmed Completed")
                return
            # close the summary and retry after a short wait (count lags)
            try:
                p.get_by_role("button").filter(
                    has_text=re.compile(r"^$")).last.click(timeout=2000)
            except Exception:
                pass
            p.wait_for_timeout(15000)
            self.open()

        self.shot("rstatus-timeout")
        raise AssertionError(
            f"RESTORE SUMMARY did not show a Completed restore in time (last={last})")
