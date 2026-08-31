"""
End-to-end Trilio (T4K) test suite.

Order matters â€” each stage builds on the previous one:
  login -> install app -> target -> policy -> backupplan -> backup
  (snapshot) -> restore with transformation -> verify.

Run:
  pytest tests/test_e2e_trilio.py --headed ^
      --trilio-url https://trilio-system.apps.<your-cluster>/#/login ^
      --console-url https://console-openshift-console.apps.<your-cluster> ^
      --username kubeadmin --password <password> --cluster-type ocp ^
      --target-type s3 --s3-bucket my-bucket --s3-access-key ... --s3-secret-key ...
"""
import pytest

from pages.targets_page import TargetsPage
from pages.nfs_target_page import NFSTargetPage
from pages.backupplans_page import BackupPlansPage
from pages.helm_backupplan_page import HelmBackupPlanPage
from pages.backup_summary_page import BackupSummaryPage
from pages.restore_helm_trans_page import RestoreHelmTransPage
from pages.restore_custom_trans_page import RestoreCustomTransPage
from pages.backups_page import BackupsPage
from pages.backup_status_page import BackupStatusPage
from pages.policies_page import PoliciesPage
from pages.restore_page import RestorePage
from pages.restore_status_page import RestoreStatusPage
from utils.kube_client import KubeClient
from utils.helm_app import HelmApp
from utils.helm_verify import (wait_for_helm_backup, wait_for_helm_restore,
                                helm_restore_verify)
from utils.storage_class import ensure_trans_storageclass, verify_pvc_storageclass


@pytest.fixture(scope="session")
def kube(cfg):
    # Connects via kubeconfig if provided, else via OCP OAuth token
    # obtained from the username/password in the config.
    return KubeClient(cfg)


@pytest.mark.run(order=2)
@pytest.mark.helm_app
def test_install_helm_app(kube, cfg):
    """Install the mysql-qa helm chart (used for Helm-transformation tests).
    Run standalone with:  pytest -m helm_app
    Installs into backup_namespace if set, else the app namespace."""
    ns = cfg.backup_namespace or cfg.app.namespace
    HelmApp(cfg, kube).install(ns)


@pytest.mark.run(order=1)
@pytest.mark.login
def test_login(logged_in_page, cfg):
    """Session fixture performs the login; assert we landed in the app."""
    assert "#/login" not in logged_in_page.url


@pytest.mark.run(order=2)
@pytest.mark.app
def test_install_demo_app(kube, cfg):
    kube.install_demo_app()
    assert kube.verify_app_running(), "Demo app pods are not all Running"
    # Mark this as an integrated run: subsequent resources go in the app
    # namespace and config namespace overrides are ignored.
    cfg.app_installed = True
    print(f"[cfg] integrated run — all resources will use app namespace "
          f"'{cfg.app.namespace}'")


@pytest.mark.run(order=3)
@pytest.mark.target
def test_create_target(logged_in_page, cfg):
    # Dispatch by target type: NFS uses its own page, else ObjectStore/S3
    if cfg.target.type.lower() == "nfs":
        targets = NFSTargetPage(logged_in_page, cfg)
    else:
        targets = TargetsPage(logged_in_page, cfg)
    targets.create_target()
    targets.verify_target_available()


@pytest.mark.run(order=4)
@pytest.mark.policy
def test_create_policy(logged_in_page, cfg):
    policies = PoliciesPage(logged_in_page, cfg)
    policies.create_retention_policy(latest=5, daily=7)
    policies.verify_policy_exists()


@pytest.mark.run(order=5)
@pytest.mark.backupplan
def test_create_backupplan(logged_in_page, cfg):
    bp = BackupPlansPage(logged_in_page, cfg)
    bp.create_backupplan(with_policy=True)
    bp.verify_backupplan_available()


@pytest.mark.run(order=6)
@pytest.mark.backup
def test_trigger_backup(logged_in_page, kube, cfg):
    # Trigger the backup via the UI
    BackupPlansPage(logged_in_page, cfg).trigger_backup()
    # Wait for completion via the Backup CR (reliable, 45-min timeout)
    ns = cfg.backup_namespace or cfg.app.namespace
    kube.wait_for_backup(ns, cfg.backup_name, timeout_s=2700)
    # Close the STATUS LOG popup once the backup is done, so it doesn't block
    # the next step
    BackupPlansPage(logged_in_page, cfg)._close_status_popup()


@pytest.mark.run(order=7)
@pytest.mark.backup_status
def test_backup_status(logged_in_page, cfg):
    """Standalone-friendly UI check that the backup is in 'Available' state.
    Run on its own with:  pytest -m backup_status"""
    BackupStatusPage(logged_in_page, cfg).verify_backup_available()


@pytest.mark.run(order=8)
@pytest.mark.snapshot
def test_snapshot_stage_reported(logged_in_page, cfg):
    BackupsPage(logged_in_page, cfg).verify_snapshot_stage()


@pytest.mark.run(order=9)
@pytest.mark.restore
def test_restore(logged_in_page, kube, cfg):
    # Ensure the restore target namespace exists (create it if missing)
    target_ns = cfg.restore_ns()
    kube.create_namespace(target_ns)  # idempotent — ignores 'already exists'
    restore = RestorePage(logged_in_page, cfg)
    restore.start_restore_from_backup()
    # Wait for completion via the Restore CR (reliable, 45-min timeout)
    kube.wait_for_restore(cfg.restore_name, namespace=target_ns, timeout_s=2700)
    # Close the STATUS LOG popup once the restore is done (mirrors backup)
    restore.close_status_popup()

    # Verify the transformation took effect (if one was applied). The restore
    # reaching 'Completed' with a transform means TVK applied it; optionally
    # confirm a specific changed field on a restored resource.
    if cfg.transform_enabled:
        print(f"[restore] transform '{cfg.transform_name}' applied — restore Completed")
        if cfg.transform_verify_kind.lower() == "deployment" and cfg.transform_verify_name:
            actual = kube.get_deployment_replicas(cfg.transform_verify_name, target_ns)
            assert str(actual) == str(cfg.transform_verify_expected), (
                f"Transform verify failed: {cfg.transform_verify_name} "
                f"expected replicas={cfg.transform_verify_expected}, got {actual}")
            print(f"[restore] transform verified: {cfg.transform_verify_name} "
                  f"replicas={actual}")


@pytest.mark.run(order=10)
@pytest.mark.restore_status
def test_restore_status(logged_in_page, cfg):
    """Standalone-friendly UI check that the restore completed.
    Run on its own with:  pytest -m restore_status"""
    RestoreStatusPage(logged_in_page, cfg).verify_restore_completed()


@pytest.mark.target_browsing
def test_target_browsing(logged_in_page, kube, cfg):
    """Test ONLY target creation with 'Enable Browsing' ON (no app install).
    Run with:  pytest -m target_browsing"""
    ns = cfg.target.namespace or cfg.backup_namespace or cfg.app.namespace
    kube.create_namespace(ns)
    cfg.target.namespace = ns
    cfg.target.enable_browsing = True   # force on for this test
    tpage = (NFSTargetPage(logged_in_page, cfg)
             if cfg.target.type.lower() == "nfs"
             else TargetsPage(logged_in_page, cfg))
    tpage.create_target()
    tpage.verify_target_available()


@pytest.mark.helm_transform
def test_helm_transformation(logged_in_page, kube, cfg):
    """Self-contained Helm-transformation flow:
      create namespace + install helm app -> create target -> create Helm
      backup plan -> backup (wait + close popup + view summary) -> restore
      WITH helm transformation -> wait.
    Names/namespaces/target are derived from the run; restore_from_plan and
    restore_target_namespace are set automatically. Run with:
      pytest -m helm_transform"""
    suffix = cfg.run_suffix
    ns = f"helm-tf-{suffix}"
    plan = f"helm-bp-{suffix}"
    backup_name = f"helm-backup-{suffix}"
    restore_ns = f"{ns}-restore"
    restore_name = f"helm-trans-{suffix}"
    target_name = cfg.target.name      # auto-target-<suffix>

    # 1. New namespace + helm app
    HelmApp(cfg, kube).install(ns)

    # 2. Create the target IN this namespace (existing target code).
    #    Force 'Enable Browsing' ON for helm transform (overrides config).
    cfg.target.namespace = ns
    cfg.target.enable_browsing = True
    tpage = (NFSTargetPage(logged_in_page, cfg)
             if cfg.target.type.lower() == "nfs"
             else TargetsPage(logged_in_page, cfg))
    tpage.create_target()
    tpage.verify_target_available()

    # 3. Helm backup plan (Application type + Helm Release component)
    HelmBackupPlanPage(logged_in_page, cfg).create(
        namespace=ns, plan_name=plan, target=target_name,
        release=cfg.helm_app.release_name)

    # 4. Trigger backup, wait (Backup CR), close popup, view backup summary
    cfg.backup_namespace = ns
    cfg.backup_from_plan = plan
    cfg.backup_name = backup_name
    bp = BackupPlansPage(logged_in_page, cfg)
    bp.trigger_backup()
    wait_for_helm_backup(kube, backup_name, ns, timeout_s=2700)
    bp._close_status_popup()
    BackupSummaryPage(logged_in_page, cfg).verify(plan)

    # 5. Restore WITH helm transformation into a derived namespace
    #    (dedicated helm-transform restore page; restore_page.py untouched)
    kube.create_namespace(restore_ns)
    cfg.restore_from_plan = plan
    cfg.restore_target_namespace = restore_ns
    cfg.restore_name = restore_name
    cfg.transform_name = cfg.transform_name or f"helm-tf-{suffix}"
    RestoreHelmTransPage(logged_in_page, cfg).restore_with_transform()
    # Strict wait for THIS restore by exact name (no 'latest' fallback), then
    # confirm in the UI monitoring page.
    wait_for_helm_restore(kube, restore_name, restore_ns, timeout_s=2700)
    RestoreStatusPage(logged_in_page, cfg).verify_restore_completed()
    assert kube.verify_app_running(restore_ns), \
        f"Restored app pods are not Running in '{restore_ns}'"
    # Verify the transformation: the source app is restored (same image,
    # Running) into the restore namespace, and the cpu request was changed.
    expected_cpu = (cfg.transform_helm_values.split("cpu:")[-1].strip().strip('"')
                    if "cpu:" in cfg.transform_helm_values else None)
    helm_restore_verify(kube, source_ns=ns, restore_ns=restore_ns,
                        expected_cpu=expected_cpu)
    print(f"[helm_transform] restore '{restore_name}' completed with transform "
          f"'{cfg.transform_name}' into '{restore_ns}'")


@pytest.mark.custom_transform
def test_custom_transformation(logged_in_page, kube, cfg):
    """Self-contained Custom-transformation flow (namespace-based backup):
      create namespace + install demo app (has a PVC) -> create target
      (browsing ON) -> create NAMESPACE backup plan -> backup (wait + close
      popup + view summary) -> create 'trans-storageclass' -> restore WITH a
      custom transform that rewrites each PVC's /spec/storageClassName to the
      new storage class -> wait -> verify the restored PVC uses it.
    Reuses the existing namespace-backup code unchanged; the custom-transform
    restore lives in its own page. Run with:  pytest -m custom_transform"""
    suffix = cfg.run_suffix
    ns = f"custom-tf-{suffix}"
    plan = f"custom-bp-{suffix}"
    backup_name = f"custom-backup-{suffix}"
    restore_ns = f"{ns}-restore"
    restore_name = f"custom-trans-{suffix}"
    target_name = cfg.target.name      # auto-target-<suffix>

    # 1. New namespace + demo app (the nginx+PVC demo gives us a PVC to retarget)
    cfg.app.namespace = ns
    cfg.app_installed = False           # standalone: honor backup_namespace
    kube.create_namespace(ns)
    kube.install_demo_app()
    assert kube.verify_app_running(ns), "Demo app pods are not all Running"

    # 2. Create the target IN this namespace with 'Enable Browsing' ON
    cfg.target.namespace = ns
    cfg.target.enable_browsing = True
    tpage = (NFSTargetPage(logged_in_page, cfg)
             if cfg.target.type.lower() == "nfs"
             else TargetsPage(logged_in_page, cfg))
    tpage.create_target()
    tpage.verify_target_available()

    # 3. Namespace-based backup plan (existing code, unchanged)
    cfg.backup_namespace = ns
    cfg.backupplan_name = plan
    cfg.backup_component = "namespace"
    bp = BackupPlansPage(logged_in_page, cfg)
    bp.create_backupplan(with_policy=False)
    bp.verify_backupplan_available()

    # 4. Trigger backup, wait (Backup CR, strict name), close popup, view summary
    cfg.backup_from_plan = plan
    cfg.backup_name = backup_name
    bp.trigger_backup()
    wait_for_helm_backup(kube, backup_name, ns, timeout_s=2700)
    bp._close_status_popup()
    BackupSummaryPage(logged_in_page, cfg).verify(plan)

    # 5. Create the transformation storage class (clone/select per shell logic)
    sc_name = ensure_trans_storageclass(kube)

    # 6. Restore WITH custom transform into a derived namespace
    kube.create_namespace(restore_ns)
    cfg.restore_from_plan = plan
    cfg.restore_target_namespace = restore_ns
    cfg.restore_name = restore_name
    cfg.transform_name = f"custom-tf-{suffix}"
    RestoreCustomTransPage(logged_in_page, cfg).restore_with_transform(
        storage_class=sc_name)

    # 7. Strict wait for THIS restore, confirm in UI, verify the PVC storage class
    wait_for_helm_restore(kube, restore_name, restore_ns, timeout_s=2700)
    RestoreStatusPage(logged_in_page, cfg).verify_restore_completed()
    assert kube.verify_app_running(restore_ns), \
        f"Restored app pods are not Running in '{restore_ns}'"
    verify_pvc_storageclass(kube, restore_ns, sc_name)
    print(f"[custom_transform] restore '{restore_name}' completed with custom "
          f"transform (/spec/storageClassName -> '{sc_name}') into '{restore_ns}'")


@pytest.mark.run(order=12)
@pytest.mark.cleanup
def test_cleanup(kube, cfg):
    """Delete all resources created in this run — gated by cleanup_enabled.
    Set cleanup_enabled: true in config to run it; false skips it."""
    if not cfg.cleanup_enabled:
        pytest.skip("cleanup_enabled is false — leaving resources in place")
    kube.cleanup_resources(cfg)

