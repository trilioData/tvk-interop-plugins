"""Hooks page, plus the hook sub-form shared by backup plans and restores.

Create Hook (from the Hooks listing), following the console recording:
  Backup & Recovery -> Hooks -> Create New
  Namespace placeholder 'Select Namespace' -> type the namespace, Enter
  Name placeholder 'Enter Hook Name'
  POST, then PRE
  Timeout(sec), Max Retry Count
  Add Command x3: /bin/sh, -c, sync
  PRE, then POST
  Add Command x3 again
  Create

Backup-plan and restore hook configuration follows the Cassandra example:
select the hook, match the pod labels, and set the pod and container regex.
"""
import re

from pages.base_page import BasePage, settle


class HooksPage(BasePage):

    def open(self):
        from pages.dashboard_page import DashboardPage
        DashboardPage(self.page, self.cfg).goto_section("hooks")

    # ---------- create hook ----------

    def create_hook(self, hook: dict):
        """Create `hook` from the Hooks page. `hook` is hook_payload(cfg)."""
        p = self.page
        self.open()
        p.wait_for_timeout(800)
        self.click_create_new()
        p.wait_for_timeout(1000)
        self.shot("hook-create-form")

        self._select_namespace_enter(hook["namespace"])
        name_box = p.get_by_placeholder("Enter Hook Name")
        if not name_box.is_visible(timeout=3000):
            name_box = p.get_by_role(
                "textbox", name=re.compile(r"hook\s*name|^\s*name", re.I)).last
        name_box.click()
        name_box.fill(hook["name"])
        self.shot("hook-name-filled")

        # POST then PRE leaves the PRE section active for the first command.
        self._click_phase("POST")
        self._click_phase("PRE")
        self._fill_limits(hook)
        for command in hook["commands"]:
            self._add_command(command)
        self.shot("hook-pre-commands")

        # PRE then POST switches to the POST section for the same command.
        self._click_phase("PRE")
        self._click_phase("POST")
        # POST gains its own Timeout / Max Retry Count. Filling any POST
        # field makes the rest of that section required, so set the same
        # limits here when those inputs are still empty.
        self._fill_limits(hook, only_empty=True)
        for command in hook["commands"]:
            self._add_command(command)
        self.shot("hook-post-commands")

        self._click_create()
        self.shot("hook-created")

    def _select_namespace_enter(self, namespace: str):
        """Searchable Namespace dropdown. Type the namespace and press Enter."""
        p = self.page
        trigger = p.get_by_placeholder(re.compile(r"^\s*Select Namespace\s*$", re.I))
        try:
            if not trigger.first.is_visible(timeout=2000):
                trigger = p.get_by_text(re.compile(r"^\s*Select Namespace\s*$"))
        except Exception:
            trigger = p.get_by_text(re.compile(r"^\s*Select Namespace\s*$"))
        trigger.last.click()
        p.wait_for_timeout(500)
        typed = False
        rs = p.locator("input[id^='react-select'][id$='-input']").last
        try:
            if rs.is_visible(timeout=2000):
                rs.fill(namespace)
                typed = True
        except Exception:
            typed = False
        if not typed:
            p.keyboard.type(namespace, delay=40)
        p.wait_for_timeout(800)
        p.keyboard.press("Enter")
        p.wait_for_timeout(500)
        # Enter selects the highlighted row. If the list is still open, click
        # the exact namespace.
        option = p.get_by_role("option", name=namespace, exact=True)
        try:
            if option.first.is_visible(timeout=1000):
                option.first.click()
                p.wait_for_timeout(300)
        except Exception:
            pass
        self.shot("hook-namespace-selected")

    def _click_phase(self, phase: str):
        p = self.page
        exact = re.compile(rf"^\s*{phase}\s*$", re.I)
        target = self._last_visible(p.get_by_role("button", name=exact))
        if target is None:
            target = self._last_visible(p.get_by_text(exact))
        if target is None:
            self.shot(f"hook-phase-{phase.lower()}-missing")
            raise AssertionError(
                f"'{phase}' option is not on the hook form — see "
                f"{self.cfg.screenshot_dir}/hook-phase-{phase.lower()}-missing.png")
        target.click()
        p.wait_for_timeout(500)
        self.shot(f"hook-phase-{phase.lower()}")

    def _fill_limits(self, hook: dict, only_empty: bool = False):
        self._fill_labeled(r"Timeout\s*\(\s*sec\s*\)", str(hook["timeout_seconds"]),
                           only_empty=only_empty)
        self._fill_labeled(r"Max\s*Retry\s*Count", str(hook["max_retry_count"]),
                           only_empty=only_empty)
        self.shot("hook-limits")

    def _add_command(self, command: str):
        p = self.page
        add = self._last_visible(p.get_by_role(
            "button", name=re.compile(r"^\s*Add Command\s*$", re.I)))
        if add is None:
            add = self._last_visible(p.get_by_text(re.compile(r"Add Command", re.I)))
        if add is None:
            self.shot("hook-add-command-missing")
            raise AssertionError("Add Command is not visible on the hook form")
        add.click()
        p.wait_for_timeout(400)
        boxes = p.get_by_placeholder(re.compile(r"^\s*Enter Command\s*$", re.I))
        empty = []
        for box in boxes.all():
            try:
                if box.is_visible() and not (box.input_value() or "").strip():
                    empty.append(box)
            except Exception:
                continue
        if not empty:
            self.shot("hook-command-field-missing")
            raise AssertionError(
                f"No empty 'Enter Command' field for {command!r}")
        empty[-1].click()
        empty[-1].fill(command)
        p.wait_for_timeout(200)
        print(f"[hooks] command {command!r}")

    def _click_create(self):
        p = self.page
        clicked = False
        for _ in range(20):
            btn = self.find_enabled_button(r"^\s*Create\s*$")
            if btn is not None:
                btn.click()
                clicked = True
                break
            p.wait_for_timeout(1000)
        if not clicked:
            self.shot("hook-create-disabled")
            raise AssertionError(
                "Create stayed disabled on the hook form — see "
                f"{self.cfg.screenshot_dir}/hook-create-disabled.png")
        settle(p)
        p.wait_for_timeout(1500)
        # A still-open name field means Create did not accept the form.
        try:
            name_box = p.get_by_placeholder("Enter Hook Name")
            if name_box.is_visible(timeout=1500):
                self.shot("hook-create-rejected")
                raise AssertionError(
                    "Create Hook dialog is still open after Create — see "
                    f"{self.cfg.screenshot_dir}/hook-create-rejected.png")
        except AssertionError:
            raise
        except Exception:
            pass

    # ---------- hook configuration on a backup plan / restore ----------

    def add_plan_hook(self, hook: dict):
        """Step 1 of Create Backup Plan: Advanced -> Add Hook -> select the
        hook, label set, pod regex, container regex."""
        p = self.page
        self._expand_advanced()
        self._click_text_button(r"Add\s+Hook")
        p.wait_for_timeout(800)
        self.shot("hook-plan-form")
        self._pick_hook(hook["name"])
        self._fill_regexes(hook)
        self._add_label_set(hook["labels"])
        self._commit_adds()
        self.shot("hook-plan-configured")
        print(f"[hooks] backup plan hook '{hook['name']}' configured")

    def add_restore_hook(self, hook: dict):
        """Restore wizard hook step. Adds the hook when the wizard offers
        Add hook; accepts a prefilled hook confirmation otherwise."""
        p = self.page
        if not self._text_visible(r"Add\s+hook"):
            nxt = self.find_enabled_button(r"^\s*Next\s*$")
            if nxt is not None:
                nxt.click()
                p.wait_for_timeout(1000)
        if self._text_visible(r"Add\s+hook"):
            self._click_text_button(r"\+?\s*Add\s+hook")
            p.wait_for_timeout(800)
            self.shot("hook-restore-form")
            self._pick_hook(hook["name"])
            self._fill_regexes(hook)
            self._add_label_set(hook["labels"])
            self._commit_adds()
            self.shot("hook-restore-configured")
            print(f"[hooks] restore hook '{hook['name']}' configured")
            return
        if self._text_visible(re.escape(hook["name"])):
            print(f"[hooks] restore wizard already lists '{hook['name']}'")
            self.shot("hook-restore-prefilled")
            return
        self.shot("hook-restore-missing")
        raise AssertionError(
            "Restore wizard has no hook step — see "
            f"{self.cfg.screenshot_dir}/hook-restore-missing.png")

    def _expand_advanced(self):
        p = self.page
        advanced = self._last_visible(p.get_by_role(
            "button", name=re.compile(r"Advanced", re.I)))
        if advanced is None:
            advanced = self._last_visible(
                p.get_by_text(re.compile(r"^\s*Advanced\s*$", re.I)))
        if advanced is None:
            self.shot("hook-advanced-missing")
            raise AssertionError(
                "Advanced section is not on the backup plan form — see "
                f"{self.cfg.screenshot_dir}/hook-advanced-missing.png")
        advanced.click()
        p.wait_for_timeout(700)
        self.shot("hook-advanced-expanded")

    def _pick_hook(self, name: str):
        """Select the hook from its searchable dropdown and press Enter."""
        p = self.page
        trigger = None
        for pattern in (r"^\s*Select Hook\s*$", r"^\s*Select\s*$"):
            trigger = self._last_visible(p.get_by_text(re.compile(pattern)))
            if trigger is not None:
                break
        if trigger is None:
            self.shot("hook-dropdown-missing")
            raise AssertionError("Hook dropdown was not found")
        trigger.click()
        p.wait_for_timeout(400)
        rs = p.locator("input[id^='react-select'][id$='-input']").last
        try:
            if rs.is_visible(timeout=1500):
                rs.fill(name)
            else:
                p.keyboard.type(name, delay=40)
        except Exception:
            p.keyboard.type(name, delay=40)
        p.wait_for_timeout(700)
        p.keyboard.press("Enter")
        p.wait_for_timeout(400)
        option = p.get_by_role("option", name=name, exact=True)
        try:
            if option.first.is_visible(timeout=800):
                option.first.click()
        except Exception:
            pass
        self.shot("hook-selected")

    def _fill_regexes(self, hook: dict):
        # Pod selector is above Container Name Matching on the form. Skip an
        # input already holding the other value so one heading cannot overwrite
        # the other field.
        self._fill_labeled(r"Pod\s+(Selection|Regex)", hook["pod_regex"],
                           required=False)
        self._fill_labeled(r"Container", hook["container_regex"], required=False,
                           skip_value=hook["pod_regex"])

    def _add_label_set(self, labels: dict):
        p = self.page
        opener = self._last_visible(
            p.get_by_text(re.compile(r"Add\s+Label\s*Set", re.I)))
        if opener is None:
            self.shot("hook-label-set-missing")
            raise AssertionError(
                "Add Label Set is not on the hook configuration form — see "
                f"{self.cfg.screenshot_dir}/hook-label-set-missing.png")
        opener.click()
        p.wait_for_timeout(600)
        match_tab = self._last_visible(
            p.get_by_text(re.compile(r"^\s*Match Labels\s*$", re.I)))
        if match_tab is not None:
            match_tab.click()
            p.wait_for_timeout(400)
        for key, value in labels.items():
            self._apply_one_label(key, value)
        # Commit the label set itself (its own Add), leaving the outer hook
        # Add for _commit_adds.
        add = self.find_enabled_button(r"^\s*Add\s*$")
        if add is None:
            self.shot("hook-label-add-missing")
            raise AssertionError("Label set has no enabled Add button")
        add.click()
        p.wait_for_timeout(600)
        self.shot("hook-labels-added")

    def _apply_one_label(self, key: str, value: str):
        """Pick `key=value` from the labels dropdown and click Apply."""
        p = self.page
        trigger = None
        for pattern in (r"Select Labels", r"^\s*Labels\s*$", r"^\s*Select\s*$"):
            trigger = self._last_visible(p.get_by_text(re.compile(pattern, re.I)))
            if trigger is not None:
                break
        if trigger is None:
            rs = p.locator("input[id^='react-select'][id$='-input']").last
            rs.click()
        else:
            trigger.click()
        p.wait_for_timeout(400)
        p.keyboard.type(key, delay=40)
        p.wait_for_timeout(700)
        wanted = re.compile(rf"{re.escape(key)}.+{re.escape(value)}", re.I)
        option = p.get_by_role("option").filter(has_text=wanted)
        picked = False
        try:
            if option.first.is_visible(timeout=1500):
                option.first.click()
                picked = True
        except Exception:
            picked = False
        if not picked:
            p.keyboard.type(f"={value}", delay=40)
            p.keyboard.press("Enter")
        p.wait_for_timeout(300)
        apply = self.find_enabled_button(r"^\s*Apply\s*$")
        if apply is None:
            self.shot(f"hook-label-apply-missing-{key}")
            raise AssertionError(
                f"Could not apply label {key}={value} — see "
                f"{self.cfg.screenshot_dir}/hook-label-apply-missing-{key}.png")
        apply.click()
        p.wait_for_timeout(400)
        print(f"[hooks] label {key}={value}")

    def _commit_adds(self, max_clicks: int = 3):
        """Click Add until the hook sub-form is gone (label set, then hook)."""
        p = self.page
        for i in range(max_clicks):
            btn = self.find_enabled_button(r"^\s*Add\s*$")
            if btn is None:
                return
            btn.click()
            p.wait_for_timeout(800)
            self.shot(f"hook-add-{i}")

    # ---------- small locators ----------

    def _fill_labeled(self, label_re: str, value: str, required: bool = True,
                      only_empty: bool = False, skip_value: str | None = None):
        box = self._input_near_label(label_re, skip_value=skip_value)
        if box is None:
            if required:
                self.shot("hook-field-missing")
                raise AssertionError(
                    f"No input near label /{label_re}/ — see "
                    f"{self.cfg.screenshot_dir}/hook-field-missing.png")
            print(f"[hooks] optional field /{label_re}/ not shown")
            return
        current = ""
        try:
            current = box.input_value() or ""
        except Exception:
            current = ""
        if only_empty and current.strip():
            return
        box.click()
        box.fill(str(value))
        print(f"[hooks] filled /{label_re}/ = {value}")

    def _input_near_label(self, label_re: str, skip_value: str | None = None):
        """The next visible input after a visible matching label.

        Timeout and Max Retry Count have no placeholder; the label text is
        the only handle. The search stays on inputs that follow the label so
        a large ancestor form cannot hand back an unrelated field.
        """
        p = self.page
        labels = p.get_by_text(re.compile(label_re, re.I))
        try:
            nodes = labels.all()
        except Exception:
            return None
        for label in nodes:
            try:
                if not label.is_visible():
                    continue
            except Exception:
                continue
            following = label.locator("xpath=following::input[not(@type='hidden')]")
            try:
                count = min(following.count(), 4)
            except Exception:
                count = 0
            for index in range(count):
                box = following.nth(index)
                try:
                    if not box.is_visible():
                        continue
                    current = box.input_value() or ""
                except Exception:
                    continue
                if skip_value is not None and current == str(skip_value):
                    continue
                return box
        return None

    def _click_text_button(self, pattern: str):
        p = self.page
        target = self._last_visible(p.get_by_role(
            "button", name=re.compile(pattern, re.I)))
        if target is None:
            target = self._last_visible(p.get_by_text(re.compile(pattern, re.I)))
        if target is None:
            self.shot("hook-control-missing")
            raise AssertionError(
                f"Control /{pattern}/ not found — see "
                f"{self.cfg.screenshot_dir}/hook-control-missing.png")
        target.click()

    def _text_visible(self, pattern: str) -> bool:
        try:
            return self._last_visible(
                self.page.get_by_text(re.compile(pattern, re.I))) is not None
        except Exception:
            return False

    @staticmethod
    def _last_visible(locator):
        try:
            visible = [node for node in locator.all() if node.is_visible()]
        except Exception:
            return None
        return visible[-1] if visible else None
