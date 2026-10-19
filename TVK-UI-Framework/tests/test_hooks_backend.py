"""
Backend hooks suite — the same PVC lifecycle through custom resources.

Cluster-free checks (Hook body, Cassandra-style hookConfig, hook status)
always run. The cluster stages are selected explicitly:

  pytest tests/test_hooks_backend.py -m hooks_backend --tvk-config <cfg>
"""
import pytest

from utils.kube_client import KubeClient
from utils.pvc_hook_app import MARKER, load_manifests, PvcHookApp, hook_payload
from utils.tvk_crs import BACKUP, BACKUPPLAN, HOOK, RESTORE, TvkCRs


# --------------------------------------------------------------------------
# no cluster
# --------------------------------------------------------------------------

def test_sample_pvc_manifest_matches_script():
    pvc, deploy = load_manifests()
    assert pvc["kind"] == "PersistentVolumeClaim"
    assert pvc["metadata"]["name"] == "sample-pvc"
    assert pvc["metadata"]["labels"]["run"] == "backup1an"
    assert pvc["spec"]["resources"]["requests"]["storage"] == "10Gi"
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]

    assert deploy["metadata"]["name"] == "sample-pvc-deploy"
    assert deploy["spec"]["selector"]["matchLabels"] == {
        "app": "redis", "run": "backup1a"}
    container = deploy["spec"]["template"]["spec"]["containers"][0]
    assert container["name"] == "nginx"
    assert container["image"] == "docker.io/library/nginx:1.25"
    assert container["volumeMounts"] == [
        {"mountPath": "/ocp/data", "name": "nfs-vol1a"}]
    claim = deploy["spec"]["template"]["spec"]["volumes"][0][
        "persistentVolumeClaim"]["claimName"]
    assert claim == "sample-pvc"


def test_hook_cr_matches_cassandra_shape():
    """PRE and POST are separate command lists, same fields as the Cassandra
    hook example (execAction.command, ignoreFailure, maxRetryCount,
    timeoutSeconds)."""
    body = TvkCRs.hook(
        "sample-pvc-hook", "pvc-ns", ["/bin/sh", "-c", "sync"],
        timeout_seconds=300, max_retry_count=0)
    assert body["kind"] == "Hook"
    assert body["metadata"]["name"] == "sample-pvc-hook"
    assert body["metadata"]["namespace"] == "pvc-ns"
    pre, post = body["spec"]["pre"], body["spec"]["post"]
    assert pre["execAction"]["command"] == ["/bin/sh", "-c", "sync"]
    assert post["execAction"]["command"] == ["/bin/sh", "-c", "sync"]
    assert pre is not post
    assert pre["execAction"] is not post["execAction"]
    for side in (pre, post):
        assert side["timeoutSeconds"] == 300
        assert side["maxRetryCount"] == 0
        assert side["ignoreFailure"] is False


def test_backupplan_hook_config_matches_cassandra_shape():
    hook_cfg = TvkCRs.hook_config(
        "sample-pvc-hook", "pvc-ns",
        {"app": "redis", "run": "backup1a"},
        pod_regex="sample-pvc-deploy.*", container_regex="nginx")
    plan = TvkCRs.backupplan(
        "sample-pvc-bp", "pvc-ns", ("auto-target", "pvc-ns"),
        hook_config=hook_cfg)
    stored = plan["spec"]["hookConfig"]
    assert stored["mode"] == "Sequential"
    entry = stored["hooks"][0]
    assert entry["hook"] == {"name": "sample-pvc-hook", "namespace": "pvc-ns"}
    assert entry["podSelector"]["labels"] == [
        {"matchLabels": {"app": "redis", "run": "backup1a"}}]
    assert entry["podSelector"]["regex"] == "sample-pvc-deploy.*"
    assert entry["containerRegex"] == "nginx"
    # plans that do not ask for a hook stay unchanged
    plain = TvkCRs.backupplan("plain", "pvc-ns", ("t", "pvc-ns"))
    assert "hookConfig" not in plain["spec"]


def test_restore_carries_hook_config():
    hook_cfg = TvkCRs.hook_config(
        "sample-pvc-hook", "pvc-ns", {"app": "redis"},
        "sample-pvc-deploy.*", "nginx")
    body = TvkCRs.restore(
        "sample-pvc-restore", "pvc-ns-restore",
        ("sample-pvc-backup", "pvc-ns"), hook_config=hook_cfg)
    assert body["spec"]["hookConfig"]["hooks"][0]["hook"]["name"] == "sample-pvc-hook"
    assert body["spec"]["restoreFlags"]["skipIfAlreadyExists"] is True


def _sample_status(pre="Completed", post="Completed"):
    return {
        "status": {
            "status": "Available",
            "hookStatus": {
                "hookPriorityStatus": [{
                    "priority": 0,
                    "hooks": [{
                        "hook": {"name": "sample-pvc-hook", "namespace": "pvc-ns"},
                        "hookTarget": [{
                            "podHookStatus": [{
                                "podName": "sample-pvc-deploy-abc",
                                "containerHookStatus": [{
                                    "containerName": "nginx",
                                    "preHookStatus": {"status": pre, "exitStatus": "0"},
                                    "postHookStatus": {"status": post, "exitStatus": "0"},
                                }],
                            }],
                        }],
                    }],
                }],
            },
        }
    }


def test_assert_hooks_completed_accepts_pre_and_post():
    TvkCRs.assert_hooks_completed(_sample_status(), "sample-pvc-hook")


def test_assert_hooks_completed_rejects_failure_and_gaps():
    with pytest.raises(AssertionError, match="did not complete"):
        TvkCRs.assert_hooks_completed(_sample_status(pre="Failed"), "sample-pvc-hook")
    missing_post = _sample_status()
    container = (missing_post["status"]["hookStatus"]["hookPriorityStatus"][0]
                 ["hooks"][0]["hookTarget"][0]["podHookStatus"][0]
                 ["containerHookStatus"][0])
    del container["postHookStatus"]
    with pytest.raises(AssertionError, match="missing"):
        TvkCRs.assert_hooks_completed(missing_post, "sample-pvc-hook")
    with pytest.raises(AssertionError, match="no pre/post"):
        TvkCRs.assert_hooks_completed({"status": {"hookStatus": {}}}, "sample-pvc-hook")


# --------------------------------------------------------------------------
# cluster
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def kube(cfg):
    return KubeClient(cfg)


@pytest.fixture(scope="module")
def crs(kube):
    return TvkCRs(kube)


@pytest.fixture(scope="module")
def sample_app(kube, cfg):
    app = PvcHookApp(kube, cfg)
    app.install()
    return app


def _names(cfg):
    suffix = cfg.run_suffix
    ns = cfg.hooks.namespace
    return {
        "namespace": ns,
        "plan": f"sample-pvc-api-bp-{suffix}",
        "backup": f"sample-pvc-api-bk-{suffix}",
        "restore": f"sample-pvc-api-rs-{suffix}",
        "restore_ns": f"{ns}-api-restore-{suffix}",
    }


def _ensure_hook(crs, cfg):
    hook = hook_payload(cfg)
    existing = crs.get(HOOK, hook["name"], hook["namespace"])
    if existing:
        pre, post = crs.hook_commands(existing)
        assert pre == hook["commands"], pre
        assert post == hook["commands"], post
        print(f"[hooks-api] reusing hook '{hook['name']}'")
        return existing
    body = crs.hook(
        hook["name"], hook["namespace"], hook["commands"],
        hook["timeout_seconds"], hook["max_retry_count"])
    created = crs.create(HOOK, hook["namespace"], body)
    print(f"[hooks-api] created hook '{hook['name']}'")
    return created


@pytest.mark.hooks_backend
def test_api_install_sample_pvc_app(sample_app, cfg):
    assert sample_app.read_marker() == MARKER
    print(f"[hooks-api] app Running in '{cfg.hooks.namespace}'")


@pytest.mark.hooks_backend
def test_api_create_hook_backupplan_backup_and_restore(sample_app, crs, cfg):
    hook = hook_payload(cfg)
    names = _names(cfg)
    ns = names["namespace"]

    _ensure_hook(crs, cfg)
    target = crs.ensure_target(cfg, ns)
    plan_body = crs.backupplan(
        names["plan"], ns, target,
        hook_config=crs.hook_config(
            hook["name"], ns, hook["labels"],
            hook["pod_regex"], hook["container_regex"], hook["mode"]))
    crs.create(BACKUPPLAN, ns, plan_body)
    crs.wait_status(BACKUPPLAN, names["plan"], ns, timeout_s=300, poll_s=10)

    crs.create(BACKUP, ns, crs.backup(names["backup"], ns, names["plan"]))
    backup = crs.wait_status(BACKUP, names["backup"], ns, timeout_s=2700)
    crs.assert_hooks_completed(backup, hook["name"])

    restore_ns = names["restore_ns"]
    sample_app.kube.create_namespace(restore_ns)
    sample_app.kube.grant_hook_app_sccs(restore_ns)
    restore_hook = crs.hook(
        hook["name"], restore_ns, hook["commands"],
        hook["timeout_seconds"], hook["max_retry_count"])
    if crs.get(HOOK, hook["name"], restore_ns) is None:
        crs.create(HOOK, restore_ns, restore_hook)
    crs.create(RESTORE, restore_ns, crs.restore(
        names["restore"], restore_ns, (names["backup"], ns),
        hook_config=crs.hook_config(
            hook["name"], restore_ns, hook["labels"],
            hook["pod_regex"], hook["container_regex"], hook["mode"])))
    restored = crs.wait_status(RESTORE, names["restore"], restore_ns, timeout_s=2700)
    crs.assert_hooks_completed(restored, hook["name"])
    sample_app.kube.wait_labeled_pod_ready(restore_ns, "app=redis", timeout_s=600)
    assert sample_app.read_marker(restore_ns) == MARKER
    print(f"[hooks-api] restore '{names['restore']}' verified marker {MARKER}")
