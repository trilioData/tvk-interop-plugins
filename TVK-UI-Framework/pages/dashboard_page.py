"""Trilio dashboard / navigation page object."""
import re

from pages.base_page import BasePage, settle


class DashboardPage(BasePage):
    """Left-nav navigation. Targets/Backup Plans/Policies live under the
    expandable 'Backup and Recovery' group."""

    # section -> (parent group to expand first, exact link text pattern)
    # Patterns are anchored (^...$) and matched against the element's OWN text,
    # so a group like 'Cluster Management' can never be picked by accident.
    NAV_ITEMS = {
        "backupplans": (r"^\s*Backup\s*Plans?\s*$",),
        "targets":     (r"^\s*Targets?\s*$",),
        "policies":    (r"^\s*Polic(y|ies)\s*$",),
        "backups":     (r"^\s*Backups?\s*$",),
        "restores":    (r"^\s*Restores?\s*$",),
        "monitoring":  (r"^\s*(Monitoring|Dashboard|Overview)\s*$",),
    }

    PARENT_GROUP = r"^\s*Backup\s*(and|&)\s*Recovery\s*$"
    NEEDS_PARENT = {"backupplans", "targets", "policies", "backups", "restores"}

    def _exact_text(self, pattern: str):
        """Smallest element whose own text matches the anchored pattern."""
        return self.page.get_by_text(re.compile(pattern, re.I)).first

    def _ensure_backup_recovery_view(self):
        """Make sure we're in the 'Backup & Recovery' view (its left-nav with
        Backup Plans/Targets/etc.). Other views — e.g. 'Trilio Monitoring' /
        Backup Overview — have a different sidebar where the section links
        aren't present. Recover via the codegen entry path."""
        p = self.page
        # Already in the right view?
        if self._exact_text(self.PARENT_GROUP).is_visible(timeout=2000):
            return
        # Try the 'Backup & Recovery' link/back-arrow if present
        try:
            br = p.get_by_role("link", name=re.compile(r"Backup\s*&?\s*Recovery", re.I)).first
            if br.is_visible(timeout=2000):
                br.click()
                settle(p)
                if self._exact_text(self.PARENT_GROUP).is_visible(timeout=3000):
                    return
        except Exception:
            pass
        # Fallback: navigate to the cluster list, then click Backup & Recovery
        try:
            base = self.cfg.cluster.trilio_url.split("#/")[0]
            p.goto(base + "#/cluster-management/list", wait_until="networkidle")
            p.wait_for_timeout(1000)
            p.get_by_role("link", name=re.compile(r"Backup\s*&?\s*Recovery", re.I)).first.click()
            settle(p)
            p.wait_for_timeout(1000)
        except Exception as e:
            print(f"[nav] could not re-enter Backup & Recovery view: {e}")

    def goto_section(self, section: str):
        item = self.NAV_ITEMS.get(section)
        if not item:
            raise ValueError(f"Unknown section '{section}'. Known: {list(self.NAV_ITEMS)}")
        pattern = item[0]

        link = self._exact_text(pattern)

        # Expand 'Backup and Recovery' if the sub-item isn't visible yet
        if section in self.NEEDS_PARENT and not link.is_visible(timeout=3000):
            # We may be on a different view (e.g. Monitoring) — get back first
            if not self._exact_text(self.PARENT_GROUP).is_visible(timeout=2000):
                self._ensure_backup_recovery_view()
            parent = self._exact_text(self.PARENT_GROUP)
            parent.wait_for(state="visible", timeout=20000)
            parent.click()
            self.page.wait_for_timeout(1000)
            self.shot(f"nav-expanded-{section}")
            link = self._exact_text(pattern)

        link.wait_for(state="visible", timeout=20000)
        link.click()
        settle(self.page)
        self.shot(f"nav-{section}")
