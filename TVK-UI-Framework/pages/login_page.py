"""
Login strategies per cluster type.

Adding a new cluster flavour = subclass BaseLoginPage and register it
in LOGIN_STRATEGIES. Nothing else in the framework changes.
"""
import os
import re

from playwright.sync_api import Page

from config.settings import FrameworkConfig
from pages.base_page import BasePage, settle


class BaseLoginPage(BasePage):
    def login(self):
        raise NotImplementedError

    def _accept_license_if_present(self):
        p = self.page

        # "END USER LICENSE AGREEMENT" modal popup with an "Accept" button
        eula = p.locator("[role='dialog'], .ant-modal, .modal").filter(
            has_text=re.compile("end\\s*user\\s*license\\s*agreement|license\\s*agreement", re.I)).first
        try:
            eula.wait_for(state="visible", timeout=10000)
            self.shot("login-license-screen")
            # Tick agree checkbox inside the dialog, if any
            cb = eula.locator("input[type='checkbox'], [role='checkbox']").first
            try:
                if cb.is_visible(timeout=2000) and not cb.is_checked():
                    cb.check()
            except Exception:
                pass
            eula.locator("button").filter(
                has_text=re.compile(r"^\s*accept\s*$|accept|agree", re.I)).first.click()
            settle(p)
            self.shot("login-license-accepted")
            return
        except Exception:
            pass  # no modal — fall through to full-page EULA check

        body = ""
        try:
            body = p.inner_text("body", timeout=5000).lower()
        except Exception:
            pass
        if not any(w in body for w in ("license", "eula", "terms", "agreement")):
            return

        self.shot("login-license-screen")
        # Tick the "I agree / accept" checkbox if one exists
        checkbox = p.locator("input[type='checkbox'], [role='checkbox']").first
        try:
            if checkbox.is_visible(timeout=3000) and not checkbox.is_checked():
                checkbox.check()
        except Exception:
            pass
        # Click the accept/agree/continue button
        btn = p.locator("button, a, input[type='submit']").filter(
            has_text=re.compile(r"accept|agree|confirm|continue|proceed|ok", re.I)).first
        try:
            if btn.is_visible(timeout=3000):
                btn.click()
                settle(p)
                self.shot("login-license-accepted")
        except Exception:
            pass


class OCPLoginPage(BaseLoginPage):
    """Trilio UI -> 'Sign In via OpenShift' -> OCP OAuth (kube:admin)."""

    def login(self):
        p = self.page
        p.goto(self.cfg.cluster.trilio_url, wait_until="networkidle")
        self.shot("login-01-trilio-login")

        # Click "Sign-in via Openshift" (text varies across versions: "Sign In", "Sign-in"...)
        self.click_text(r"sign[\s\-]*in\s*via\s*openshift")
        settle(p)
        self.shot("login-02-ocp-oauth")

        # Provider selector screen (htpasswd / kube:admin) may appear
        provider = p.locator("a, button").filter(has_text=re.compile("kube:admin", re.I)).first
        try:
            if provider.is_visible(timeout=5000):
                provider.click()
                settle(p)
        except Exception:
            pass

        # Credentials
        p.locator("input#inputUsername, input[name='username'], input#username").first.fill(
            self.cfg.cluster.username)
        p.locator("input#inputPassword, input[name='password'], input#password").first.fill(
            self.cfg.cluster.password)
        self.shot("login-03-credentials")
        p.locator("button[type='submit'], input[type='submit']").first.click()
        settle(p)

        # OAuth approval screen ("Authorize access") may appear on first login
        approve = p.locator("button, input[type='submit']").filter(
            has_text=re.compile("allow|approve|authorize", re.I)).first
        try:
            if approve.is_visible(timeout=5000):
                approve.click()
                settle(p)
        except Exception:
            pass

        # License / EULA agreement screen may appear after first login
        self._accept_license_if_present()

        self.shot("login-04-logged-in")
        assert "login" not in p.url.lower() or "#/login" not in p.url, \
            f"Login appears to have failed, still on: {p.url}"

class VanillaLoginPage(BaseLoginPage):
    """Placeholder: kubeconfig/token-based login for upstream Kubernetes."""

    def login(self):
        raise NotImplementedError(
            "Vanilla K8s login not implemented yet — subclass and implement here.")


class KubeconfigLoginPage(BaseLoginPage):
    """Trilio UI -> upload kubeconfig -> 'Sign-in using Kubeconfig'.

    This is the login the console offers on non-OpenShift clusters (AKS, EKS,
    GKE, upstream K8s): there is no OAuth provider, so the first page takes a
    kubeconfig file directly. The file comes from cluster.kubeconfig, which must
    carry embedded credentials — a kubeconfig relying on an `exec` plugin
    (e.g. kubelogin) cannot be used here, because the console has no way to run it.
    """

    # Hidden-but-present file input rendered behind the "Choose a new file" label.
    FILE_INPUT = "input.custom-file-input, input[type='file']"
    # Matched by text, not by type: the button carries no type attribute, and
    # HTMLButtonElement.type reports "submit" by default — so button[type=submit]
    # looks correct when inspecting via JS but selects nothing in the DOM.
    SUBMIT = "button"
    ERROR_POPUP = ".modal-popup.login-error-popup, .login-error-popup"

    def login(self):
        p = self.page
        kubeconfig = self.cfg.cluster.kubeconfig
        assert kubeconfig, ("cluster.kubeconfig must point at a kubeconfig file for "
                            f"'{self.cfg.cluster.cluster_type}' login")
        assert os.path.isfile(kubeconfig), f"kubeconfig not found: {kubeconfig}"

        p.goto(self.cfg.cluster.trilio_url, wait_until="networkidle")
        self.shot("login-01-kubeconfig-page")

        # Attach the kubeconfig. set_input_files works on the hidden input, so
        # there is no need to click the styled label first.
        p.locator(self.FILE_INPUT).first.set_input_files(kubeconfig)
        self.shot("login-02-kubeconfig-attached")

        p.locator(self.SUBMIT).filter(
            has_text=re.compile(r"sign[\s\-]*in", re.I)).first.click()
        settle(p)

        # The console raises a WARNING popup for a rejected/unusable kubeconfig.
        # 'Yes' is the affirmative on it, so try to proceed, then confirm below
        # whether we actually left the login page.
        popup_text = ""
        popup = p.locator(self.ERROR_POPUP).first
        try:
            if popup.is_visible(timeout=5000):
                popup_text = popup.inner_text(timeout=3000).replace("\n", " ").strip()
                self.shot("login-03-warning-popup")
                print(f"[login] console raised a warning: {popup_text[:200]}")
                popup.locator("button").filter(
                    has_text=re.compile(r"^\s*yes\s*$", re.I)).first.click()
                settle(p)
        except Exception:
            pass

        self._accept_license_if_present()
        self.shot("login-04-logged-in")

        assert "#/login" not in p.url, (
            "Kubeconfig login failed, still on the login page"
            + (f" — console said: {popup_text[:200]}" if popup_text else "")
        )


class CredentialsDbLoginPage(BaseLoginPage):
    """Trilio Manager (master.k8strilio.net) -> upload credentials.db -> Sign in.

    The hosted console has no OpenShift OAuth and does not take a kubeconfig.
    It takes the credentials.db file (same flow as upload_credentials + sign_in
    in the sample LoginPage). After login the UI lands on Cluster Management.
    """

    FILE_INPUT = "input.custom-file-input, input[type='file']"
    SUBMIT = "button"
    CLUSTER_MANAGEMENT = re.compile(r"cluster\s*management", re.I)

    def login(self):
        p = self.page
        creds = self.cfg.cluster.credentials_db
        assert creds, (
            "cluster.credentials_db must point at a credentials.db file for "
            f"'{self.cfg.cluster.cluster_type}' login")
        assert os.path.isfile(creds), f"credentials.db not found: {creds}"

        p.goto(self.cfg.cluster.trilio_url, wait_until="networkidle")
        self.shot("login-01-credentials-page")

        p.locator(self.FILE_INPUT).first.set_input_files(os.path.abspath(creds))
        self.shot("login-02-credentials-attached")

        p.locator(self.SUBMIT).filter(
            has_text=re.compile(r"sign[\s\-]*in", re.I)).first.click()
        settle(p)

        self._accept_license_if_present()
        self.shot("login-03-logged-in")

        cluster_mgmt = p.get_by_text(self.CLUSTER_MANAGEMENT).first
        try:
            cluster_mgmt.wait_for(state="visible", timeout=30000)
        except Exception:
            self.shot("login-cluster-management-missing")
            raise AssertionError(
                "credentials.db login did not reach Cluster Management — still on: "
                f"{p.url} (file={creds})")

        assert "#/login" not in p.url, (
            f"credentials.db login failed, still on the login page: {p.url}")


LOGIN_STRATEGIES = {
    "ocp": OCPLoginPage,
    "vanilla": VanillaLoginPage,
    # Non-OpenShift clusters all present the same kubeconfig-upload login.
    "aks": KubeconfigLoginPage,
    "eks": KubeconfigLoginPage,
    "gke": KubeconfigLoginPage,
    # Hosted manager: upload credentials.db (https://master.k8strilio.net/).
    "master": CredentialsDbLoginPage,
    "credentials_db": CredentialsDbLoginPage,
}


def get_login_page(page: Page, cfg: FrameworkConfig) -> BaseLoginPage:
    cls = LOGIN_STRATEGIES.get(cfg.cluster.cluster_type)
    if not cls:
        raise ValueError(f"Unsupported cluster type: {cfg.cluster.cluster_type}. "
                         f"Known: {list(LOGIN_STRATEGIES)}")
    return cls(page, cfg)
