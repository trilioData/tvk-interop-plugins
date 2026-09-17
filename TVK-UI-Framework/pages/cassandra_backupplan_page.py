"""Cassandra backup-plan + backup page.

  create()              Single-namespace plan
  create_application()  Application plan (operator + CassandraDatacenter)
  trigger_backup()           Create Backup from a plan
  create_backup_and_wait()   trigger, stay on STATUS LOG until Available/Failed, then close
"""
import re
import time

from pages.base_page import BasePage, settle


class CassandraBackupPlanPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        self._ensure_backupplans_ready()
        if "status-log" in (self.page.url or "") or "backupplans" not in (self.page.url or ""):
            try:
                DashboardPage(self.page, self.cfg).goto_section("backupplans")
            except Exception:
                self._goto_backupplans_list()
        self.page.wait_for_timeout(1000)

    def _open_create_menu(self, shot_name: str):
        """Same entry as the namespace plan: icon caret, then Create New."""
        p = self.page
        try:
            p.locator("div.overlay").first.wait_for(state="hidden", timeout=15000)
        except Exception:
            self._ensure_backupplans_ready()
        try:
            p.locator(".icon-container.icon-xs-15.icon-sm-18 > svg").click(timeout=8000)
        except Exception:
            self.click_create_new()
        p.wait_for_timeout(800)
        self.shot(shot_name)

    def create(self, namespace: str, plan_name: str, target: str):
        """Single-namespace backup plan for cass-oper-ns."""
        p = self.page
        self.open()
        self._open_create_menu("cassbp-create-menu")

        p.get_by_role("button", name=re.compile(r"single[\s\-]*namespace", re.I)).click()
        p.wait_for_timeout(1500)
        self.shot("cassbp-type-namespace")

        self.select_react_dropdown(r"^Select Namespace$", namespace,
                                   type_filter=namespace[:5],
                                   shot_name="cassbp-namespace")
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        if not name_box.is_visible(timeout=2000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(plan_name)
        self.shot("cassbp-name-filled")
        self.select_react_dropdown(r"^Select$", target, shot_name="cassbp-target")

        # Continue / Next after namespace + name + target
        try:
            p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).click()
        except Exception:
            try:
                p.get_by_test_id("form-wizard-children").get_by_role(
                    "button", name=re.compile(r"^\s*Next\s*$", re.I)).click()
            except Exception:
                p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(1500)
        self.shot("cassbp-continued")

        self._finish()

    def create_application(self, namespace: str, plan_name: str, target: str,
                           operator: str = "", cr_kind: str = "CassandraDatacenter",
                           cr_object: str = ""):
        """Application backup plan for the Cassandra operator.

        Create New -> Application -> Namespace -> Name -> Target -> Next ->
        Add Operator -> Operator name -> Apply -> Add Operator Resource ->
        OLM Backup -> subscription -> Add -> Add Custom Resources ->
        CassandraDatacenter -> dc1 -> Apply -> Save ->
        Advanced Configuration (secret + configmap) -> Next -> Create
        """
        p = self.page
        c = self.cfg.cassandra
        operator = operator or c.operator_name
        cr_object = cr_object or c.dc_name
        self.open()
        self._open_create_menu("cassapp-create-menu")
        p.get_by_role("button", name=re.compile(r"^\s*Application\s*$", re.I)).click()
        p.wait_for_timeout(1200)
        self.shot("cassapp-application")

        # Namespace, Name, Target
        self.select_react_dropdown(r"^Select Namespace$", namespace,
                                   type_filter=namespace[:5],
                                   shot_name="cassapp-namespace")
        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name", re.I)).first
        if not name_box.is_visible(timeout=2000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(plan_name)
        self.shot("cassapp-name-filled")
        self.select_react_dropdown(r"^Select$", target, shot_name="cassapp-target")
        self._click_next()
        self.shot("cassapp-components")

        # Add Operator -> fill Operator -> Apply
        p.get_by_text(re.compile(r"Add Operator", re.I)).first.click()
        p.wait_for_timeout(800)
        op_box = p.get_by_role("textbox", name=re.compile(r"^\s*Operator", re.I)).first
        if not op_box.is_visible(timeout=2000):
            try:
                self.select_react_dropdown(r"^Select Option$", operator,
                                           type_filter=operator,
                                           shot_name="cassapp-operator")
                op_box = None
            except Exception:
                op_box = p.get_by_placeholder(re.compile(r"operator", re.I)).first
        if op_box is not None:
            op_box.click()
            op_box.fill(operator)
            # pick the filtered suggestion if one appears
            try:
                p.get_by_text(operator, exact=True).last.click(timeout=3000)
            except Exception:
                pass
        self.shot("cassapp-operator-filled")
        self._click_named_button(r"^\s*Apply\s*$")
        p.wait_for_timeout(800)
        self.shot("cassapp-operator-applied")

        # Add Operator Resource -> OLM Backup -> subscription -> Add
        p.get_by_text(re.compile(r"Add Operator Resource", re.I)).first.click()
        p.wait_for_timeout(800)
        p.get_by_text(re.compile(r"OLM\s*Backup", re.I)).first.click()
        p.wait_for_timeout(800)
        self.shot("cassapp-olm")
        # Label: "Select a subscription"; placeholder: "Select Option".
        # Type a prefix, then pick the filtered option or press Enter.
        try:
            p.get_by_text(re.compile(r"Select a subscription", re.I)).first.click()
        except Exception:
            p.get_by_text(re.compile(r"^\s*Select Option\s*$", re.I)).last.click()
        p.wait_for_timeout(400)
        prefix = operator[:5] if operator else "cass-"
        rs = p.locator("input[id^='react-select'][id$='-input']").last
        try:
            if rs.is_visible(timeout=2000):
                rs.fill(prefix)
            else:
                p.keyboard.type(prefix, delay=50)
        except Exception:
            p.keyboard.type(prefix, delay=50)
        p.wait_for_timeout(1000)
        self.shot("cassapp-subscription-typed")
        opt = p.locator("[role='option'], [id*='react-select'][id*='option']").filter(
            has_text=re.compile(re.escape(prefix), re.I)).first
        try:
            if not opt.is_visible(timeout=2500):
                opt = p.get_by_test_id("form-wizard-children").locator(
                    "[role='option']").first
            if opt.is_visible(timeout=2000):
                opt.click()
            else:
                p.keyboard.press("Enter")
        except Exception:
            p.keyboard.press("Enter")
        p.wait_for_timeout(500)
        self.shot("cassapp-subscription")
        self._click_named_button(r"^\s*Add\s*$")
        p.wait_for_timeout(800)
        self.shot("cassapp-subscription-added")

        # Add Custom Resources -> CassandraDatacenter -> dc1 -> Apply
        p.get_by_text(re.compile(r"Add Custom Resources?", re.I)).first.click()
        p.wait_for_timeout(800)
        p.get_by_text(re.compile(rf"^\s*{re.escape(cr_kind)}\s*$", re.I)).first.click()
        p.wait_for_timeout(500)
        p.get_by_text(re.compile(rf"^\s*{re.escape(cr_object)}\s*$", re.I)).first.click()
        p.wait_for_timeout(500)
        self.shot("cassapp-cr-selected")
        self._click_named_button(r"^\s*Apply\s*$")
        p.wait_for_timeout(800)
        self.shot("cassapp-cr-applied")

        # Save -> Advanced Configuration (secret + configmap) -> Next -> Create
        self._click_named_button(r"^\s*Save\s*$")
        p.wait_for_timeout(1000)
        self.shot("cassapp-saved")
        self._add_advanced_application_resources()
        self._click_next()
        p.wait_for_timeout(1000)
        self.shot("cassapp-after-next")
        self._click_named_button(r"^\s*Create\s*$")
        p.wait_for_timeout(2000)
        self.shot("cassapp-created")
        self._finish()
        self._ensure_backupplans_ready()
        print(f"[cassandra] Application plan '{plan_name}' created "
              f"(operator={operator}, {cr_kind}/{cr_object})")

    def _add_advanced_application_resources(self):
        """Advanced Configuration -> secret + configmap as SpecificObject."""
        p = self.page
        p.get_by_text(re.compile(r"Advanced Configuration", re.I)).first.click()
        p.wait_for_timeout(800)
        p.get_by_text(re.compile(r"Add Application Resource", re.I)).first.click()
        p.wait_for_timeout(800)
        p.get_by_text(re.compile(r"^\s*Resources?\s*$", re.I)).first.click()
        p.wait_for_timeout(1000)
        self.shot("cassapp-advanced-resources")

        self._search_and_add_specific_object("secret", "cassandra-app-secret")
        self._search_and_add_specific_object("configmap", "cassandra-config")

        self._click_named_button(r"^\s*Add\s*$")
        p.wait_for_timeout(800)
        self.shot("cassapp-advanced-added")

    def _search_and_add_specific_object(self, kind: str, object_name: str):
        """Search dropdown (placeholder Search) -> type kind -> Enter ->
        SpecificObject -> name -> Apply."""
        p = self.page
        try:
            p.get_by_text(re.compile(r"^\s*Search\s*$", re.I)).last.click()
        except Exception:
            p.locator("div").filter(has_text=re.compile(r"^\s*Search\s*$")).nth(1).click()
        p.wait_for_timeout(400)
        rs = p.locator("input[id^='react-select'][id$='-input']").last
        try:
            rs.fill(kind)
        except Exception:
            p.keyboard.type(kind, delay=50)
        p.wait_for_timeout(600)
        p.keyboard.press("Enter")
        p.wait_for_timeout(800)
        self.shot(f"cassapp-searched-{kind}")

        p.get_by_text(re.compile(r"SpecificObject", re.I)).first.click()
        p.wait_for_timeout(500)
        p.get_by_text(re.compile(rf"^\s*{re.escape(object_name)}\s*$", re.I)).first.click()
        p.wait_for_timeout(500)
        self._click_named_button(r"^\s*Apply\s*$")
        p.wait_for_timeout(800)
        self.shot(f"cassapp-applied-{kind}")

    def _click_next(self):
        p = self.page
        try:
            p.get_by_test_id("form-wizard-children").get_by_role(
                "button", name=re.compile(r"^\s*Next\s*$", re.I)).click(timeout=5000)
        except Exception:
            p.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)).first.click()
        p.wait_for_timeout(800)

    def _click_named_button(self, pattern: str):
        p = self.page
        btn = self.find_enabled_button(pattern)
        if btn is not None:
            btn.click(timeout=8000)
            return
        p.get_by_role("button", name=re.compile(pattern, re.I)).last.click()

    def trigger_backup(self, plan: str, backup_name: str, namespace: str = ""):
        """Select the Cassandra plan, Create Backup, name it, create."""
        p = self.page
        self.open()
        p.wait_for_timeout(1000)

        ns = namespace or self.cfg.cassandra.namespace
        if ns:
            self._filter_by_namespace(ns)

        row = p.locator("tr, [role='row']").filter(has_text=plan).first
        row.wait_for(state="visible", timeout=15000)
        row.scroll_into_view_if_needed()
        self.shot("cass-backup-plan-row")

        cb = row.get_by_role("checkbox", name=re.compile(r"toggle\s*row\s*selected", re.I))
        if not cb.is_visible(timeout=2000):
            cb = row.locator("input[type='checkbox'], [role='checkbox']").first
        cb.check()
        p.wait_for_timeout(500)

        p.get_by_role("button", name=re.compile(r"^\s*Create Backup\s*$", re.I)).click()
        p.wait_for_timeout(1500)
        self.shot("cass-backup-create-popup")

        name_box = p.get_by_role("textbox", name=re.compile(r"^\s*Name\s*$", re.I)).first
        if not name_box.is_visible(timeout=2000):
            name_box = p.get_by_placeholder(re.compile(r"name", re.I)).first
        name_box.click()
        name_box.fill(backup_name)
        self.shot("cass-backup-name-filled")

        try:
            p.get_by_role("button", name="Create", exact=True).click()
        except Exception:
            btn = self.find_enabled_button(r"^\s*Create\s*$")
            if btn:
                btn.click()
        settle(p)
        self.shot("cass-backup-triggered")

    def create_backup_and_wait(self, plan: str, backup_name: str,
                               namespace: str = "", timeout_s: int = 2700):
        """Keep STATUS LOG open until Available/Failed, then close it.

        Backup progress is read from the UI only — no kubectl/CR poll.
        """
        self.trigger_backup(plan=plan, backup_name=backup_name, namespace=namespace)
        print(f"[cassandra] STATUS LOG open — waiting for backup '{backup_name}'")
        self._wait_backup_status_log(timeout_s=timeout_s)
        self._close_status_popup()
        print(f"[cassandra] backup '{backup_name}' done on STATUS LOG "
              f"(plan '{plan}') — popup closed")

    def verify_plan_available(self, plan_name: str):
        self.open()
        self.wait_for_status(plan_name, "Available", timeout_s=600)

    def _finish(self):
        """Walk Next -> Skip & Create -> Finish. Wait out the loading overlay."""
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
            try:
                p.locator("div.overlay").first.wait_for(state="hidden", timeout=10000)
            except Exception:
                pass
            try:
                if not p.get_by_test_id("form-wizard-container").first.is_visible(timeout=1500):
                    self.shot("cassbp-created")
                    return
            except Exception:
                self.shot("cassbp-created")
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
        self.shot("cassbp-finish-timeout")
        raise AssertionError(
            "Cassandra backup-plan wizard did not finish — see "
            f"{self.cfg.screenshot_dir}/cassbp-finish-timeout.png")

    def _filter_by_namespace(self, namespace: str):
        p = self.page
        try:
            trigger = p.get_by_text(re.compile(r"Namespace\s*:", re.I)).last
            if not trigger.is_visible(timeout=2000):
                return
            trigger.click()
            p.wait_for_timeout(600)
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
                try:
                    p.get_by_text(re.compile(r"^\s*BACKUP PLANS\s*$", re.I)).first.click()
                except Exception:
                    p.keyboard.press("Escape")
                p.wait_for_timeout(800)
            else:
                p.keyboard.press("Escape")
        except Exception:
            print(f"[cassandra] could not filter plans by '{namespace}'")

    def _overlay_up(self) -> bool:
        try:
            return self.page.locator("div.overlay").first.is_visible(timeout=800)
        except Exception:
            return False

    def _status_log_open(self) -> bool:
        if "status-log" in (self.page.url or ""):
            return True
        try:
            return self.page.get_by_text(re.compile(r"^\s*STATUS LOG\s*$", re.I)).first.is_visible(
                timeout=800)
        except Exception:
            return False

    def _goto_backupplans_list(self):
        base = self.cfg.cluster.trilio_url.split("#/")[0].rstrip("/")
        self.page.goto(f"{base}/#/backup-recovery/backupplans",
                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)

    def _reload_backupplans_list(self):
        """Land on the Backup Plans list and reload so the SPA modal unmounts."""
        print("[cassandra] reloading Backup Plans list")
        self._goto_backupplans_list()
        try:
            self.page.reload(wait_until="domcontentloaded")
            self.page.wait_for_timeout(1500)
        except Exception:
            pass

    def _ensure_backupplans_ready(self):
        """If a leftover STATUS LOG/overlay is blocking the list, reload."""
        if self._status_log_open() or self._overlay_up():
            self._reload_backupplans_list()

    def _status_log_panel(self):
        """The STATUS LOG modal — not the Backup Plans list behind it."""
        p = self.page
        try:
            wiz = p.get_by_test_id("form-wizard-container").last
            if wiz.is_visible(timeout=800):
                return wiz
        except Exception:
            pass
        title = p.get_by_text(re.compile(r"^\s*STATUS LOG\s*$", re.I)).first
        return title.locator("xpath=ancestor::*[contains(@class,'app-panel') "
                             "or contains(@class,'d-block')][1]")

    def _wait_backup_status_log(self, timeout_s: int = 2700):
        """Leave the modal open. Poll it until Available or Failed."""
        p = self.page
        deadline = time.time() + timeout_s
        saw_progress = False
        fail_pat = re.compile(r"\b(Failed|Error)\b", re.I)
        while time.time() < deadline:
            panel = self._status_log_panel()
            try:
                if panel.get_by_text(re.compile(r"In\s*Progress", re.I)).first.is_visible(
                        timeout=800):
                    saw_progress = True
            except Exception:
                pass
            try:
                if saw_progress and panel.get_by_text(fail_pat).first.is_visible(timeout=800):
                    self.shot("cass-backup-failed")
                    raise AssertionError(
                        "Backup reported Failed on STATUS LOG — see "
                        f"{self.cfg.screenshot_dir}/cass-backup-failed.png")
            except AssertionError:
                raise
            except Exception:
                pass
            if saw_progress and self._backup_finished():
                self.shot("cass-backup-complete-popup")
                print("[cassandra] STATUS LOG shows Available")
                return
            remaining = int(deadline - time.time())
            print(f"[cassandra] STATUS LOG still InProgress ({remaining}s left)")
            p.wait_for_timeout(15000)
        self.shot("cass-backup-wait-timeout")
        raise TimeoutError(
            f"STATUS LOG did not reach Available/Failed within {timeout_s}s")

    def _backup_finished(self) -> bool:
        """True when the STATUS LOG modal has no InProgress and shows Available
        or Cleanup Completed. Ignores 'Available' on the plan list behind it."""
        try:
            panel = self._status_log_panel()
        except Exception:
            return False
        try:
            if panel.get_by_text(re.compile(r"In\s*Progress", re.I)).first.is_visible(
                    timeout=800):
                return False
        except Exception:
            pass
        try:
            if panel.get_by_text(re.compile(r"\bAvailable\b", re.I)).first.is_visible(
                    timeout=500):
                return True
        except Exception:
            pass
        try:
            rows = panel.get_by_text(re.compile(r"\bCleanup\b", re.I))
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
        """Close STATUS LOG after the backup is done (×, then reload if stuck)."""
        p = self.page
        if not self._status_log_open() and not self._overlay_up():
            return
        try:
            x = p.get_by_test_id("close-svg").last
            if x.is_visible(timeout=3000):
                x.click(timeout=4000, force=True)
                p.wait_for_timeout(800)
                print("[cassandra] STATUS LOG closed (×)")
        except Exception:
            pass
        if self._status_log_open() or self._overlay_up():
            try:
                p.keyboard.press("Escape")
                p.wait_for_timeout(500)
            except Exception:
                pass
        if self._status_log_open() or self._overlay_up():
            print("[cassandra] STATUS LOG still open after × — reload list")
            self._reload_backupplans_list()
