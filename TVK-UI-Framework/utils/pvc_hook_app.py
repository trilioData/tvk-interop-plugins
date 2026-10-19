"""Install the sample PVC workload the hooks suites back up.

The manifests live in sample-pvc-app.yaml (the attached kubectl script).
OpenShift needs the anyuid and privileged SCC RoleBindings before the
nginx:1.25 pod can start; if the pod is not Running the caller fails
before any console or backup work.
"""
from pathlib import Path

import yaml
from kubernetes.dynamic import DynamicClient

from utils.feature_apps import FeatureApps

MANIFEST = Path(__file__).with_name("sample-pvc-app.yaml")
POD_LABEL = "app=redis"
MARKER = "hook-marker-pvc"
MARKER_PATH = "/ocp/data/marker.txt"


def load_manifests() -> list[dict]:
    docs = [d for d in yaml.safe_load_all(MANIFEST.read_text()) if d]
    if len(docs) != 2:
        raise AssertionError(f"{MANIFEST.name} should contain a PVC and a Deployment")
    return docs


def hook_payload(cfg) -> dict:
    """The hook the console types in, and the CR the backend suite creates."""
    h = cfg.hooks
    return {
        "name": h.name,
        "namespace": h.namespace,
        "commands": list(h.commands),
        "timeout_seconds": int(h.timeout_seconds),
        "max_retry_count": int(h.max_retry_count),
        "labels": dict(h.pod_labels),
        "pod_regex": h.pod_regex,
        "container_regex": h.container_regex,
        "mode": h.mode,
    }


class PvcHookApp:
    def __init__(self, kube, cfg):
        self.kube = kube
        self.cfg = cfg
        self.namespace = cfg.hooks.namespace
        self.pod_name = ""

    def install(self) -> str:
        """Create the namespace, SCC grants, PVC and Deployment. Fail if the
        pod does not become Running."""
        ns = self.namespace
        print(f"[pvc-app] creating namespace '{ns}'")
        self.kube.create_namespace(ns)
        print(f"[pvc-app] granting anyuid to the default SA and privileged "
              f"to system:authenticated in '{ns}'")
        self.kube.grant_hook_app_sccs(ns)
        self._apply(ns)
        self.pod_name = self.kube.wait_labeled_pod_ready(ns, POD_LABEL, timeout_s=600)
        self.seed_marker()
        return self.pod_name

    def _apply(self, namespace: str):
        dyn = DynamicClient(self.kube.api_client)
        for doc in load_manifests():
            doc.setdefault("metadata", {})["namespace"] = namespace
            api = dyn.resources.get(api_version=doc["apiVersion"], kind=doc["kind"])
            name = doc["metadata"]["name"]
            try:
                api.create(body=doc, namespace=namespace)
                print(f"[pvc-app] created {doc['kind']}/{name} in '{namespace}'")
            except Exception as e:
                if getattr(e, "status", None) != 409:
                    raise
                print(f"[pvc-app] {doc['kind']}/{name} already exists in '{namespace}'")

    def seed_marker(self):
        """Write a known file onto the PVC so the hook's `sync` has data to
        flush and the restore can prove the bytes came back."""
        script = f"echo {MARKER} > {MARKER_PATH} && sync && cat {MARKER_PATH}"
        out = FeatureApps(self.kube).exec_sh(self.namespace, POD_LABEL, script)
        if MARKER not in (out or ""):
            raise AssertionError(
                f"could not seed {MARKER_PATH} in '{self.namespace}': {out!r}")
        print(f"[pvc-app] seeded {MARKER_PATH} in '{self.namespace}'")

    def read_marker(self, namespace: str | None = None) -> str:
        ns = namespace or self.namespace
        out = FeatureApps(self.kube).exec_sh(
            ns, POD_LABEL, f"cat {MARKER_PATH}", timeout_s=180)
        return (out or "").strip()
