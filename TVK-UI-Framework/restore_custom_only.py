"""Run ONLY the custom-transformation restore, reusing a backup that exists.

Companion to restore_helm_only.py. test_custom_transformation is monolithic
(namespace + demo app -> target -> namespace backup plan -> backup -> storage
class -> restore with a custom transform). On a retry there is no reason to
rebuild the first four steps: point this at the existing plan and it drives just
the storage-class + restore + verify tail.

  .venv\\Scripts\\python.exe restore_custom_only.py <plan> <source-ns> [restore-name]

e.g.
  .venv\\Scripts\\python.exe restore_custom_only.py custom-bp-abc custom-tf-abc

With no arguments it discovers the newest custom-bp-* plan on the cluster.
"""
import sys

import yaml
from playwright.sync_api import sync_playwright

from config.settings import FrameworkConfig
from pages.login_page import get_login_page
from pages.restore_custom_trans_page import RestoreCustomTransPage
from pages.restore_status_page import RestoreStatusPage
from utils.kube_client import KubeClient
from utils.helm_verify import wait_for_helm_restore
from utils.storage_class import ensure_trans_storageclass, verify_pvc_storageclass

CONFIG = "config/aks-sanitytestns-config.yaml"


def build_cfg(path):
    c = FrameworkConfig()
    data = yaml.safe_load(open(path)) or {}
    for section, val in data.items():
        obj = getattr(c, section, None)
        if obj is not None and isinstance(val, dict):
            for k, v in val.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
        elif hasattr(c, section):
            setattr(c, section, val)
    return c


def discover_plan(kube):
    """Newest custom-bp-* BackupPlan on the cluster, so a retry needs no args."""
    plans = kube.custom.list_cluster_custom_object(
        "triliovault.trilio.io", "v1", "backupplans").get("items", [])
    mine = [p for p in plans if p["metadata"]["name"].startswith("custom-bp-")]
    if not mine:
        raise SystemExit("No custom-bp-* backup plan found — run the full "
                         "custom_transform test at least once first.")
    mine.sort(key=lambda p: p["metadata"]["creationTimestamp"], reverse=True)
    newest = mine[0]["metadata"]
    print(f"discovered plan '{newest['name']}' in '{newest['namespace']}' "
          f"(created {newest['creationTimestamp']})")
    return newest["name"], newest["namespace"]


def main():
    cfg = build_cfg(CONFIG)
    kube = KubeClient(cfg)

    if len(sys.argv) > 2:
        plan, source_ns = sys.argv[1], sys.argv[2]
    else:
        plan, source_ns = discover_plan(kube)

    suffix = source_ns.rsplit("-", 1)[-1]
    restore_name = sys.argv[3] if len(sys.argv) > 3 else f"custom-trans-{suffix}"
    restore_ns = f"{source_ns}-restore"

    cfg.run_suffix = suffix
    cfg.backup_namespace = source_ns
    cfg.restore_from_plan = plan
    cfg.restore_target_namespace = restore_ns
    cfg.restore_name = restore_name
    cfg.transform_enabled = True
    cfg.transform_type = "custom"
    cfg.transform_name = f"custom-tf-{suffix}"

    print(f"plan={plan}  source_ns={source_ns}")
    print(f"restore={restore_name} -> ns={restore_ns}")

    # Reuses 'trans-storageclass' if a previous attempt already made it.
    sc_name = ensure_trans_storageclass(kube)
    print(f"transform target storage class: {sc_name}")
    kube.create_namespace(restore_ns)  # idempotent

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=150)
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        print("login...")
        get_login_page(page, cfg).login()

        print("starting custom-transform restore...")
        RestoreCustomTransPage(page, cfg).restore_with_transform(storage_class=sc_name)

        print("waiting for the Restore CR to complete...")
        wait_for_helm_restore(kube, restore_name, restore_ns, timeout_s=2700)
        RestoreStatusPage(page, cfg).verify_restore_completed()

        assert kube.verify_app_running(restore_ns), \
            f"Restored app pods are not Running in '{restore_ns}'"
        verify_pvc_storageclass(kube, restore_ns, sc_name)

        print(f"\nPASS: restore '{restore_name}' completed with custom transform "
              f"(/spec/storageClassName -> '{sc_name}') into '{restore_ns}'")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
