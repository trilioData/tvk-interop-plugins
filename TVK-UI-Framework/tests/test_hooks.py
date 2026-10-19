"""
UI hooks suite.

Ordered, and selected explicitly:
  pytest tests/test_hooks.py -m hooks --headed --tvk-config <cfg>

  install sample PVC app (fail if it is not Running)
  -> login
  -> target in pvc-ns
  -> create hook from the Hooks page
  -> backup plan with that hook
  -> backup
  -> restore with the hook

The hook command, timeout, and pod selector match utils/sample-pvc-app.yaml
and the Cassandra hookConfig shape (Sequential, matchLabels, pod regex,
container regex).
"""
import time

import pytest

from pages.backupplans_page import BackupPlansPage
from pages.hooks_page import HooksPage
from pages.nfs_target_page import NFSTargetPage
from pages.restore_page import RestorePage
from pages.targets_page import TargetsPage
from utils.kube_client import KubeClient
from utils.pvc_hook_app import MARKER, PvcHookApp, hook_payload
from utils.tvk_crs import HOOK, BACKUPPLAN, TvkCRs


def _plan_hook(plan: dict, hook: dict) -> dict:
    hooks = ((plan.get("spec") or {}).get("hookConfig") or {}).get("hooks") or []
    assert hooks, f"backup plan has no hookConfig hooks: {plan.get('spec')}"
    ref = hooks[0]
    assert (ref.get("hook") or {}).get("name") == hook["name"], ref
    labels = (((ref.get("podSelector") or {}).get("labels") or [{}])[0]
              .get("matchLabels") or {})
    for key, value in hook["labels"].items():
        assert labels.get(key) == value, labels
    return ref


@pytest.fixture(scope="module")
def hooks_cfg(cfg):
    """Point the existing target / backup plan / restore pages at pvc-ns."""
    h = cfg.hooks
    cfg.app_installed = False
    cfg.backup_namespace = h.namespace
    cfg.target.namespace = h.namespace
    cfg.target.enable_browsing = True
    suffix = cfg.run_suffix
    cfg.backupplan_name = f"sample-pvc-bp-{suffix}"
    cfg.backup_name = f"sample-pvc-backup-{suffix}"
    cfg.restore_name = f"sample-pvc-restore-{suffix}"
    cfg.restore_target_namespace = f"{h.namespace}-restore-{suffix}"
    cfg.backup_from_plan = cfg.backupplan_name
    cfg.restore_from_plan = cfg.backupplan_name
    return cfg


@pytest.fixture(scope="module")
def kube(hooks_cfg):
    return KubeClient(hooks_cfg)


@pytest.fixture(scope="module")
def crs(kube):
    return TvkCRs(kube)


@pytest.fixture(scope="module")
def sample_app(kube, hooks_cfg):
    """Install the PVC app. Every later stage depends on this, so a pod that
    never becomes Running fails the suite before the browser does any work."""
    app = PvcHookApp(kube, hooks_cfg)
    app.install()
    return app


@pytest.mark.run(order=1)
@pytest.mark.hooks
def test_install_sample_pvc_app(sample_app, hooks_cfg):
    assert sample_app.pod_name, "sample-pvc-deploy pod name was empty"
    marker = sample_app.read_marker()
    assert marker == MARKER
    print(f"[hooks] app Running in '{hooks_cfg.hooks.namespace}' "
          f"pod={sample_app.pod_name}")


@pytest.mark.run(order=2)
@pytest.mark.hooks
def test_login(logged_in_page, sample_app):
    assert "#/login" not in logged_in_page.url


@pytest.mark.run(order=3)
@pytest.mark.hooks
def test_create_target(logged_in_page, sample_app, hooks_cfg):
    if hooks_cfg.target.type.lower() == "nfs":
        page = NFSTargetPage(logged_in_page, hooks_cfg)
    else:
        page = TargetsPage(logged_in_page, hooks_cfg)
    page.create_target()
    page.verify_target_available()


@pytest.mark.run(order=4)
@pytest.mark.hooks
def test_create_hook_from_hooks_page(logged_in_page, sample_app, crs, hooks_cfg):
    hook = hook_payload(hooks_cfg)
    crs.force_delete(HOOK, hook["name"], hook["namespace"])
    deadline = time.time() + 60
    while time.time() < deadline:
        if crs.get(HOOK, hook["name"], hook["namespace"]) is None:
            break
        time.sleep(2)
    else:
        raise AssertionError(
            f"hook '{hook['name']}' is still in '{hook['namespace']}' after delete")

    HooksPage(logged_in_page, hooks_cfg).create_hook(hook)

    created = None
    deadline = time.time() + 60
    while time.time() < deadline:
        created = crs.get(HOOK, hook["name"], hook["namespace"])
        if created:
            break
        time.sleep(2)
    assert created, f"hook '{hook['name']}' was not created"
    pre, post = crs.hook_commands(created)
    assert pre == hook["commands"], pre
    assert post == hook["commands"], post
    for side in ("pre", "post"):
        spec = created["spec"][side]
        assert spec["timeoutSeconds"] == hook["timeout_seconds"], spec
        assert spec["maxRetryCount"] == hook["max_retry_count"], spec
    print(f"[hooks] hook '{hook['name']}' created in '{hook['namespace']}'")


@pytest.mark.run(order=5)
@pytest.mark.hooks
def test_create_backupplan_with_hooks(logged_in_page, sample_app, crs, hooks_cfg):
    hook = hook_payload(hooks_cfg)
    plans = BackupPlansPage(logged_in_page, hooks_cfg)
    plans.create_backupplan(hook=hook)
    plans.verify_backupplan_available()

    plan = crs.get(BACKUPPLAN, hooks_cfg.backupplan_name, hook["namespace"])
    assert plan, f"backup plan '{hooks_cfg.backupplan_name}' not found"
    _plan_hook(plan, hook)
    print(f"[hooks] backup plan '{hooks_cfg.backupplan_name}' uses "
          f"'{hook['name']}'")


@pytest.mark.run(order=6)
@pytest.mark.hooks
def test_backup_runs_hooks(logged_in_page, kube, sample_app, crs, hooks_cfg):
    plans = BackupPlansPage(logged_in_page, hooks_cfg)
    plans.trigger_backup()
    backup = kube.wait_for_backup(
        hooks_cfg.hooks.namespace, hooks_cfg.backup_name, timeout_s=2700)
    plans._close_status_popup()
    crs.assert_hooks_completed(backup, hooks_cfg.hooks.name)
    print(f"[hooks] backup '{hooks_cfg.backup_name}' completed with hooks")


@pytest.mark.run(order=7)
@pytest.mark.hooks
def test_restore_with_hooks(logged_in_page, kube, sample_app, crs, hooks_cfg):
    hook = hook_payload(hooks_cfg)
    restore_ns = hooks_cfg.restore_target_namespace
    kube.create_namespace(restore_ns)
    kube.grant_hook_app_sccs(restore_ns)
    # The restore wizard lists hooks in the namespace it is restoring into.
    # Copy the hook created from the Hooks page so that dropdown can select it.
    if crs.get(HOOK, hook["name"], restore_ns) is None:
        body = crs.hook(
            hook["name"], restore_ns, hook["commands"],
            hook["timeout_seconds"], hook["max_retry_count"])
        crs.create(HOOK, restore_ns, body)

    restore = RestorePage(logged_in_page, hooks_cfg)
    restore.start_restore_from_backup(hook=hook)
    restored = kube.wait_for_restore(
        hooks_cfg.restore_name, namespace=restore_ns, timeout_s=2700)
    restore.close_status_popup()
    crs.assert_hooks_completed(restored, hook["name"])

    kube.wait_labeled_pod_ready(restore_ns, "app=redis", timeout_s=600)
    assert sample_app.read_marker(restore_ns) == MARKER
    print(f"[hooks] restore '{hooks_cfg.restore_name}' completed in "
          f"'{restore_ns}' with marker {MARKER}")
