"""
TVK custom-resource helpers (Policy / BackupPlan / Backup / Restore).

Everything goes through CustomObjectsApi on the existing KubeClient, so this
inherits its OCP OAuth connectivity and needs no CLI.

Why builders return plain dicts: the TVK schemas differ between releases (the
Target schema changed in 5.4.0-rc.5, for instance), so keeping the bodies as
data makes them easy to diff against a CRD and to tweak per-version without
touching the tests.
"""
import time

from kubernetes.client.rest import ApiException

GROUP = "triliovault.trilio.io"
VERSION = "v1"

# plural names as registered by the CRDs
POLICY = "policies"
BACKUPPLAN = "backupplans"
BACKUP = "backups"
RESTORE = "restores"
TARGET = "targets"
HOOK = "hooks"

# statuses that mean "stop waiting"
TERMINAL_OK = {"Available", "Completed", "Ready"}
TERMINAL_BAD = {"Failed", "Error", "Unavailable"}


class TvkCRs:
    def __init__(self, kube):
        self.kube = kube
        self.custom = kube.custom

    # ---------- generic CRUD ----------

    def create(self, plural: str, namespace: str, body: dict) -> dict:
        return self.custom.create_namespaced_custom_object(
            GROUP, VERSION, namespace, plural, body)

    def get(self, plural: str, name: str, namespace: str) -> dict | None:
        try:
            return self.custom.get_namespaced_custom_object(
                GROUP, VERSION, namespace, plural, name)
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def list_all(self, plural: str, namespace: str) -> list[dict]:
        return self.custom.list_namespaced_custom_object(
            GROUP, VERSION, namespace, plural).get("items", [])

    def patch(self, plural: str, name: str, namespace: str, body: dict) -> dict:
        return self.custom.patch_namespaced_custom_object(
            GROUP, VERSION, namespace, plural, name, body)

    def delete(self, plural: str, name: str, namespace: str, ignore_missing=True):
        try:
            return self.custom.delete_namespaced_custom_object(
                GROUP, VERSION, namespace, plural, name)
        except ApiException as e:
            if e.status == 404 and ignore_missing:
                return None
            raise

    def force_delete(self, plural: str, name: str, namespace: str):
        """Strip finalizers first.

        TVK CRs carry cleanup finalizers (backup-cleanup-finalizer and friends).
        If the control plane is unhealthy, or the resource is mid-flight, a plain
        delete leaves the object stuck in Terminating forever.
        """
        try:
            self.patch(plural, name, namespace, {"metadata": {"finalizers": []}})
        except ApiException:
            pass
        self.delete(plural, name, namespace)

    # ---------- waiting ----------

    @staticmethod
    def status_of(obj: dict) -> str:
        return ((obj or {}).get("status") or {}).get("status") or ""

    @staticmethod
    def phase_of(obj: dict) -> str:
        return ((obj or {}).get("status") or {}).get("phase") or ""

    def wait_status(self, plural: str, name: str, namespace: str,
                    timeout_s: int = 1800, poll_s: int = 15,
                    want: set[str] | None = None) -> dict:
        """Poll until the CR reaches a terminal status. Returns the final object.

        Raises TimeoutError on timeout and AssertionError on a bad terminal
        status, so a test failure names the resource and its last phase rather
        than surfacing as an opaque None.
        """
        want = want or TERMINAL_OK
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            obj = self.get(plural, name, namespace)
            if obj:
                st, ph = self.status_of(obj), self.phase_of(obj)
                if (st, ph) != last:
                    print(f"[tvk] {plural}/{name}: status={st or '-'} phase={ph or '-'}")
                    last = (st, ph)
                if st in want:
                    return obj
                if st in TERMINAL_BAD:
                    raise AssertionError(
                        f"{plural}/{name} reached {st} in phase {ph}: "
                        f"{self.last_reason(obj)}")
            time.sleep(poll_s)
        raise TimeoutError(
            f"{plural}/{name} did not reach {want} within {timeout_s}s "
            f"(last status={last})")

    @staticmethod
    def assert_hooks_completed(obj: dict, hook_name: str) -> None:
        """Both the pre and post command finished Completed, and the status
        names this hook.

        TVK records that under status.hookStatus.hookPriorityStatus[].hooks[].
        hookTarget[].podHookStatus[].containerHookStatus[] as preHookStatus /
        postHookStatus. Walking the tree avoids depending on every intermediate
        key staying stable.
        """
        hook_status = ((obj or {}).get("status") or {}).get("hookStatus") or {}
        phases = _hook_phases(hook_status)
        if not phases:
            raise AssertionError(
                f"backup/restore status has no pre/post hook results for "
                f"'{hook_name}': {hook_status}")
        bad = [p for p in phases if p.get("status") != "Completed"]
        if bad:
            raise AssertionError(
                f"hook '{hook_name}' did not complete: {bad}")
        seen = {p["phase"] for p in phases}
        missing = {"pre", "post"} - seen
        if missing:
            raise AssertionError(
                f"hook '{hook_name}' missing {sorted(missing)} results; "
                f"saw {sorted(seen)}")
        if not _tree_has_name(hook_status, hook_name):
            raise AssertionError(
                f"hookStatus does not reference hook '{hook_name}'")

    @staticmethod
    def last_reason(obj: dict) -> str:
        conds = ((obj or {}).get("status") or {}).get("condition") or []
        return (conds[-1].get("reason") if conds else "") or ""

    # ---------- body builders ----------

    @staticmethod
    def schedule_policy(name: str, namespace: str, crons: list[str]) -> dict:
        return {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Policy",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"type": "Schedule", "scheduleConfig": {"schedule": crons}},
        }

    @staticmethod
    def retention_policy(name: str, namespace: str, latest: int = 5,
                         weekly: int | None = None, day_of_week: str | None = None) -> dict:
        cfg = {"latest": latest}
        if weekly:
            cfg["weekly"] = weekly
        if day_of_week:
            cfg["dayOfWeek"] = day_of_week
        return {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Policy",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"type": "Retention", "retentionConfig": cfg},
        }

    @staticmethod
    def hook(name: str, namespace: str, commands: list[str],
             timeout_seconds: int = 300, max_retry_count: int = 0,
             ignore_failure: bool = False) -> dict:
        """PRE and POST hook. Same command shape as the Cassandra example
        (`bash -c ...`), with the PVC suite's `/bin/sh -c sync` argv."""
        def action() -> dict:
            return {
                "execAction": {"command": list(commands)},
                "ignoreFailure": ignore_failure,
                "maxRetryCount": max_retry_count,
                "timeoutSeconds": timeout_seconds,
            }
        return {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Hook",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"pre": action(), "post": action()},
        }

    @staticmethod
    def hook_config(hook_name: str, hook_namespace: str, match_labels: dict,
                    pod_regex: str, container_regex: str,
                    mode: str = "Sequential") -> dict:
        """BackupPlan / Restore hookConfig.

        Mirrors the documented Cassandra backup plan: Sequential mode, one
        hook, podSelector matchLabels + regex, and a container regex.
        """
        return {
            "mode": mode,
            "hooks": [{
                "hook": {"name": hook_name, "namespace": hook_namespace},
                "podSelector": {
                    "labels": [{"matchLabels": dict(match_labels)}],
                    "regex": pod_regex,
                },
                "containerRegex": container_regex,
            }],
        }

    @staticmethod
    def hook_commands(obj: dict) -> tuple[list, list]:
        spec = (obj or {}).get("spec") or {}
        def cmds(side: str) -> list:
            return (((spec.get(side) or {}).get("execAction") or {}).get("command") or [])
        return cmds("pre"), cmds("post")

    @staticmethod
    def backupplan(name: str, namespace: str, target: tuple[str, str],
                   schedule_policy: tuple[str, str] | None = None,
                   retention_policy: tuple[str, str] | None = None,
                   helm_releases: list[str] | None = None,
                   match_labels: dict | None = None,
                   hook_config: dict | None = None) -> dict:
        """Namespace-scoped plan when neither helm_releases nor match_labels given.

        target / policies are (name, namespace) pairs — cross-namespace refs work,
        so one target in trilio-system can serve every plan.
        """
        backup_config = {"target": {"name": target[0], "namespace": target[1]}}
        if schedule_policy:
            backup_config["schedulePolicy"] = {
                "fullBackupPolicy": {"name": schedule_policy[0],
                                     "namespace": schedule_policy[1]}}
        if retention_policy:
            backup_config["retentionPolicy"] = {"name": retention_policy[0],
                                                "namespace": retention_policy[1]}

        spec = {"backupConfig": backup_config}
        if helm_releases:
            spec["backupPlanComponents"] = {"helmReleases": helm_releases}
        elif match_labels:
            # nesting matters: customSelector.selectResources.labelSelector
            spec["backupPlanComponents"] = {
                "customSelector": {
                    "selectResources": {"labelSelector": [{"matchLabels": match_labels}]}}}
        if hook_config:
            spec["hookConfig"] = hook_config
        return {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "BackupPlan",
            "metadata": {"name": name, "namespace": namespace},
            "spec": spec,
        }

    @staticmethod
    def backup(name: str, namespace: str, backupplan: str,
               backup_type: str = "Full") -> dict:
        return {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Backup",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"type": backup_type,
                     "backupPlan": {"name": backupplan, "namespace": namespace}},
        }

    @staticmethod
    def restore(name: str, namespace: str, backup: tuple[str, str],
                skip_if_exists: bool = True,
                transform_custom: list[dict] | None = None,
                extra_flags: dict | None = None,
                hook_config: dict | None = None) -> dict:
        """The Restore CR's own namespace is the restore target namespace.

        skip_if_exists defaults True because on OpenShift every namespace is
        pre-populated with kube-root-ca.crt, openshift-service-ca.crt and the
        system: rolebindings, which a namespace-scoped backup captures — without
        the flag the restore fails validation on those collisions.
        """
        flags = {"skipIfAlreadyExists": skip_if_exists}
        if extra_flags:
            flags.update(extra_flags)
        spec = {
            "source": {"type": "Backup",
                       "backup": {"name": backup[0], "namespace": backup[1]}},
            "restoreFlags": flags,
        }
        if transform_custom:
            spec["transformComponents"] = {"custom": transform_custom}
        if hook_config:
            spec["hookConfig"] = hook_config
        return {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Restore",
            "metadata": {"name": name, "namespace": namespace},
            "spec": spec,
        }

    @staticmethod
    def custom_transform(transform_name: str, kind: str, objects: list[str],
                         patches: list[dict], group: str = "apps",
                         version: str = "v1") -> dict:
        """One entry for transformComponents.custom (RFC-6902 style patches)."""
        return {
            "transformName": transform_name,
            "resources": {
                "groupVersionKind": {"group": group, "version": version, "kind": kind},
                "objects": objects,
            },
            "jsonPatches": patches,
        }

    # ---------- schedule introspection ----------

    def cron_map(self, plan: str, namespace: str) -> dict:
        """status.fullBackupCrons — cron expression -> CronJob object reference.

        This is how a Schedule Policy becomes observable: TVK compiles it into a
        real Kubernetes CronJob per BackupPlan, and records the mapping here. It
        lets a test assert registration without waiting for the schedule to fire.
        """
        obj = self.get(BACKUPPLAN, plan, namespace) or {}
        return (obj.get("status") or {}).get("fullBackupCrons") or {}

    def scheduled_backups(self, plan: str, namespace: str) -> list[dict]:
        """Backups created by the schedule rather than by hand.

        TVK names scheduled backups '<plan>-<uuid>'; manually created ones keep
        whatever name was given, so the prefix plus a longer name is a reliable
        discriminator.
        """
        return [b for b in self.list_all(BACKUP, namespace)
                if b["metadata"]["name"].startswith(f"{plan}-")
                and len(b["metadata"]["name"]) > len(plan) + 8]

    def ensure_target(self, cfg, namespace: str) -> tuple[str, str]:
        """Create the configured target in `namespace` if it is not already there.

        Object-store targets take their keys from cfg (or TVK_S3_ACCESS_KEY /
        TVK_S3_SECRET_KEY). NFS targets use cfg.target.nfs_path. Returns
        (name, namespace) for BackupPlan.spec.backupConfig.target.
        """
        import base64

        from kubernetes import client
        from kubernetes.client.rest import ApiException

        t = cfg.target
        name = t.name
        kind = (t.type or "").lower()
        if kind == "nfs":
            if not t.nfs_path:
                raise AssertionError(
                    "target.nfs_path is required to create the NFS target "
                    "used by the hooks suite")
            body = {
                "apiVersion": f"{GROUP}/{VERSION}",
                "kind": "Target",
                "metadata": {"name": name, "namespace": namespace},
                "spec": {
                    "type": "NFS",
                    "vendor": "Other",
                    "thresholdCapacity": t.threshold_capacity or "10Gi",
                    "nfsCredentials": {
                        "nfsExport": t.nfs_path,
                        "nfsOptions": "nfsvers=4",
                    },
                },
            }
        else:
            if not (t.bucket and t.access_key and t.secret_key):
                raise AssertionError(
                    "Object-store target needs target.bucket plus "
                    "TVK_S3_ACCESS_KEY and TVK_S3_SECRET_KEY")
            secret_name = f"{name}-secret"
            def encoded(value: str) -> str:
                return base64.b64encode(value.encode()).decode()
            secret = client.V1Secret(
                metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace),
                data={"accessKey": encoded(t.access_key),
                      "secretKey": encoded(t.secret_key)},
            )
            try:
                self.kube.core.create_namespaced_secret(namespace, secret)
                print(f"[tvk] secret '{secret_name}' created in '{namespace}'")
            except ApiException as e:
                if e.status != 409:
                    raise
                print(f"[tvk] secret '{secret_name}' already exists")
            creds = {
                "bucketName": t.bucket,
                "credentialSecret": {"name": secret_name, "namespace": namespace},
            }
            if t.region:
                creds["region"] = t.region
            if t.s3_url:
                creds["url"] = t.s3_url
            body = {
                "apiVersion": f"{GROUP}/{VERSION}",
                "kind": "Target",
                "metadata": {"name": name, "namespace": namespace},
                "spec": {
                    "type": "ObjectStore",
                    "vendor": t.vendor or "AWS",
                    "thresholdCapacity": t.threshold_capacity or "10Gi",
                    "objectStoreCredentials": creds,
                },
            }
        if not self.get(TARGET, name, namespace):
            self.create(TARGET, namespace, body)
            print(f"[tvk] target '{name}' created in '{namespace}'")
        else:
            print(f"[tvk] target '{name}' already exists in '{namespace}'")
        self.wait_status(TARGET, name, namespace, timeout_s=600, poll_s=10)
        return name, namespace


def _hook_phases(node) -> list[dict]:
    """Every preHookStatus / postHookStatus dict under a hookStatus tree."""
    found: list[dict] = []

    def walk(current):
        if isinstance(current, dict):
            for key, phase in (("preHookStatus", "pre"), ("postHookStatus", "post")):
                side = current.get(key)
                if isinstance(side, dict) and "status" in side:
                    found.append({"phase": phase, **side})
            for value in current.values():
                walk(value)
        elif isinstance(current, list):
            for item in current:
                walk(item)

    walk(node)
    return found


def _tree_has_name(node, name: str) -> bool:
    if isinstance(node, dict):
        if node.get("name") == name:
            return True
        return any(_tree_has_name(v, name) for v in node.values())
    if isinstance(node, list):
        return any(_tree_has_name(item, name) for item in node)
    return False
