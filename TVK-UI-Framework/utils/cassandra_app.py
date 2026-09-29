"""
Cassandra install + data seed — runs the scripts in utils/cassandra/.

install()  -> install-operator.sh  (exact order in that script)
insert_and_verify() -> insert-verify-data-500MB.sh
uninstall() -> uninstall-operator.sh  (DC, PVCs, secret, configmap, operator)
verify() -> insert-verify-data-500MB.sh with VERIFY_ONLY=true

If IF_EXISTS_PROCEED is true (default) and cass-operator / dc1 already exist,
install-operator.sh skips those apply steps and waits for the pod.
"""
import os
import subprocess
import time

import yaml

from kubernetes.client.rest import ApiException

from config.settings import FrameworkConfig

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cassandra")


class CassandraApp:
    def __init__(self, cfg: FrameworkConfig, kube):
        self.cfg = cfg
        self.kube = kube
        self.c = cfg.cassandra
        self._kubeconfig = None
        if kube is not None:
            try:
                path = os.path.join(os.path.expanduser("~"), ".tvk-kubeconfig")
                self._kubeconfig = kube.write_kubeconfig(path)
            except Exception as e:
                raise RuntimeError(f"[cassandra] could not generate kubeconfig ({e})") from e

    def _env(self):
        env = dict(os.environ)
        kc = self.cfg.cluster.kubeconfig or self._kubeconfig
        if kc:
            env["KUBECONFIG"] = kc
        env["NAMESPACE"] = self.c.namespace
        env["DC_NAME"] = self.c.dc_name
        env["CLUSTER_NAME"] = self.c.cluster_name
        env["OPERATOR_NAMESPACE"] = self.c.operator_namespace
        env["TARGET_SIZE_MB"] = str(self.c.target_size_mb)
        env["PAYLOAD_SIZE_BYTES"] = str(self.c.payload_size_bytes)
        env["PULL_SECRET_NAME"] = self.c.pull_secret_name
        env["IF_EXISTS_PROCEED"] = "true" if self.c.if_exists_proceed else "false"
        env["SKIP_DATACENTER"] = "false"
        env["VERIFY_ONLY"] = "false"
        # Empty = omit storageClassName (cluster default). Set to pin a class.
        if self.c.storage_class:
            env["STORAGE_CLASS"] = self.c.storage_class
        return env

    def _run_script(self, name: str, timeout: int, extra_env: dict | None = None):
        script = os.path.join(SCRIPT_DIR, name)
        if not os.path.isfile(script):
            raise FileNotFoundError(f"Cassandra script not found: {script}")
        env = self._env()
        if extra_env:
            env.update(extra_env)
        print(f"[cassandra] running {name} (cwd={SCRIPT_DIR})")
        r = subprocess.run(
            ["bash", script],
            cwd=SCRIPT_DIR,
            env=env,
            check=False,
            timeout=timeout,
        )
        if r.returncode != 0:
            raise RuntimeError(f"{name} failed with exit {r.returncode}")
        print(f"[cassandra] {name} completed")

    def install(self):
        """install-operator.sh:
        ns -> anyuid -> pull secret -> operator + wait CSV ->
        secret-cm -> CassandraDatacenter dc1 -> wait pod
        """
        self._run_script("install-operator.sh", timeout=self.c.ready_timeout_s + 120)

    def insert_and_verify(self):
        """insert-verify-data-500MB.sh — seed and verify data in dc1."""
        self._run_script("insert-verify-data-500MB.sh", timeout=self.c.insert_timeout_s)

    def uninstall(self, keep_configmap: bool = False):
        """uninstall-operator.sh: DC, PVCs, secret, configmap, operator.

        Leaves the namespace so TVK targets / plans / backups stay.
        """
        extra = {"KEEP_CONFIGMAP": "true" if keep_configmap else "false"}
        self._run_script("uninstall-operator.sh",
                         timeout=self.c.ready_timeout_s + 120, extra_env=extra)

    def create_configmap(self, namespace: str):
        """Create cassandra-config from secret-cm.yaml (ConfigMap only)."""
        path = os.path.join(SCRIPT_DIR, "secret-cm.yaml")
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
        cm = next((d for d in docs if d and d.get("kind") == "ConfigMap"), None)
        if not cm:
            raise RuntimeError(f"ConfigMap missing from {path}")
        cm.setdefault("metadata", {})["name"] = "cassandra-config"
        try:
            self.kube.core.create_namespaced_config_map(namespace, cm)
        except ApiException as e:
            if e.status != 409:
                raise
            self.kube.core.patch_namespaced_config_map(
                "cassandra-config", namespace, cm)
        print(f"[cassandra] configmap/cassandra-config ready in '{namespace}'")

    def verify(self, namespace: str | None = None):
        """Re-check ~500 MB live data without inserting again."""
        extra = {"VERIFY_ONLY": "true"}
        if namespace:
            extra["NAMESPACE"] = namespace
        self._run_script(
            "insert-verify-data-500MB.sh",
            timeout=self.c.insert_timeout_s,
            extra_env=extra,
        )

    def is_datacenter_ready(self, namespace: str | None = None) -> bool:
        """True if CassandraDatacenter exists and a cassandra pod is Ready."""
        if self.kube is None:
            return False
        ns, dc = namespace or self.c.namespace, self.c.dc_name
        try:
            self.kube.custom.get_namespaced_custom_object(
                "cassandra.datastax.com", "v1beta1", ns,
                "cassandradatacenters", dc)
        except ApiException:
            return False
        pods = self.kube.core.list_namespaced_pod(ns).items
        for p in pods:
            if dc not in p.metadata.name or "cassandra" not in p.metadata.name:
                continue
            statuses = p.status.container_statuses or []
            if p.status.phase == "Running" and statuses and all(s.ready for s in statuses):
                return True
        return False

    def wait_datacenter_ready(self, timeout_s: int | None = None,
                              namespace: str | None = None):
        """Wait until CassandraDatacenter exists and its pod is Ready."""
        if self.kube is None:
            raise RuntimeError("kube client is required to wait for the datacenter")
        timeout_s = timeout_s or self.c.ready_timeout_s
        ns, dc = namespace or self.c.namespace, self.c.dc_name
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.is_datacenter_ready(namespace=ns):
                print(f"[cassandra] datacenter '{dc}' Ready in '{ns}'")
                return
            remaining = int(deadline - time.time())
            print(f"[cassandra] waiting for '{dc}' in '{ns}' ({remaining}s left)")
            time.sleep(15)
        raise TimeoutError(
            f"CassandraDatacenter '{dc}' in '{ns}' did not become Ready "
            f"within {timeout_s}s")

    def _secret_present(self, namespace: str) -> bool:
        try:
            self.kube.core.read_namespaced_secret("cassandra-app-secret", namespace)
            return True
        except ApiException:
            return False

    def configmap_present(self, namespace: str) -> bool:
        try:
            self.kube.core.read_namespaced_config_map("cassandra-config", namespace)
            return True
        except ApiException:
            return False

    def wait_restore_verified(self, namespace: str, timeout_s: int | None = None):
        """After a UI restore: DC Ready, secret, configmap, then seed data."""
        timeout_s = timeout_s or self.c.ready_timeout_s
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            secret = self._secret_present(namespace)
            cm = self.configmap_present(namespace)
            dc = self.is_datacenter_ready(namespace=namespace)
            remaining = int(deadline - time.time())
            print(f"[cassandra] restore check in '{namespace}': "
                  f"secret={secret} configmap={cm} dc={dc} ({remaining}s left)")
            if secret and cm and dc:
                print(f"[cassandra] DC + secret + configmap ready in '{namespace}'")
                self.verify(namespace=namespace)
                return
            time.sleep(15)
        raise TimeoutError(
            f"Restore did not bring back CassandraDatacenter, secret, and "
            f"configmap in '{namespace}' within {timeout_s}s")
