"""TVK backup/restore stress test — CR driven, resource-aware.

Repeated backup + restore cycles across three application shapes on one cluster:
a Helm release, an operator-managed app, and a KubeVirt VM.

The design goal is that it must not fail for want of resources, so it is sized
against what the cluster can actually SCHEDULE rather than what it has:

* Memory REQUESTS are the binding constraint here (~80-88% of allocatable is
  already requested while real usage is under 45%). Pods are rejected on
  requests, not usage, so every workload carries a small explicit request and
  the peak footprint stays well inside the free request budget.
* A restore doubles an app's footprint while it exists, so each round deletes
  its restore namespaces before the next starts. Steady state stays flat
  regardless of how many rounds run.
* Backups are staggered rather than fired together, so the three apps'
  datamover pods do not all land in the same instant.

Usage:
    .venv\\Scripts\\python.exe stress_tvk.py [rounds]        # default 3
    .venv\\Scripts\\python.exe stress_tvk.py --teardown      # remove everything

Uses an isolated kubeconfig so no shared kube config is touched.
"""
import base64
import os
import subprocess
import sys
import time

from kubernetes import client
from kubernetes import config as kube_config
from kubernetes.client.rest import ApiException

# ----------------------------------------------------------------- config ---
KUBECONFIG_PATH = os.environ.get("TVK_KUBECONFIG") or (
                  "<path-to-kubeconfig>"
                   "C--Users-nikita-sadnani--claude/"
                   "1fe8b2d3-6562-4ece-9ff9-b29a7d64fec5/scratchpad/"
                   "ocp-cluster2.kubeconfig")
HELM_BIN = os.environ.get("TVK_HELM_BIN") or (
           "<path-to-kubeconfig>"
            "Helm.Helm_Microsoft.Winget.Source_8wekyb3d8bbwe/windows-amd64/helm.EXE")

TVK_NS = "trilio-system"
GROUP, VERSION = "triliovault.trilio.io", "v1"

TARGET_NAME = "stress-s3-target"
SECRET_NAME = "stress-s3-secret"
# Credentials come from the environment so they are never committed:
#   setx TVK_S3_ACCESS_KEY "..."   /  export TVK_S3_ACCESS_KEY=...
#   setx TVK_S3_SECRET_KEY "..."   /  export TVK_S3_SECRET_KEY=...
S3 = {
    "bucket": os.environ.get("TVK_S3_BUCKET", "qa-auto-s3"),
    "region": os.environ.get("TVK_S3_REGION", "us-east-1"),
    "url": os.environ.get("TVK_S3_URL", "https://s3.amazonaws.com"),
    "access_key": os.environ.get("TVK_S3_ACCESS_KEY", ""),
    "secret_key": os.environ.get("TVK_S3_SECRET_KEY", ""),
    "threshold": os.environ.get("TVK_S3_THRESHOLD", "6Gi"),
}

NS_HELM, NS_OPERATOR, NS_VM = "stress-helm", "stress-operator", "stress-vm"
HELM_RELEASE = "stress-mysql"
INFINISPAN_NAME = "stress-datagrid"
VM_NAME = "stress-fedora"

# Small explicit requests: the cluster is request-bound. TVK's own datamover
# pods request ~10m/10Mi each, so the apps are the only meaningful cost.
MYSQL_REQ_MEM, MYSQL_REQ_CPU = "384Mi", "100m"
INFINISPAN_REQ_MEM, INFINISPAN_REQ_CPU = "512Mi", "200m"
VM_MEMORY = "1Gi"
# Must be >= the Fedora DataSource volume (30Gi). CDI rejects a clone whose
# target request is smaller than the source, so a smaller disk never binds.
VM_DISK_SIZE = "30Gi"

APP_READY_TIMEOUT_S = 900
BACKUP_TIMEOUT_S = 2700
RESTORE_TIMEOUT_S = 2700
STAGGER_S = 45
MIN_FREE_REQUEST_MEM_MI = 6000   # abort if the cluster cannot schedule this

ROUNDS = 3
for _a in sys.argv[1:]:
    if _a.isdigit():
        ROUNDS = int(_a)

kube_config.load_kube_config(config_file=KUBECONFIG_PATH)
core = client.CoreV1Api()
custom = client.CustomObjectsApi()
apps = client.AppsV1Api()


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- helpers ---
def helm(*args):
    r = subprocess.run([HELM_BIN, *args], capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if "already exists" not in err and "cannot re-use" not in err:
            log(f"  helm: {err[:250]}")
    return r.returncode == 0


def ensure_ns(name):
    try:
        core.create_namespace(client.V1Namespace(
            metadata=client.V1ObjectMeta(name=name)))
        log(f"namespace '{name}' created")
    except ApiException as e:
        if e.status != 409:
            raise


def delete_ns(name):
    try:
        core.delete_namespace(name)
    except ApiException as e:
        if e.status != 404:
            raise


def cr_create(plural, ns, body, api_group=GROUP, api_version=VERSION):
    try:
        return custom.create_namespaced_custom_object(
            api_group, api_version, ns, plural, body)
    except ApiException as e:
        if e.status == 409:
            log(f"  {plural}/{body['metadata']['name']} exists — reusing")
            return None
        raise


def cr_field(plural, name, ns, path, api_group=GROUP, api_version=VERSION):
    # Catch Exception, not just ApiException: a dropped connection surfaces as
    # urllib3 MaxRetryError, which would otherwise abort an hour-long run over a
    # momentary blip. Polling should treat any read failure as "unknown yet".
    try:
        obj = custom.get_namespaced_custom_object(
            api_group, api_version, ns, plural, name)
    except Exception:
        return ""
    cur = obj
    for key in path:
        cur = (cur or {}).get(key) if isinstance(cur, dict) else None
    return cur or ""


def wait_cr(plural, name, ns, want, timeout_s):
    """Poll a TVK CR's .status.status until it hits `want` (or Failed)."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        st = cr_field(plural, name, ns, ["status", "status"])
        if st != last:
            log(f"  {plural}/{name}: {st or '<pending>'}")
            last = st
        if st in want:
            return True
        if st == "Failed":
            return False
        time.sleep(15)
    log(f"  {plural}/{name}: TIMEOUT after {timeout_s}s")
    return False


def pods_ready(ns, min_pods=1, name_prefix=None):
    # Same rationale as cr_field: transient connection errors must not be fatal.
    try:
        pods = core.list_namespaced_pod(ns).items
    except Exception:
        return False
    if name_prefix:
        # Needed for the VM: during a disk import CDI runs its own importer pod
        # in the namespace, which is Running/Ready and would otherwise be
        # mistaken for the VM being up long before virt-launcher exists.
        pods = [p for p in pods if p.metadata.name.startswith(name_prefix)]
    running = [p for p in pods
               if p.status.phase == "Running"
               and all(c.ready for c in (p.status.container_statuses or []))]
    return len(running) >= min_pods


def wait_pods(ns, min_pods=1, timeout_s=APP_READY_TIMEOUT_S, label="",
              name_prefix=None):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pods_ready(ns, min_pods, name_prefix):
            log(f"  {label or ns}: {min_pods}+ pod(s) Running/Ready")
            return True
        time.sleep(15)
    log(f"  {label or ns}: pods NOT ready in {timeout_s}s")
    return False


# --------------------------------------------------------------- preflight ---
def preflight():
    """Refuse to start if the cluster cannot schedule the planned footprint."""
    log("=== preflight: schedulable memory ===")
    nodes = [n for n in core.list_node().items
             if "node-role.kubernetes.io/worker" in (n.metadata.labels or {})]
    total_free_mi = 0
    for n in nodes:
        alloc = n.status.allocatable["memory"]
        alloc_mi = int(alloc.rstrip("Ki")) // 1024 if alloc.endswith("Ki") else 0
        req_mi = 0
        for p in core.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={n.metadata.name}").items:
            if p.status.phase not in ("Running", "Pending"):
                continue
            for c in p.spec.containers:
                m = ((c.resources.requests or {}).get("memory") if c.resources else None)
                if not m:
                    continue
                if m.endswith("Mi"):
                    req_mi += int(m[:-2])
                elif m.endswith("Gi"):
                    req_mi += int(float(m[:-2]) * 1024)
                elif m.endswith("Ki"):
                    req_mi += int(m[:-2]) // 1024
        free = alloc_mi - req_mi
        total_free_mi += max(free, 0)
        log(f"  {n.metadata.name.split('worker-0-')[-1]}: "
            f"alloc={alloc_mi}Mi requested={req_mi}Mi free={free}Mi")
    log(f"  schedulable memory across workers: {total_free_mi}Mi")

    planned = 384 + 512 + 1280      # mysql + infinispan + vm(1Gi + overhead)
    peak = planned * 2              # a restore doubles it while it exists
    log(f"  planned steady footprint: ~{planned}Mi, peak with restores: ~{peak}Mi")
    if total_free_mi < MIN_FREE_REQUEST_MEM_MI:
        log(f"ABORT: only {total_free_mi}Mi schedulable, need "
            f"{MIN_FREE_REQUEST_MEM_MI}Mi to run safely")
        return False
    log(f"  OK — {total_free_mi}Mi schedulable vs ~{peak}Mi peak need")
    return True


# ------------------------------------------------------------------ target ---
def ensure_target():
    log("=== target ===")
    if not S3["access_key"] or not S3["secret_key"]:
        log("ABORT: set TVK_S3_ACCESS_KEY and TVK_S3_SECRET_KEY in the environment")
        return False
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    try:
        core.create_namespaced_secret(TVK_NS, client.V1Secret(
            metadata=client.V1ObjectMeta(name=SECRET_NAME, namespace=TVK_NS),
            data={"accessKey": b64(S3["access_key"]),
                  "secretKey": b64(S3["secret_key"])}))
        log(f"  secret '{SECRET_NAME}' created")
    except ApiException as e:
        if e.status != 409:
            raise
        log(f"  secret '{SECRET_NAME}' exists")

    # rc.5 rejects inline credentials — they must come via credentialSecret.
    cr_create("targets", TVK_NS, {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "Target",
        "metadata": {"name": TARGET_NAME, "namespace": TVK_NS},
        "spec": {
            "type": "ObjectStore",
            "vendor": "AWS",
            "thresholdCapacity": S3["threshold"],
            "objectStoreCredentials": {
                "bucketName": S3["bucket"],
                "region": S3["region"],
                "url": S3["url"],
                "credentialSecret": {"name": SECRET_NAME, "namespace": TVK_NS},
            },
        },
    })
    return wait_cr("targets", TARGET_NAME, TVK_NS, ("Available",), 600)


# -------------------------------------------------------------------- apps ---
def deploy_helm_app():
    log("=== app 1/3: Helm release (MySQL) ===")
    ensure_ns(NS_HELM)
    helm("repo", "add", "stable", "https://charts.helm.sh/stable")
    helm("repo", "update")
    ok = helm("install", HELM_RELEASE, "stable/mysql",
              "--namespace", NS_HELM,
              "--set", "image=us-central1-docker.pkg.dev/tvk-solutions-330321/tvk-interop/mysql",
              "--set", "imageTag=latest",
              "--set", "testFramework.enabled=false",
              "--set", f"resources.requests.memory={MYSQL_REQ_MEM}",
              "--set", f"resources.requests.cpu={MYSQL_REQ_CPU}",
              "--set", "persistence.size=2Gi")
    if not ok:
        log("  (install returned non-zero — may already exist, continuing)")
    return wait_pods(NS_HELM, 1, label="helm/mysql")


def deploy_operator_app():
    log("=== app 2/3: operator-managed app (Data Grid / Infinispan) ===")
    ensure_ns(NS_OPERATOR)
    cr_create("infinispans", NS_OPERATOR, {
        "apiVersion": "infinispan.org/v1",
        "kind": "Infinispan",
        "metadata": {"name": INFINISPAN_NAME, "namespace": NS_OPERATOR},
        "spec": {
            "replicas": 1,
            "service": {"type": "DataGrid"},
            "container": {"memory": INFINISPAN_REQ_MEM, "cpu": INFINISPAN_REQ_CPU},
        },
    }, api_group="infinispan.org", api_version="v1")
    return wait_pods(NS_OPERATOR, 1, label="operator/infinispan")


def deploy_vm():
    log("=== app 3/3: KubeVirt VM (Fedora) ===")
    ensure_ns(NS_VM)
    cr_create("virtualmachines", NS_VM, {
        "apiVersion": "kubevirt.io/v1",
        "kind": "VirtualMachine",
        "metadata": {"name": VM_NAME, "namespace": NS_VM},
        "spec": {
            "running": True,
            "dataVolumeTemplates": [{
                "metadata": {"name": f"{VM_NAME}-disk"},
                "spec": {
                    "sourceRef": {"kind": "DataSource", "name": "fedora",
                                  "namespace": "openshift-virtualization-os-images"},
                    "storage": {"resources": {"requests": {"storage": VM_DISK_SIZE}}},
                },
            }],
            "template": {
                "metadata": {"labels": {"kubevirt.io/domain": VM_NAME}},
                "spec": {
                    "domain": {
                        "cpu": {"cores": 1},
                        "resources": {"requests": {"memory": VM_MEMORY}},
                        "devices": {"disks": [
                            {"name": "rootdisk", "disk": {"bus": "virtio"}}]},
                    },
                    "volumes": [{"name": "rootdisk",
                                 "dataVolume": {"name": f"{VM_NAME}-disk"}}],
                },
            },
        },
    }, api_group="kubevirt.io", api_version="v1")
    # The 30Gi disk is imported before the VM boots, so allow longer here, and
    # match only virt-launcher so the importer pod cannot be mistaken for it.
    return wait_pods(NS_VM, 1, timeout_s=2400, label="vm/fedora",
                     name_prefix="virt-launcher")


# ------------------------------------------------------------ backup plans ---
APPS = [
    {"key": "helm", "ns": NS_HELM, "plan": "bp-stress-helm",
     "components": {"helmReleases": [HELM_RELEASE]}},
    {"key": "operator", "ns": NS_OPERATOR, "plan": "bp-stress-operator",
     "components": {}},          # namespace-scoped: captures the operator CR
    {"key": "vm", "ns": NS_VM, "plan": "bp-stress-vm",
     "components": {}},          # namespace-scoped: captures VM + DataVolume
]


def ensure_backupplans():
    log("=== backup plans ===")
    ok = True
    for a in APPS:
        spec = {"backupConfig": {"target": {"name": TARGET_NAME, "namespace": TVK_NS}}}
        if a["components"]:
            spec["backupPlanComponents"] = a["components"]
        cr_create("backupplans", a["ns"], {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "BackupPlan",
            "metadata": {"name": a["plan"], "namespace": a["ns"]},
            "spec": spec,
        })
        ok &= wait_cr("backupplans", a["plan"], a["ns"], ("Available",), 600)
    return ok


# ------------------------------------------------------------------ rounds ---
def run_round(rnd, results):
    log(f"########## ROUND {rnd} ##########")

    # --- backups, staggered so datamovers don't all start together
    backups = []
    for a in APPS:
        name = f"bk-{a['key']}-r{rnd}"
        cr_create("backups", a["ns"], {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Backup",
            "metadata": {"name": name, "namespace": a["ns"]},
            "spec": {"type": "Full",
                     "backupPlan": {"name": a["plan"], "namespace": a["ns"]}},
        })
        log(f"  backup '{name}' submitted ({a['key']})")
        backups.append((a, name))
        time.sleep(STAGGER_S)

    for a, name in backups:
        ok = wait_cr("backups", name, a["ns"], ("Available",), BACKUP_TIMEOUT_S)
        size = cr_field("backups", name, a["ns"], ["status", "size"])
        results.append({"round": rnd, "app": a["key"], "op": "backup",
                        "name": name, "ok": ok, "size": size})
        log(f"  BACKUP {a['key']} r{rnd}: {'OK' if ok else 'FAIL'} (size={size})")

    # --- restores into fresh namespaces
    restores = []
    for a, bname in backups:
        rns = f"{a['ns']}-restore-r{rnd}"
        ensure_ns(rns)
        rname = f"rs-{a['key']}-r{rnd}"
        cr_create("restores", rns, {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Restore",
            "metadata": {"name": rname, "namespace": rns},
            "spec": {
                "source": {"type": "Backup",
                           "backup": {"name": bname, "namespace": a["ns"]}},
                "restoreNamespace": rns,
                # MUST sit under restoreFlags — a top-level skipIfAlreadyExists
                # is silently ignored. Without it, a namespace-scoped restore
                # fails Validation because the backup captured OpenShift's
                # auto-created RBAC (RoleBinding system:deployers and the
                # CLUSTER-scoped ClusterRole system:deployer), which already
                # exists. Helm-scoped plans never hit this: they only capture
                # the release's own resources.
                "restoreFlags": {"skipIfAlreadyExists": True},
            },
        })
        log(f"  restore '{rname}' submitted -> {rns}")
        restores.append((a, rname, rns))
        time.sleep(STAGGER_S)

    for a, rname, rns in restores:
        ok = wait_cr("restores", rname, rns, ("Completed",), RESTORE_TIMEOUT_S)
        # Give the workload a moment to schedule: the Restore CR reports
        # Completed as soon as the resources are applied, which is before the
        # pods are up. Checking instantly reported healthy=False on restores
        # that were in fact fine.
        healthy = wait_pods(rns, 1, timeout_s=300,
                            label=f"restored/{a['key']}") if ok else False
        results.append({"round": rnd, "app": a["key"], "op": "restore",
                        "name": rname, "ok": ok and healthy, "size": rns})
        log(f"  RESTORE {a['key']} r{rnd}: "
            f"{'OK' if ok else 'FAIL'} (pods_ready={healthy})")

    # --- drop the restore namespaces so the footprint stays flat
    for _, _, rns in restores:
        delete_ns(rns)
    log(f"  round {rnd}: restore namespaces removed (footprint reset)")


# ---------------------------------------------------------------- teardown ---
def teardown():
    log("=== teardown ===")
    for ns in [NS_HELM, NS_OPERATOR, NS_VM]:
        for suffix in [""] + [f"-restore-r{i}" for i in range(1, 11)]:
            delete_ns(ns + suffix)
    try:
        custom.delete_namespaced_custom_object(
            GROUP, VERSION, TVK_NS, "targets", TARGET_NAME)
    except ApiException:
        pass
    try:
        core.delete_namespaced_secret(SECRET_NAME, TVK_NS)
    except ApiException:
        pass
    log("teardown requested for all stress-* namespaces, target and secret")


# -------------------------------------------------------------------- main ---
def main():
    if "--teardown" in sys.argv:
        teardown()
        return

    t0 = time.time()
    if not preflight():
        sys.exit(1)
    if not ensure_target():
        log("ABORT: target did not reach Available")
        sys.exit(1)

    ready = {"helm": deploy_helm_app(),
             "operator": deploy_operator_app(),
             "vm": deploy_vm()}
    log(f"app readiness: {ready}")
    live = [a for a in APPS if ready.get(a["key"])]
    if not live:
        log("ABORT: no application became ready")
        sys.exit(1)
    if len(live) < len(APPS):
        skipped = [a["key"] for a in APPS if not ready.get(a["key"])]
        log(f"NOTE: continuing without {skipped} — they did not become ready")
    APPS[:] = live

    if not ensure_backupplans():
        log("ABORT: a backup plan did not reach Available")
        sys.exit(1)

    results = []
    for rnd in range(1, ROUNDS + 1):
        run_round(rnd, results)

    # ------------------------------------------------------------- summary ---
    log("")
    log("================ STRESS SUMMARY ================")
    ok_n = sum(1 for r in results if r["ok"])
    for r in results:
        log(f"  r{r['round']} {r['app']:<9} {r['op']:<8} "
            f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']}")
    log(f"  {ok_n}/{len(results)} operations passed "
        f"over {ROUNDS} round(s) in {int(time.time() - t0) // 60}m")
    failures = [r for r in results if not r["ok"]]
    if failures:
        log(f"  FAILURES: {[(r['app'], r['op'], r['round']) for r in failures]}")
    log("===============================================")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
