"""Run ONLY the Helm-transformation restore, from a backup that already exists.

test_helm_transformation is monolithic (install app -> target -> plan -> backup
-> restore). When the backup is already there, re-running all of it wastes ~20
minutes to reach the step under test. This drives just the restore.

  .venv\\Scripts\\python.exe restore_helm_only.py helm-bp-g98 helm-tf-g98 helm-trans-g98
     <plan>            backup plan to restore from (its latest backup)
     <source-ns>       namespace holding the plan/backup
     <restore-name>    name to give the restore
"""
import sys

import yaml
from playwright.sync_api import sync_playwright

from config.settings import FrameworkConfig
from pages.login_page import get_login_page
from pages.restore_helm_trans_page import RestoreHelmTransPage
from pages.restore_status_page import RestoreStatusPage
from utils.kube_client import KubeClient
from utils.helm_verify import wait_for_helm_restore, helm_restore_verify

CONFIG = "config/aks-sanitytestns-config.yaml"

PLAN = sys.argv[1] if len(sys.argv) > 1 else "helm-bp-g98"
SOURCE_NS = sys.argv[2] if len(sys.argv) > 2 else "helm-tf-g98"
RESTORE_NAME = sys.argv[3] if len(sys.argv) > 3 else "helm-trans-g98"
RESTORE_NS = f"{SOURCE_NS}-restore"


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

    # Point every restore knob at the pre-existing backup.
    c.run_suffix = RESTORE_NAME.split("-")[-1]
    c.backup_namespace = SOURCE_NS
    c.restore_from_plan = PLAN
    c.restore_target_namespace = RESTORE_NS
    c.restore_name = RESTORE_NAME
    c.transform_enabled = True
    c.transform_type = "helm"
    c.transform_name = f"tf-{c.run_suffix}"
    return c


def main():
    cfg = build_cfg(CONFIG)
    print(f"plan={PLAN}  source_ns={SOURCE_NS}")
    print(f"restore={RESTORE_NAME} -> ns={RESTORE_NS}")
    print(f"transform={cfg.transform_name}  values={cfg.transform_helm_values.strip()!r}")

    kube = KubeClient(cfg)
    kube.create_namespace(RESTORE_NS)  # idempotent

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=150)
        ctx = browser.new_context(ignore_https_errors=True,
                                  viewport={"width": 1600, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        print("login...")
        get_login_page(page, cfg).login()

        print("starting helm-transform restore...")
        RestoreHelmTransPage(page, cfg).restore_with_transform()

        print("waiting for the Restore CR to complete...")
        wait_for_helm_restore(kube, RESTORE_NAME, RESTORE_NS, timeout_s=2700)
        RestoreStatusPage(page, cfg).verify_restore_completed()

        assert kube.verify_app_running(RESTORE_NS), \
            f"Restored app pods are not Running in '{RESTORE_NS}'"

        expected_cpu = (cfg.transform_helm_values.split("cpu:")[-1].strip().strip('"')
                        if "cpu:" in cfg.transform_helm_values else None)
        helm_restore_verify(kube, source_ns=SOURCE_NS, restore_ns=RESTORE_NS,
                            expected_cpu=expected_cpu)
        print(f"\nPASS: restore '{RESTORE_NAME}' completed with transform "
              f"'{cfg.transform_name}' into '{RESTORE_NS}'")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
