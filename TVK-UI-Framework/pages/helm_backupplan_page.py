"""Helm backup plan page object — separate from the namespace backup plan.

Creates an Application-type backup plan that captures a Helm Release, per
helm_trans.spec.js:
  Create New -> Application -> Namespace -> Name -> Target -> Next ->
  Helm Release tab -> Add Helm Release -> pick release -> Apply -> finish
"""
import re
import time

from pages.base_page import BasePage


class HelmBackupPlanPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("backupplans")
        self.page.wait_for_timeout(1000)

    def create(self, namespace: str, plan_name: str, target: str, release: str):
        p = self.page
        self.open()

        # Create New -> Application
        p.get_by_text(re.compile(r"^\s*Create New\s*$", re.I)).first.click()
        p.wait_for_timeout(1000)
        self.shot("helmbp-create-menu")
        p.get_by_role("button", name=re.compile(r"^\s*Application\s*$", re.I)).click()
        p.wait_for_timeout(1200)
        self.shot("helmbp-application")

        # Same as backupplans_page: Namespace (filter prefix), Name, Target (Select, no type)
        self.select_react_dropdown(r"^Select Namespace$", namespace,
                                   type_filter=namespace[:5],
                                   shot_name="helmbp-namespace")
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        if not name_box.is_visible(timeout=2000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(plan_name)
        self.shot("helmbp-name-filled")
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

        # Finish wizard: Next -> Skip & Create -> close -> Finish
        self._finish()

    def _finish(self):
        """Walk Next -> Skip & Create -> (sync) -> Finish. A loading overlay
        (div.overlay) intercepts clicks during the sync, so wait for it to
        clear and poll for each button until the wizard popup closes."""
        p = self.page
        labels = [
            r"skip\s*&?\s*create|skip\s*and\s*create",
            r"^\s*Finish\s*$",
            r"^\s*Next\s*$",
            r"^\s*close\s*$",
            r"^\s*Create\s*$",
        ]
        deadline = time.time() + 180
        while time.time() < deadline:
            # wait for any loading overlay to clear before clicking
            try:
                p.locator("div.overlay").first.wait_for(state="hidden", timeout=10000)
            except Exception:
                pass
            # wizard closed? (the form-wizard popup is gone)
            try:
                if not p.get_by_test_id("form-wizard-container").first.is_visible(timeout=1500):
                    self.shot("helmbp-created")
                    return
            except Exception:
                self.shot("helmbp-created")
                return
            clicked = False
            for pat in labels:
                btn = self.find_enabled_button(pat)
                if btn is not None:
                    try:
                        btn.click(timeout=5000)
                        p.wait_for_timeout(1500)
                        clicked = True
                        break
                    except Exception:
                        continue
            if not clicked:
                p.wait_for_timeout(2000)
        self.shot("helmbp-finish-timeout")
