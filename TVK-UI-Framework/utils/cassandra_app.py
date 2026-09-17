"""
Cassandra install + data seed — runs the scripts in utils/cassandra/.

install()  -> install-operator.sh  (exact order in that script)
insert_and_verify() -> insert-verify-data-500MB.sh

Do not skip the operator because a CRD already exists. The script always
applies the subscription and waits for the CSV before secret-cm and dc1.
"""
import os
import subprocess

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
                print(f"[cassandra] could not generate kubeconfig ({e})")

    def _env(self):
        env = dict(os.environ)
        kc = self.cfg.cluster.kubeconfig or self._kubeconfig
        if kc:
            env["KUBECONFIG"] = kc
        env["NAMESPACE"] = self.c.namespace
        env["DC_NAME"] = self.c.dc_name
        env["OPERATOR_NAMESPACE"] = self.c.operator_namespace
        env["TARGET_SIZE_MB"] = str(self.c.target_size_mb)
        env["PAYLOAD_SIZE_BYTES"] = str(self.c.payload_size_bytes)
        # Empty = omit storageClassName (cluster default). Set to pin a class.
        if self.c.storage_class:
            env["STORAGE_CLASS"] = self.c.storage_class
        return env

    def _run_script(self, name: str, timeout: int):
        script = os.path.join(SCRIPT_DIR, name)
        if not os.path.isfile(script):
            raise FileNotFoundError(f"Cassandra script not found: {script}")
        print(f"[cassandra] running {name} (cwd={SCRIPT_DIR})")
        r = subprocess.run(
            ["bash", script],
            cwd=SCRIPT_DIR,
            env=self._env(),
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
