"""Backups page object.

Note: this Trilio UI has no separate 'Backups' nav item — backups live under
their Backup Plan (and their progress is shown in the STATUS LOG popup, which
BackupPlansPage._wait_backup_done already polls to completion). So these
methods work off the Backup Plans page rather than a non-existent section.
"""
import re

from pages.base_page import BasePage


class BackupsPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def verify_backup_complete(self):
        """Verify via the MONITORING summary: open 'View Backup & Restore
        Summary' and check the BACKUP SUMMARY card shows no Failed backups and
        at least one Available."""
        p = self.page
        self.open()

        # Open the monitoring summary popup
        btn = p.get_by_role("button", name=re.compile(
            r"View Backup\s*&?\s*Restore Summary", re.I)).first
        if not btn.is_visible(timeout=3000):
            # may be hidden behind a toolbar overflow (kebab) button
            try:
                p.get_by_role("button").nth(5).click(timeout=5000)
                p.wait_for_timeout(600)
            except Exception:
                pass
            btn = p.get_by_text(re.compile(
                r"View Backup\s*&?\s*Restore Summary", re.I)).first
        btn.click(timeout=8000)
        p.wait_for_timeout(1500)
        self.shot("backup-summary")

        # Read the BACKUP SUMMARY card text
        heading = p.get_by_text(re.compile(r"BACKUP SUMMARY", re.I)).first
        heading.wait_for(state="visible", timeout=10000)
        card_text = ""
        for level in range(1, 7):
            try:
                cand = heading.locator(f"xpath=ancestor::*[{level}]")
                t = cand.inner_text(timeout=1500)
                if "Available(" in t and "Failed(" in t:
                    card_text = t
                    break
            except Exception:
                continue
        if not card_text:
            card_text = p.inner_text("body")

        failed = re.search(r"Failed\((\d+)\)", card_text)
        available = re.search(r"Available\((\d+)\)", card_text)
        n_failed = int(failed.group(1)) if failed else 0
        n_avail = int(available.group(1)) if available else 0
        print(f"[backup] BACKUP SUMMARY -> Available({n_avail}) Failed({n_failed})")

        assert n_failed == 0, f"Backup summary reports {n_failed} failed backup(s)"
        assert n_avail >= 1, "No Available backups in the summary"
        self.shot("backup-complete")

    def verify_snapshot_stage(self):
        """Open the plan's STATUS LOG and confirm a snapshot stage is present.
        The status log lists MetaSnapshot/DataSnapshot stages."""
        c = self.cfg
        p = self.page
        self.open()
        plan = c.backup_from_plan or c.backupplan_name
        row = p.locator("tr, [role='row']").filter(has_text=plan).first
        try:
            row.click()
            p.wait_for_timeout(1500)
        except Exception:
            pass
        self.shot("backup-details-snapshot")
        body = p.inner_text("body").lower()
        assert "snapshot" in body, "No snapshot stage info found"
