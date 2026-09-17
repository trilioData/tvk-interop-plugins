"""Base page object with shared helpers for all Trilio UI pages."""
import re
import time
from playwright.sync_api import Page, expect

from config.settings import FrameworkConfig


def settle(page: Page, timeout_ms: int = 15000):
    """Best-effort wait for the console to go quiet after a navigation/click.

    The Trilio console polls continuously, so 'networkidle' (500ms with no
    network traffic) is frequently never reached — noticeably so when the UI is
    reached through a port-forward. A bare wait_for_load_state("networkidle")
    then raises at the page default timeout and fails the test even though the
    page is perfectly usable. Wait briefly, fall back to domcontentloaded, and
    never propagate: settling is an optimisation, not an assertion.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass


class BasePage:
    def __init__(self, page: Page, cfg: FrameworkConfig):
        self.page = page
        self.cfg = cfg

    # ---------- generic helpers ----------

    def shot(self, name: str):
        self.page.screenshot(path=f"{self.cfg.screenshot_dir}/{name}.png", full_page=True)

    def click_text(self, pattern: str, role_hint: str = "button, a, [role='menuitem'], [role='tab']"):
        """Click first element matching the text pattern (case-insensitive)."""
        pat = re.compile(pattern, re.I)
        loc = self.page.locator(role_hint).filter(has_text=pat).first
        try:
            loc.wait_for(state="visible", timeout=15000)
        except Exception:
            # Fallback: any element with matching text (clickable divs/spans)
            loc = self.page.get_by_text(pat).first
            loc.wait_for(state="visible")
        loc.click()

    def fill_field(self, label_or_placeholder: str, value: str):
        """Fill an input found by label, placeholder, name or id (best-effort)."""
        p = self.page
        candidates = [
            p.get_by_label(re.compile(label_or_placeholder, re.I)),
            p.get_by_placeholder(re.compile(label_or_placeholder, re.I)),
            p.locator(f"input[name*='{label_or_placeholder}' i]"),
            p.locator(f"input[id*='{label_or_placeholder}' i]"),
        ]
        for loc in candidates:
            try:
                if loc.first.is_visible(timeout=2000):
                    loc.first.fill(value)
                    return
            except Exception:
                continue
        raise AssertionError(f"Could not find input for '{label_or_placeholder}'")

    def select_dropdown_option(self, dropdown_hint: str, option_text: str | None = None):
        """Open a dropdown found by hint and pick an option (first if not given)."""
        p = self.page
        dd = p.locator(
            f"[placeholder*='{dropdown_hint}' i], [aria-label*='{dropdown_hint}' i], "
            f"select[name*='{dropdown_hint}' i], [data-testid*='{dropdown_hint}' i]"
        ).first
        dd.wait_for(state="visible")
        dd.click()
        if option_text:
            p.locator("[role='option'], li, .ant-select-item").filter(
                has_text=re.compile(option_text, re.I)).first.click()
        else:
            p.locator("[role='option'], li.ant-select-item").first.click()

    def wait_for_status(self, row_text: str, expected: str = "Available|Success|Completed",
                        timeout_s: int | None = None):
        """Poll a table row containing row_text until its status matches expected."""
        timeout_s = timeout_s or self.cfg.operation_timeout_s
        deadline = time.time() + timeout_s
        pat = re.compile(expected, re.I)
        fail_pat = re.compile("Failed|Error|Unavailable", re.I)
        while time.time() < deadline:
            row = self.page.locator("tr, [role='row']").filter(has_text=row_text).first
            try:
                text = row.inner_text(timeout=5000)
                if pat.search(text):
                    return True
                if fail_pat.search(text):
                    raise AssertionError(f"'{row_text}' entered failed state: {text}")
            except AssertionError:
                raise
            except Exception:
                pass
            self.page.reload()
            settle(self.page)
            time.sleep(10)
        raise TimeoutError(f"'{row_text}' did not reach state '{expected}' in {timeout_s}s")

    def pick_from_custom_dropdown(self, trigger, option_text: str | None = None,
                                  shot_name: str = "dropdown"):
        """Open a custom (React/Ant) dropdown and select an option.

        Options often render in a portal at the end of <body>, outside the
        modal, so they are searched on the whole page. Falls back to typing
        the option text + Enter (works for searchable selects)."""
        p = self.page
        trigger.scroll_into_view_if_needed()
        trigger.click()
        p.wait_for_timeout(800)
        self.shot(f"{shot_name}-opened")

        # Options load asynchronously — poll up to 15s while 'Loading...'
        # is displayed or no options have rendered yet
        count = 0
        options = None
        for _ in range(15):
            loading = p.get_by_text(re.compile(r"^\s*loading", re.I)).last
            try:
                if loading.is_visible(timeout=500):
                    p.wait_for_timeout(1000)
                    continue
            except Exception:
                pass
            options = p.locator(
                "[role='option'], .ant-select-item-option, [class*='option' i], "
                "[class*='menu' i] li, [class*='dropdown' i] li").locator("visible=true")
            try:
                count = options.count()
            except Exception:
                count = 0
            if count:
                break
            p.wait_for_timeout(1000)
        self.shot(f"{shot_name}-options-loaded")

        if count:
            if option_text:
                match = options.filter(has_text=re.compile(option_text, re.I)).first
                if match.is_visible(timeout=2000):
                    match.click()
                    self.shot(f"{shot_name}-selected")
                    return
            options.first.click()
            self.shot(f"{shot_name}-selected")
            return

        # Keyboard fallback: type into the focused search input and pick top hit
        if option_text:
            p.keyboard.type(option_text, delay=50)
            p.wait_for_timeout(800)
            self.shot(f"{shot_name}-typed")
        p.keyboard.press("Enter")
        p.wait_for_timeout(500)
        self.shot(f"{shot_name}-selected")

    def _wait_dropdown_loading(self, timeout_ms: int = 30000):
        """If the react-select shows Loading, wait until it is gone."""
        p = self.page
        for loc in (
            p.get_by_text(re.compile(r"^\s*Loading", re.I)),
            p.locator("[class*='loadingIndicator'], [class*='-loading']"),
        ):
            try:
                if loc.first.is_visible(timeout=800):
                    loc.first.wait_for(state="hidden", timeout=timeout_ms)
                    return
            except Exception:
                continue

    def select_react_dropdown(self, placeholder_regex: str, option_text: str,
                              type_filter: str | None = None, shot_name: str = "dropdown"):
        """Open this dropdown only, wait if Loading, type into the focused
        input (not another Select on the form), then click the option."""
        p = self.page
        container = p.locator("div").filter(
            has_text=re.compile(placeholder_regex)).nth(1)
        try:
            container.click()
        except Exception:
            p.get_by_text(re.compile(placeholder_regex.strip("^$"), re.I)).last.click()
        p.wait_for_timeout(400)
        self._wait_dropdown_loading()

        if type_filter:
            # The control we just opened owns the last react-select input.
            rs = p.locator("input[id^='react-select'][id$='-input']").last
            try:
                if rs.is_visible(timeout=2000):
                    rs.fill(type_filter)
                    p.wait_for_timeout(800)
                else:
                    p.keyboard.type(type_filter, delay=50)
                    p.wait_for_timeout(800)
            except Exception:
                p.keyboard.type(type_filter, delay=50)
                p.wait_for_timeout(800)

        option = p.get_by_test_id("form-wizard-children").get_by_text(
            option_text, exact=True)
        try:
            if not option.is_visible(timeout=2000):
                option = p.get_by_text(option_text, exact=True).last
        except Exception:
            option = p.get_by_text(option_text, exact=True).last
        try:
            option.click(timeout=8000)
        except Exception:
            p.keyboard.press("Enter")
        p.wait_for_timeout(500)
        self.shot(shot_name)

    def find_enabled_button(self, pattern: str):
        """Last VISIBLE enabled button whose text matches pattern, or None."""
        btns = self.page.locator("button:not([disabled])").filter(
            has_text=re.compile(pattern, re.I))
        try:
            candidates = [b for b in btns.all() if b.is_visible()]
            return candidates[-1] if candidates else None
        except Exception:
            return None

    def click_create_new(self):
        """Click the 'Create New' (or similar) button on a listing page."""
        self.click_text(r"create\s*new|create|new|add|\+")

    def advance_wizard_to_create(self, max_steps: int = 8, name_prefix: str = "wizard",
                                 fill_name: str | None = None):
        """Multi-page wizards: keep clicking Next/Continue until a Create/Save/
        Submit/Finish button is visible, then click it. If fill_name is given,
        any empty 'name' input encountered along the way is filled with it."""
        p = self.page
        # Exact button labels only ('Create', not 'Create New'); the popup is
        # appended at the end of the DOM, so .last picks the popup's button
        # rather than same-text buttons on the page behind it.
        # 'Create', 'Create Target', 'Create Backup Plan', 'Save', ... —
        # but never 'Create New' (the page-level listing button)
        final_pat = re.compile(
            r"^\s*(save|submit|finish|create(?!\s*new\b)(\s+[\w-]+)*)\s*$", re.I)
        next_pat = re.compile(r"^\s*(next|continue)\s*$", re.I)

        def enabled(pat):
            """Last VISIBLE, truly-enabled button matching pat (skips hidden
            duplicates and aria-disabled buttons)."""
            btns = p.locator(
                "button:not([disabled]):not([aria-disabled='true'])").filter(has_text=pat)
            try:
                candidates = [b for b in btns.all()
                              if b.is_visible() and b.is_enabled()]
                return candidates[-1] if candidates else None
            except Exception:
                return None

        def try_fill_name():
            if not fill_name:
                return
            inputs = p.locator(
                "input[placeholder*='name' i]:visible, input[name*='name' i]:visible, "
                "input[id*='name' i]:visible")
            try:
                # popups are appended last in the DOM — fill the LAST visible
                # empty name input so the popup's field wins
                candidates = [i for i in inputs.all()
                              if i.is_visible() and not i.input_value()]
                if candidates:
                    candidates[-1].fill(fill_name)
                    p.wait_for_timeout(500)
                    self.shot(f"{name_prefix}-name-filled")
            except Exception:
                pass

        for step in range(max_steps):
            try_fill_name()
            self.shot(f"{name_prefix}-step{step}")

            # Poll up to 60s for an enabled Create/Next button — validation
            # can take a while to enable them after the form is filled.
            # A name popup may appear at any point (e.g. right after
            # Continue), so re-check for an empty name field on every poll.
            clicked_next = False
            for _ in range(30):
                try_fill_name()
                # short click timeouts so a briefly non-actionable button
                # re-loops here instead of hanging the default 60s
                final_btn = enabled(final_pat)
                if final_btn:
                    try:
                        final_btn.click(timeout=5000)
                        settle(p)
                        self.shot(f"{name_prefix}-submitted")
                        return
                    except Exception:
                        p.wait_for_timeout(1500)
                        continue
                next_btn = enabled(next_pat)
                if next_btn:
                    try:
                        next_btn.click(timeout=5000)
                        p.wait_for_timeout(1500)
                        clicked_next = True
                        break
                    except Exception:
                        p.wait_for_timeout(1500)
                        continue
                p.wait_for_timeout(2000)
            if clicked_next:
                continue
            self.shot(f"{name_prefix}-step{step}-stuck")
            raise AssertionError(
                f"Wizard stuck at step {step}: no enabled Create/Next/Continue "
                f"button appeared within 30s (see {self.cfg.screenshot_dir}/"
                f"{name_prefix}-step{step}-stuck.png)")
        raise AssertionError(f"Wizard did not finish within {max_steps} steps")

    def row_exists(self, text: str) -> bool:
        return self.page.locator("tr, [role='row']").filter(has_text=text).first.is_visible(timeout=10000)
