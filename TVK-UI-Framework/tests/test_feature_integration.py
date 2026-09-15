"""
TVK feature-integration suite — CR driven, ordered.

Covers the paths the UI suite doesn't: Helm / label / namespace backup types,
schedule policies, scheduled triggering, retention, transformation, and shared
policy lifecycle — all through custom resources rather than the console.

Run the whole flow:
    pytest tests/test_feature_integration.py --tvk-config config/ocp-cluster1-config.yaml

Or a single stage (state carries in a session fixture, so pick a prefix):
    pytest -m "feat_apps or feat_policy or feat_backupplan"

Two design notes:

* Tests are ordered and share the `feat` state object. pytest runs them top to
  bottom in a file, and each stage is a separate test so a failure names the
  stage instead of collapsing a 40-minute run into one red line.

* The two known policy-lifecycle defects are written as xfail tests asserting
  the *desired* behaviour. They report xfail today and flip to xpass the moment
  the product is fixed, which is what makes them regression tests rather than
  documentation.
"""
import time

import pytest

from utils.feature_apps import FeatureApps
from utils.helm_app import HelmApp
from utils.kube_client import KubeClient
from utils.tvk_crs import BACKUP, BACKUPPLAN, POLICY, RESTORE, TvkCRs

# a cron that fires often enough to observe inside a test run
FAST_CRON = "*/5 * * * *"
# what the user actually asks for; cron cannot express a true 20h interval
TWENTY_HOUR_CRON = "0 */20 * * *"
RETENTION_LATEST = 5


class FeatureState:
    """Names and captured fingerprints shared across the ordered stages."""

    def __init__(self, cfg):
        s = cfg.run_suffix
        self.tvk_ns = cfg.tvk_namespace
        self.target = (cfg.target.name, cfg.tvk_namespace)
        # namespaces
        self.helm_ns = f"ft-helm-{s}"
        self.mongo_ns = f"ft-mongo-{s}"
        self.suite_ns = f"ft-suite-{s}"
        self.helm_restore_ns = f"ft-helm-restore-{s}"
        self.mongo_restore_ns = f"ft-mongo-restore-{s}"
        self.suite_restore_ns = f"ft-suite-restore-{s}"
        self.transform_ns = f"ft-transform-restore-{s}"
        # policies
        self.sched_20h = f"ft-sched-20h-{s}"
        self.sched_fast = f"ft-sched-fast-{s}"
        self.retention = f"ft-retention-{s}"
        # plans / backups
        self.helm_plan = f"ft-helm-plan-{s}"
        self.mongo_plan = f"ft-mongo-plan-{s}"
        self.suite_plan = f"ft-suite-plan-{s}"
        self.sched_plan = f"ft-sched-plan-{s}"
        self.helm_backup = f"ft-helm-bk-{s}"
        self.mongo_backup = f"ft-mongo-bk-{s}"
        self.suite_backup = f"ft-suite-bk-{s}"
        # fingerprints captured pre-backup
        self.fp = {}

    @property
    def all_namespaces(self):
        return [self.helm_ns, self.mongo_ns, self.suite_ns, self.helm_restore_ns,
                self.mongo_restore_ns, self.suite_restore_ns, self.transform_ns]


@pytest.fixture(scope="session")
def kube(cfg) -> KubeClient:
    return KubeClient(cfg)


@pytest.fixture(scope="session")
def crs(kube) -> TvkCRs:
    return TvkCRs(kube)


@pytest.fixture(scope="session")
def apps(kube) -> FeatureApps:
    return FeatureApps(kube)


@pytest.fixture(scope="session")
def feat(cfg) -> FeatureState:
    return FeatureState(cfg)


# --------------------------------------------------------------------------
# applications
# --------------------------------------------------------------------------

@pytest.mark.feat_apps
def test_install_apps_and_seed_data(cfg, kube, apps, feat):
    """Install the apps and seed known marker data.

    Seeding before backup is what lets every restore be checked for content
    rather than just for 'Completed'.
    """
    for ns in feat.all_namespaces:
        kube.create_namespace(ns)
    # Official mongo/mariadb/redis images want their own UIDs; OpenShift hands
    # out a random one per namespace unless the SA is allowed anyuid.
    for ns in feat.all_namespaces:
        kube.grant_anyuid(ns)

    helm = HelmApp(cfg, kube)
    helm.install(feat.helm_ns)

    apps.deploy_mongodb(feat.mongo_ns, labels={"ft-backup": "mongo-set"})
    apps.deploy_suite(feat.suite_ns)

    apps.wait_ready(feat.mongo_ns, expected=1)
    apps.wait_ready(feat.suite_ns, expected=2)

    apps.seed_mysql(feat.helm_ns, cfg.helm_app.label)
    apps.seed_mongo(feat.mongo_ns)
    apps.seed_mariadb(feat.suite_ns)
    apps.seed_redis(feat.suite_ns)

    feat.fp["helm"] = apps.verify_mysql(feat.helm_ns, cfg.helm_app.label)
    feat.fp["mongo"] = apps.verify_mongo(feat.mongo_ns)
    feat.fp["mariadb"] = apps.verify_mariadb(feat.suite_ns)
    feat.fp["redis"] = apps.verify_redis(feat.suite_ns)
    feat.fp["configmap"] = apps.configmap_data(feat.suite_ns, "suite-config")
    feat.fp["secret"] = apps.secret_value(feat.suite_ns, "suite-secret", "api-token")

    print(f"[feat] baseline fingerprints: {feat.fp}")
    assert all(feat.fp[k] for k in ("helm", "mongo", "mariadb", "redis"))


# --------------------------------------------------------------------------
# policies
# --------------------------------------------------------------------------

@pytest.mark.feat_policy
def test_create_policies(crs, feat):
    """A Schedule and a Retention policy, both intended to be shared."""
    crs.create(POLICY, feat.tvk_ns,
               crs.schedule_policy(feat.sched_20h, feat.tvk_ns, [TWENTY_HOUR_CRON]))
    crs.create(POLICY, feat.tvk_ns,
               crs.schedule_policy(feat.sched_fast, feat.tvk_ns, [FAST_CRON]))
    crs.create(POLICY, feat.tvk_ns,
               crs.retention_policy(feat.retention, feat.tvk_ns, latest=RETENTION_LATEST))

    for name in (feat.sched_20h, feat.sched_fast, feat.retention):
        assert crs.get(POLICY, name, feat.tvk_ns), f"policy {name} not created"


@pytest.mark.feat_policy
def test_twenty_hour_cron_is_uneven():
    """'Every 20 hours' is not expressible in cron, and TVK accepts it silently.

    `0 */20 * * *` means "minute 0 of hours divisible by 20", i.e. 00:00 and
    20:00 — a 20h/4h alternating cadence. Asserting it here means anyone reading
    the suite sees the caveat instead of assuming a 20-hour interval.
    """
    hours = [h for h in range(24) if h % 20 == 0]
    assert hours == [0, 20]
    gaps = sorted({(hours[1] - hours[0]), 24 - (hours[1] - hours[0])})
    assert gaps == [4, 20], "cron 0 */20 should alternate 20h and 4h, not fire every 20h"


# --------------------------------------------------------------------------
# backup plans + schedule registration
# --------------------------------------------------------------------------

@pytest.mark.feat_backupplan
def test_create_backupplans(cfg, crs, feat):
    """One plan per backup type, all sharing the same two policies."""
    crs.create(BACKUPPLAN, feat.helm_ns, crs.backupplan(
        feat.helm_plan, feat.helm_ns, feat.target,
        schedule_policy=(feat.sched_20h, feat.tvk_ns),
        retention_policy=(feat.retention, feat.tvk_ns),
        helm_releases=[cfg.helm_app.release_name]))

    crs.create(BACKUPPLAN, feat.mongo_ns, crs.backupplan(
        feat.mongo_plan, feat.mongo_ns, feat.target,
        schedule_policy=(feat.sched_20h, feat.tvk_ns),
        retention_policy=(feat.retention, feat.tvk_ns),
        match_labels={"ft-backup": "mongo-set"}))

    # no components -> whole-namespace scope
    crs.create(BACKUPPLAN, feat.suite_ns, crs.backupplan(
        feat.suite_plan, feat.suite_ns, feat.target,
        schedule_policy=(feat.sched_20h, feat.tvk_ns),
        retention_policy=(feat.retention, feat.tvk_ns)))

    for plan, ns in ((feat.helm_plan, feat.helm_ns),
                     (feat.mongo_plan, feat.mongo_ns),
                     (feat.suite_plan, feat.suite_ns)):
        crs.wait_status(BACKUPPLAN, plan, ns, timeout_s=300, poll_s=10)


@pytest.mark.feat_schedule
def test_schedule_policy_registers_cronjobs(kube, crs, feat):
    """A Schedule Policy should compile into one CronJob per BackupPlan.

    Checking status.fullBackupCrons plus the CronJob itself proves registration
    without waiting 20 hours for a fire.
    """
    for plan, ns in ((feat.helm_plan, feat.helm_ns),
                     (feat.mongo_plan, feat.mongo_ns),
                     (feat.suite_plan, feat.suite_ns)):
        crons = crs.cron_map(plan, ns)
        assert TWENTY_HOUR_CRON in crons, \
            f"{plan}: expected {TWENTY_HOUR_CRON} in fullBackupCrons, got {crons}"
        ref = crons[TWENTY_HOUR_CRON]
        assert ref.get("kind") == "CronJob"
        cj = kube.batch.read_namespaced_cron_job(ref["name"], ref["namespace"])
        assert cj.spec.schedule == TWENTY_HOUR_CRON
        assert cj.spec.suspend is False
        print(f"[feat] {plan} -> CronJob {ref['name']} ({cj.spec.schedule})")


@pytest.mark.feat_schedule
def test_policy_is_reusable_across_plans(crs, feat):
    """The same Schedule Policy backs three plans, each with its own CronJob."""
    cronjobs = set()
    for plan, ns in ((feat.helm_plan, feat.helm_ns),
                     (feat.mongo_plan, feat.mongo_ns),
                     (feat.suite_plan, feat.suite_ns)):
        cronjobs.add(crs.cron_map(plan, ns)[TWENTY_HOUR_CRON]["name"])
    assert len(cronjobs) == 3, f"expected 3 distinct CronJobs, got {cronjobs}"


# --------------------------------------------------------------------------
# backups
# --------------------------------------------------------------------------

@pytest.mark.feat_backup
def test_backups_complete(crs, feat):
    """Trigger one Full backup per plan and wait for Available."""
    todo = ((feat.helm_backup, feat.helm_plan, feat.helm_ns),
            (feat.mongo_backup, feat.mongo_plan, feat.mongo_ns),
            (feat.suite_backup, feat.suite_plan, feat.suite_ns))
    for name, plan, ns in todo:
        crs.create(BACKUP, ns, crs.backup(name, ns, plan))
    for name, _plan, ns in todo:
        obj = crs.wait_status(BACKUP, name, ns, timeout_s=2400)
        size = int((obj.get("status") or {}).get("size") or 0)
        # A metadata-only backup still reports Available; size is what catches
        # the app never having been installed (a missing Helm repo, say).
        assert size > 1_000_000, f"{name} looks empty ({size} bytes) — PVC data missing?"
        print(f"[feat] {name}: {size / 2**20:.1f} MiB")


# --------------------------------------------------------------------------
# restores + data integrity
# --------------------------------------------------------------------------

@pytest.mark.feat_restore
def test_restore_helm_and_verify_data(cfg, crs, apps, feat):
    name = f"{feat.helm_backup}-rs"
    crs.create(RESTORE, feat.helm_restore_ns, crs.restore(
        name, feat.helm_restore_ns, (feat.helm_backup, feat.helm_ns)))
    crs.wait_status(RESTORE, name, feat.helm_restore_ns, timeout_s=2400)
    apps.wait_ready(feat.helm_restore_ns, expected=1)
    assert apps.verify_mysql(feat.helm_restore_ns, cfg.helm_app.label) == feat.fp["helm"]


@pytest.mark.feat_restore
def test_restore_label_and_verify_data(crs, apps, feat):
    name = f"{feat.mongo_backup}-rs"
    crs.create(RESTORE, feat.mongo_restore_ns, crs.restore(
        name, feat.mongo_restore_ns, (feat.mongo_backup, feat.mongo_ns)))
    crs.wait_status(RESTORE, name, feat.mongo_restore_ns, timeout_s=2400)
    apps.wait_ready(feat.mongo_restore_ns, expected=1)
    assert apps.verify_mongo(feat.mongo_restore_ns) == feat.fp["mongo"]


@pytest.mark.feat_restore
def test_restore_namespace_and_verify_data_and_metadata(crs, apps, feat):
    """Namespace restore must bring back workloads, data and loose metadata."""
    name = f"{feat.suite_backup}-rs"
    crs.create(RESTORE, feat.suite_restore_ns, crs.restore(
        name, feat.suite_restore_ns, (feat.suite_backup, feat.suite_ns)))
    crs.wait_status(RESTORE, name, feat.suite_restore_ns, timeout_s=2400)
    apps.wait_ready(feat.suite_restore_ns, expected=2)

    assert apps.verify_mariadb(feat.suite_restore_ns) == feat.fp["mariadb"]
    assert apps.verify_redis(feat.suite_restore_ns) == feat.fp["redis"]
    assert apps.configmap_data(feat.suite_restore_ns, "suite-config") == feat.fp["configmap"]
    assert apps.secret_value(feat.suite_restore_ns, "suite-secret", "api-token") \
        == feat.fp["secret"]


@pytest.mark.feat_restore
def test_namespace_restore_needs_skip_if_already_exists(crs, feat):
    """Without skipIfAlreadyExists a namespace restore fails on OpenShift.

    Every namespace is created with kube-root-ca.crt, openshift-service-ca.crt
    and the system: rolebindings, which a namespace backup captures, so the
    restore always collides with them. Worth pinning: the quickstart plugin sets
    the flag implicitly, so plugin-driven runs never reveal this.
    """
    name = f"{feat.suite_backup}-noskip"
    crs.create(RESTORE, feat.suite_restore_ns, crs.restore(
        name, feat.suite_restore_ns, (feat.suite_backup, feat.suite_ns),
        skip_if_exists=False))
    with pytest.raises(AssertionError, match="(?i)already present|already exists"):
        crs.wait_status(RESTORE, name, feat.suite_restore_ns, timeout_s=900, poll_s=10)
    crs.force_delete(RESTORE, name, feat.suite_restore_ns)


# --------------------------------------------------------------------------
# transformation
# --------------------------------------------------------------------------

@pytest.mark.feat_transform
def test_transformation_applies_and_preserves_data(crs, apps, feat):
    """Patch the restored StatefulSet and confirm the change landed.

    Asserting the restore merely completed would pass even if the patches were
    dropped, so both patched fields are read back off the restored object.
    """
    name = f"{feat.mongo_backup}-tf"
    transform = crs.custom_transform(
        "mongo-transform", kind="StatefulSet", objects=["mongodb"],
        patches=[
            {"op": "add", "path": "/metadata/labels/ft-transformed", "value": "yes"},
            {"op": "replace", "path": "/spec/template/spec/containers/0/image",
             "value": "docker.io/library/mongo:7.0"},
        ])
    crs.create(RESTORE, feat.transform_ns, crs.restore(
        name, feat.transform_ns, (feat.mongo_backup, feat.mongo_ns),
        transform_custom=[transform]))
    crs.wait_status(RESTORE, name, feat.transform_ns, timeout_s=2400)
    apps.wait_ready(feat.transform_ns, expected=1)

    assert apps.statefulset_labels(feat.transform_ns, "mongodb").get("ft-transformed") == "yes"
    assert apps.statefulset_image(feat.transform_ns, "mongodb") == "docker.io/library/mongo:7.0"
    # transformation must not disturb the data it carries
    assert apps.verify_mongo(feat.transform_ns) == feat.fp["mongo"]


# --------------------------------------------------------------------------
# scheduled triggering + retention
# --------------------------------------------------------------------------

@pytest.mark.feat_scheduled
def test_scheduled_backup_actually_fires(kube, crs, feat):
    """Prove the trigger path on a cadence short enough to observe.

    The 20h policy exercises the same controller code, so a fast cron firing is
    evidence the mechanism works — the difference is only the cron expression.
    """
    crs.create(BACKUPPLAN, feat.suite_ns, crs.backupplan(
        feat.sched_plan, feat.suite_ns, feat.target,
        schedule_policy=(feat.sched_fast, feat.tvk_ns),
        retention_policy=(feat.retention, feat.tvk_ns),
        match_labels={"ft-sched": "redis"}))
    crs.wait_status(BACKUPPLAN, feat.sched_plan, feat.suite_ns, timeout_s=300, poll_s=10)

    ref = crs.cron_map(feat.sched_plan, feat.suite_ns).get(FAST_CRON)
    assert ref, "fast schedule did not register a CronJob"

    deadline = time.time() + 900
    created = []
    while time.time() < deadline and not created:
        created = crs.scheduled_backups(feat.sched_plan, feat.suite_ns)
        if not created:
            time.sleep(20)
    assert created, f"no scheduled Backup appeared for {feat.sched_plan} within 15m"

    first = created[0]["metadata"]["name"]
    print(f"[feat] scheduled backup created: {first}")
    crs.wait_status(BACKUP, first, feat.suite_ns, timeout_s=1800)

    cj = kube.batch.read_namespaced_cron_job(ref["name"], ref["namespace"])
    assert cj.status.last_schedule_time, "CronJob never recorded a lastScheduleTime"


@pytest.mark.feat_retention
def test_retention_caps_scheduled_backups(crs, feat):
    """Retention latest:N must prune older scheduled backups.

    Waits for more than N to have been produced, then asserts the count settles
    at N rather than growing without bound.
    """
    deadline = time.time() + 1800
    while time.time() < deadline:
        count = len(crs.scheduled_backups(feat.sched_plan, feat.suite_ns))
        print(f"[feat] scheduled backups retained: {count}")
        if count > RETENTION_LATEST:
            time.sleep(60)  # give the retention controller a chance to prune
            continue
        if count == RETENTION_LATEST:
            break
        time.sleep(60)
    final = len(crs.scheduled_backups(feat.sched_plan, feat.suite_ns))
    assert final <= RETENTION_LATEST, \
        f"retention latest:{RETENTION_LATEST} not enforced — {final} backups retained"


@pytest.mark.feat_retention
def test_pause_schedule_stops_further_backups(kube, crs, feat):
    """pauseSchedule should stop the schedule.

    Note it is implemented by removing the CronJob rather than setting the
    CronJob's own suspend field, so this accepts either outcome.
    """
    crs.patch(BACKUPPLAN, feat.sched_plan, feat.suite_ns,
              {"spec": {"backupPlanFlags": {"pauseSchedule": True}}})
    time.sleep(30)
    ref = crs.cron_map(feat.sched_plan, feat.suite_ns).get(FAST_CRON)
    if not ref:
        return  # CronJob reference dropped from status — schedule is gone
    try:
        cj = kube.batch.read_namespaced_cron_job(ref["name"], ref["namespace"])
    except Exception:
        return  # CronJob deleted outright, which is what TVK actually does
    assert cj.spec.suspend is True, "pauseSchedule left the CronJob active"


# --------------------------------------------------------------------------
# known defects — xfail so they flip to xpass once fixed
# --------------------------------------------------------------------------

@pytest.mark.feat_policy_lifecycle
@pytest.mark.xfail(reason="in-use Policy can be deleted; plans keep dangling refs "
                          "and their CronJobs stay active", strict=False)
def test_deleting_in_use_policy_is_rejected(crs, feat):
    """Deleting a Policy that BackupPlans reference should be refused.

    It currently succeeds, leaving the plans reporting Available against a
    policy that no longer exists while their CronJobs keep firing.
    """
    crs.delete(POLICY, feat.sched_20h, feat.tvk_ns)
    time.sleep(10)
    assert crs.get(POLICY, feat.sched_20h, feat.tvk_ns) is not None, \
        "in-use schedule policy was deleted without rejection"


@pytest.mark.feat_policy_lifecycle
@pytest.mark.xfail(reason="Policy edits do not propagate to existing BackupPlans; "
                          "CronJobs keep the original schedule", strict=False)
def test_editing_shared_policy_propagates(crs, feat):
    """Editing a shared Policy should update every plan using it.

    Policies are designed for reuse, so a central schedule change that silently
    does nothing to existing consumers is the dangerous case.
    """
    new_cron = "45 */20 * * *"
    crs.patch(POLICY, feat.sched_20h, feat.tvk_ns,
              {"spec": {"scheduleConfig": {"schedule": [new_cron]}}})
    deadline = time.time() + 300
    while time.time() < deadline:
        crons = crs.cron_map(feat.mongo_plan, feat.mongo_ns)
        if new_cron in crons:
            return
        time.sleep(20)
    pytest.fail(f"policy edit never reached the plan; still {list(crons)}")


# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------

@pytest.mark.feat_cleanup
def test_cleanup(kube, crs, feat):
    """Opt-in teardown: select -m feat_cleanup explicitly.

    Left out of the default run so a failed stage can be inspected on-cluster.
    """
    for plan, ns in ((feat.helm_plan, feat.helm_ns), (feat.mongo_plan, feat.mongo_ns),
                     (feat.suite_plan, feat.suite_ns), (feat.sched_plan, feat.suite_ns)):
        for b in crs.list_all(BACKUP, ns):
            crs.force_delete(BACKUP, b["metadata"]["name"], ns)
        crs.force_delete(BACKUPPLAN, plan, ns)
    for pol in (feat.sched_20h, feat.sched_fast, feat.retention):
        crs.force_delete(POLICY, pol, feat.tvk_ns)
    for ns in feat.all_namespaces:
        kube.delete_namespace(ns)
