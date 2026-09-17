"""
Pytest fixtures + CLI arguments for the Trilio test framework.

Run example:
  pytest --trilio-url https://trilio-system.apps.../#/login ^
         --console-url https://console-openshift-console.apps... ^
         --username kubeadmin --password <pwd> --cluster-type ocp --headed
"""
import os
import random
import string

import pytest
import yaml

from config.settings import FrameworkConfig
from pages.login_page import get_login_page
from pages.dashboard_page import DashboardPage


def pytest_addoption(parser):
    g = parser.getgroup("trilio")
    g.addoption("--trilio-url", default=None, help="Trilio UI login URL")
    g.addoption("--console-url", default=None, help="Cluster console URL (OCP web console)")
    g.addoption("--username", default=None, help="Cluster username")
    g.addoption("--password", default=None, help="Cluster password")
    g.addoption("--cluster-type", default=None,
                choices=["ocp", "vanilla", "eks", "gke", "aks", "master", "credentials_db"],
                help="Kubernetes cluster flavour (drives the login strategy)")
    g.addoption("--kubeconfig", default=None, help="Path to kubeconfig for CLI operations")
    g.addoption("--credentials-db", default=None,
                help="Path to credentials.db (cluster_type=master)")
    g.addoption("--tvk-config", default=None, help="YAML file overriding any config value")
    # target options
    g.addoption("--target-type", default=None, choices=["s3", "nfs"])
    g.addoption("--s3-bucket", default=None)
    g.addoption("--s3-url", default=None)
    g.addoption("--s3-region", default=None)
    g.addoption("--s3-access-key", default=None)
    g.addoption("--s3-secret-key", default=None)
    g.addoption("--nfs-path", default=None)
    # app options
    g.addoption("--app-namespace", default=None)


@pytest.fixture(scope="session")
def cfg(request) -> FrameworkConfig:
    """Build the merged configuration: defaults <- yaml file <- CLI args."""
    c = FrameworkConfig()

    yaml_path = request.config.getoption("--tvk-config")
    if yaml_path and os.path.exists(yaml_path):
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        for section_name, section in data.items():
            obj = getattr(c, section_name, None)
            if obj is not None and isinstance(section, dict):
                for k, v in section.items():
                    if hasattr(obj, k):
                        setattr(obj, k, v)
            elif hasattr(c, section_name):
                setattr(c, section_name, section)

    opt = request.config.getoption
    if opt("--trilio-url"):    c.cluster.trilio_url = opt("--trilio-url")
    if opt("--console-url"):   c.cluster.console_url = opt("--console-url")
    if opt("--username"):      c.cluster.username = opt("--username")
    if opt("--password"):      c.cluster.password = opt("--password")
    if opt("--cluster-type"):  c.cluster.cluster_type = opt("--cluster-type")
    if opt("--kubeconfig"):    c.cluster.kubeconfig = opt("--kubeconfig")
    if opt("--credentials-db"): c.cluster.credentials_db = opt("--credentials-db")

    # Resolve a relative credentials.db against the framework root (this file's parent)
    if c.cluster.credentials_db and not os.path.isabs(c.cluster.credentials_db):
        root = os.path.dirname(os.path.abspath(__file__))
        c.cluster.credentials_db = os.path.normpath(
            os.path.join(root, c.cluster.credentials_db))
    if opt("--target-type"):   c.target.type = opt("--target-type")
    if opt("--s3-bucket"):     c.target.bucket = opt("--s3-bucket")
    if opt("--s3-url"):        c.target.s3_url = opt("--s3-url")
    if opt("--s3-region"):     c.target.region = opt("--s3-region")
    if opt("--s3-access-key"): c.target.access_key = opt("--s3-access-key")
    if opt("--s3-secret-key"): c.target.secret_key = opt("--s3-secret-key")
    if opt("--nfs-path"):      c.target.nfs_path = opt("--nfs-path")
    if opt("--app-namespace"): c.app.namespace = opt("--app-namespace")

    # Unique run suffix: every created resource gets '-<3 random chars>' so
    # names stay readable but never collide across runs
    # (e.g. auto-target-x7x, auto-backupplan-x7x)
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=3))
    c.run_suffix = suffix
    c.target.name = f"{c.target.name}-{suffix}"
    c.backupplan_name = f"{c.backupplan_name}-{suffix}"
    c.backup_name = f"{c.backup_name}-{suffix}"
    c.restore_name = f"{c.restore_name}-{suffix}"
    c.policy_name = f"{c.policy_name}-{suffix}"
    c.app.namespace = f"{c.app.namespace}-{suffix}"
    # restore_namespace is resolved dynamically via cfg.restore_ns() (depends
    # on whether the app was installed this run).
    print(f"[cfg] Run suffix: -{suffix} (target={c.target.name}, "
          f"app_ns={c.app.namespace})")

    os.makedirs(c.screenshot_dir, exist_ok=True)
    return c


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # Staging clusters use self-signed certs
    return {**browser_context_args, "ignore_https_errors": True, "viewport": {"width": 1600, "height": 900}}


@pytest.fixture(scope="session")
def logged_in_page(browser, browser_context_args, cfg):
    """A single authenticated Trilio UI session shared across the test session."""
    context = browser.new_context(**browser_context_args)
    page = context.new_page()
    page.set_default_timeout(cfg.default_timeout_ms)

    login = get_login_page(page, cfg)
    login.login()

    yield page
    context.close()


@pytest.fixture(scope="session")
def dashboard(logged_in_page, cfg) -> DashboardPage:
    return DashboardPage(logged_in_page, cfg)


# Tests that are self-contained flows, not part of the main ordered E2E
# chain. They must be selected explicitly (e.g. `-m helm_transform`) and
# never run just because someone did a bare `pytest` / `-m "not cleanup"`.
STANDALONE_ONLY_MARKERS = {
    "target_browsing", "helm_transform", "custom_transform",
    "cassandra", "cassandra_app", "cassandra_backupplan",
    "cassandra_application_backupplan", "cassandra_backup",
}


def pytest_collection_modifyitems(config, items):
    requested = config.getoption("-m") or ""
    explicitly_requested = {m for m in STANDALONE_ONLY_MARKERS if m in requested}
    skip_standalone = pytest.mark.skip(
        reason="standalone-only test — select explicitly, e.g. -m helm_transform")
    for item in items:
        item_markers = {m.name for m in item.iter_markers()}
        if item_markers & STANDALONE_ONLY_MARKERS and not (item_markers & explicitly_requested):
            item.add_marker(skip_standalone)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Screenshot on failure."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("logged_in_page")
        if page:
            try:
                page.screenshot(path=f"screenshots/FAILED-{item.name}.png", full_page=True)
            except Exception:
                pass
