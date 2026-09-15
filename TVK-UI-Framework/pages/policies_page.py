"""Policies page object — scheduling policies.

Selectors verified against Playwright codegen of the real UI:
  Create New -> popup
    1. Namespace: react-select ('Select Namespace' container) — type to
       filter, then click the option inside form-wizard-children
    2. Scheduling Policy Name textbox
    3. Click the '| Weekly' link (the visible text includes the pipe)
    4. Weekly section: pick day (Sun..Sat), set time via #schedule-time
    5. Create
"""
import re

from pages.base_page import BasePage, settle

# Map full day names to the abbreviations shown in the weekly picker
_DAY_ABBR = {
    "sunday": "Sun", "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed",
    "thursday": "Thu", "friday": "Fri", "saturday": "Sat",
}


class PoliciesPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("policies")

    def create_scheduling_policy(self, day: str = "Sunday", time_value: str = "10"):
        c = self.cfg
        p = self.page
        self.open()
        self.click_create_new()
        p.wait_for_timeout(1500)
        self.shot("policy-create-form")

        # 1. Namespace — aligned with the other resources: configured
        # policy_namespace if set (standalone runs), else the app namespace
        # (integrated runs create everything in the same namespace).
        ns = c.res_ns(c.policy_namespace)
        self._select_react_namespace(ns)
        self.shot("policy-namespace-selected")

        # 2. Scheduling Policy Name
        name_box = p.get_by_role("textbox", name=re.compile(r"scheduling\s*policy\s*name", re.I))
        name_box.click()
        name_box.fill(c.policy_name)
        self.shot("policy-name-filled")

        # 3. Click the '| Weekly' interval link (text includes the pipe)
        weekly = p.get_by_text("| Weekly")
        if not weekly.is_visible(timeout=3000):
            weekly = p.get_by_text(re.compile(r"\bWeekly\b", re.I)).last
        weekly.click()
        p.wait_for_timeout(1500)
        self.shot("policy-weekly-popup")

        # 4. Weekly section — select day, set time
        abbr = _DAY_ABBR.get(day.lower(), "Sun")
        try:
            day_el = p.get_by_text(abbr, exact=True).last
            if day_el.is_visible(timeout=2000):
                day_el.click()
                p.wait_for_timeout(500)
        except Exception:
            print(f"[policies] Day '{abbr}' not found — keeping default")

        self._set_schedule_time(time_value)
        self.shot("policy-time-filled")

        # 5. Create
        create_btn = self.find_enabled_button(r"^\s*create\s*$")
        if create_btn is None:
            self.advance_wizard_to_create(name_prefix="policy", fill_name=c.policy_name)
        else:
            create_btn.click()
            settle(p)
        self.shot("policy-created")

    def _select_react_namespace(self, namespace: str):
        """react-select namespace picker (codegen pattern)."""
        p = self.page
        container = p.locator("div").filter(has_text=re.compile(r"^Select Namespace$")).nth(1)
        try:
            container.click()
        except Exception:
            # fallback: any 'Select Namespace' text trigger
            p.get_by_text(re.compile(r"select\s*namespace", re.I)).last.click()
        p.wait_for_timeout(500)

        # Type into the focused react-select input to filter, then pick option
        typed = False
        rs_input = p.locator("input[id^='react-select'][id$='-input']").last
        try:
            if rs_input.is_visible(timeout=2000):
                rs_input.fill(namespace[:5])
                typed = True
                p.wait_for_timeout(800)
        except Exception:
            pass
        if not typed:
            p.keyboard.type(namespace[:5], delay=50)
            p.wait_for_timeout(800)

        option = p.get_by_test_id("form-wizard-children").get_by_text(namespace, exact=True)
        if not option.is_visible(timeout=2000):
            option = p.get_by_text(namespace, exact=True).last
        option.click()
        p.wait_for_timeout(500)

    @staticmethod
    def _norm_time(value: str) -> str:
        """Normalize a time to HH:MM (an <input type=time> requires it).
        '10' -> '10:00', '9:5' -> '09:05', '10:30' -> '10:30'."""
        v = str(value).strip()
        h, _, m = v.partition(":")
        try:
            h = int(h or 0)
            m = int(m or 0)
        except ValueError:
            h, m = 0, 0
        return f"{h % 24:02d}:{m % 60:02d}"

    def _set_schedule_time(self, time_value: str):
        """Set the #schedule-time picker. Opens the dropdown (clock) and
        selects the hour/minute cells; falls back to typing the digits."""
        p = self.page
        hhmm = self._norm_time(time_value)
        hh, mm = hhmm.split(":")
        field = p.locator("#schedule-time")
        field.scroll_into_view_if_needed()
        field.click()
        p.wait_for_timeout(800)
        self.shot("policy-time-dropdown")

        def value_now():
            return (field.input_value() or "").strip()

        # 1) Select from the time-panel dropdown (hour column, then minute)
        try:
            cols = p.locator(".ant-picker-time-panel-column")
            if cols.count() >= 2:
                for col_idx, want in ((0, hh), (1, mm)):
                    cell = cols.nth(col_idx).locator(
                        ".ant-picker-time-panel-cell-inner").filter(
                        has_text=re.compile(rf"^\s*{int(want)}\s*$|^\s*{want}\s*$")).first
                    cell.scroll_into_view_if_needed()
                    cell.click()
                    p.wait_for_timeout(400)
                # confirm with OK if the panel has one
                ok = p.get_by_role("button", name=re.compile(r"^\s*OK\s*$", re.I)).first
                if ok.is_visible(timeout=1500):
                    ok.click()
                    p.wait_for_timeout(300)
        except Exception as e:
            print(f"[policies] time-panel selection skipped ({e})")

        # 2) Fallback: type the digits if the value still isn't set
        if value_now() in ("", "00:00") and hhmm != "00:00":
            try:
                field.click()
                p.keyboard.type(hh + mm, delay=120)
                p.wait_for_timeout(300)
            except Exception:
                pass
        # 3) Last resort: set value directly
        if value_now() in ("", "00:00") and hhmm != "00:00":
            try:
                field.fill(hhmm)
            except Exception:
                pass
        # Dismiss the time dropdown by clicking a neutral field INSIDE the
        # modal (NOT Escape — that would close the whole Create dialog)
        try:
            p.get_by_role("textbox", name=re.compile(
                r"scheduling\s*policy\s*name", re.I)).first.click(timeout=2000)
        except Exception:
            pass
        print(f"[policies] schedule time set to '{value_now()}' (wanted {hhmm})")

    # Backwards-compatible alias (older tests called this)
    def create_retention_policy(self, latest: int = 5, daily: int = 7):
        self.create_scheduling_policy()

    def verify_policy_exists(self):
        """Confirm the policy we just created shows up in the Policies list.
        The list loads asynchronously (spinner) after a search, so poll the
        row over time instead of checking once."""
        p = self.page
        name = self.cfg.policy_name
        self.open()
        p.wait_for_timeout(1500)

        def search_for_name():
            try:
                box = p.get_by_placeholder(re.compile(r"search", re.I)).first
                if box.is_visible(timeout=2000):
                    box.fill("")
                    box.fill(name)
                    p.wait_for_timeout(1200)
            except Exception:
                pass

        search_for_name()
        # Poll up to ~40s for the row, waiting out the loading spinner and
        # re-issuing the search a couple of times
        for attempt in range(20):
            try:
                if p.locator("tr, [role='row']").filter(
                        has_text=name).first.is_visible(timeout=1500):
                    self.shot("policy-exists")
                    print(f"[policies] verified policy '{name}' in the list")
                    return
            except Exception:
                pass
            if attempt in (6, 12):           # re-trigger search periodically
                search_for_name()
            p.wait_for_timeout(1500)

        self.shot("policy-not-found")
        raise AssertionError(f"Policy {name} not found in the Policies list")
