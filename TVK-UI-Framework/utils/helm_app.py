"""
Install the MySQL helm chart (mysql-qa) used for Helm-transformation tests.

Python port of the shell install logic:
  - if the release already exists -> (optionally) proceed and wait for Ready
  - else `helm install` with the interop image overrides
  - on OpenShift, grant anyuid SCC + cluster-admin to the namespace's SAs
  - wait until the app pods (label app=mysql-qa) are Running/Ready

Helm has no Python API, so `helm`/`oc` are invoked via subprocess (the chart
install genuinely needs the helm CLI). Namespace creation and pod-readiness
use the Kubernetes API via KubeClient.
"""
import os
import shutil
import subprocess
import time

from config.settings import FrameworkConfig


class HelmApp:
    def __init__(self, cfg: FrameworkConfig, kube):
        self.cfg = cfg
        self.kube = kube          # KubeClient — for namespace + pod checks
        self.h = cfg.helm_app
        self.helm = self._resolve_helm()
        # helm/oc need a kubeconfig; the framework auth is token-based, so
        # generate a temp kubeconfig from the token for the CLIs to use.
        self._kubeconfig = None
        if kube is not None:
            try:
                path = os.path.join(os.path.expanduser("~"), ".tvk-kubeconfig")
                self._kubeconfig = kube.write_kubeconfig(path)
            except Exception as e:
                print(f"[helm] could not generate kubeconfig ({e})")

    # ---------- CLI helpers ----------

    def _resolve_helm(self) -> str:
        """Find helm: configured path, then PATH, then common user-install
        locations (e.g. ~/.local/bin/helm[.exe]) — so a freshly installed
        helm works even before a PATH change takes effect in new shells."""
        if self.h.helm_bin and os.path.exists(self.h.helm_bin):
            return self.h.helm_bin
        found = shutil.which("helm")
        if found:
            return found
        candidates = [
            os.path.join(os.path.expanduser("~"), ".local", "bin", "helm.exe"),
            os.path.join(os.path.expanduser("~"), ".local", "bin", "helm"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return ""

    def _env(self):
        env = dict(os.environ)
        kc = self.cfg.cluster.kubeconfig or self._kubeconfig
        if kc:
            env["KUBECONFIG"] = kc
        return env

    def _run(self, args, check=True):
        # swap a leading 'helm' for the resolved absolute path
        if args and args[0] == "helm" and self.helm:
            args = [self.helm] + args[1:]
        print(f"[helm] $ {' '.join(args)}")
        return subprocess.run(args, capture_output=True, text=True,
                              env=self._env(), check=check, timeout=900)

    def _require(self, tool):
        if tool == "helm":
            if not self.helm:
                raise RuntimeError(
                    "'helm' not found. Install it (no admin) and set "
                    "helm_app.helm_bin in config, or add it to PATH.")
            return
        if not shutil.which(tool):
            raise RuntimeError(f"'{tool}' CLI not found on PATH")

    def _release_exists(self, namespace) -> bool:
        r = self._run(["helm", "list", "-n", namespace], check=False)
        for line in r.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == self.h.release_name:
                return True
        return False

    # ---------- install ----------

    def install(self, namespace):
        """Install (or reuse) the mysql-qa helm app in namespace, then wait
        until it is Ready. Returns the label selector to use in a custom
        backup plan (e.g. 'app=mysql-qa')."""
        self._require("helm")
        self.kube.create_namespace(namespace)   # idempotent (API)

        if self._release_exists(namespace):
            print(f"[helm] release '{self.h.release_name}' already exists")
            if not self.h.if_exists_proceed:
                raise RuntimeError(
                    f"helm release '{self.h.release_name}' exists and "
                    "if_exists_proceed is false")
        else:
            print(f"[helm] installing '{self.h.release_name}' ({self.h.chart})")
            self._run(["helm", "repo", "add", self.h.repo_name, self.h.repo_url],
                      check=False)
            self._run(["helm", "repo", "update"], check=False)
            self._run([
                "helm", "install", self.h.release_name, self.h.chart,
                "--set", f"image={self.h.image}",
                "--set", f"imageTag={self.h.image_tag}",
                "--set", f"pullPolicy={self.h.pull_policy}",
                "--set", f"busybox.image={self.h.busybox_image}",
                "--set", f"busybox.tag={self.h.busybox_tag}",
                "--set", "testFramework.enabled=false",
                "-n", namespace,
            ])
            time.sleep(5)

        # OpenShift: grant anyuid SCC + cluster-admin to every SA in the ns
        if self.h.openshift:
            self._grant_scc(namespace)

        self._wait_ready(namespace)
        print("[helm] requested application is Up and Running!")
        return self.h.label

    def _grant_scc(self, namespace):
        """oc adm policy add-scc-to-user anyuid / add-cluster-role-to-user
        cluster-admin for each service account in the namespace."""
        if not shutil.which("oc"):
            print("[helm] 'oc' not found — skipping OpenShift SCC grants")
            return
        try:
            sas = self.kube.core.list_namespaced_service_account(namespace).items
        except Exception as e:
            print(f"[helm] could not list service accounts ({e}) — skipping SCC")
            return
        for sa in sas:
            name = sa.metadata.name
            self._run(["oc", "adm", "policy", "add-scc-to-user", "anyuid",
                       "-z", name, "-n", namespace], check=False)
            self._run(["oc", "adm", "policy", "add-cluster-role-to-user",
                       "cluster-admin", "-z", name, "-n", namespace], check=False)

    def _wait_ready(self, namespace, timeout_s=None):
        """Wait until pods matching the app label are Running and Ready."""
        timeout_s = timeout_s or self.h.ready_timeout_s
        label = self.h.label
        deadline = time.time() + timeout_s
        print(f"[helm] waiting for pods '{label}' in '{namespace}' (<={timeout_s}s)")
        while time.time() < deadline:
            pods = self.kube.core.list_namespaced_pod(
                namespace, label_selector=label).items
            if pods:
                def ready(p):
                    if p.status.phase not in ("Running", "Succeeded"):
                        return False
                    conds = p.status.conditions or []
                    return any(c.type == "Ready" and c.status == "True" for c in conds)
                if all(ready(p) for p in pods):
                    return
            time.sleep(10)
        raise TimeoutError(
            f"mysql-qa pods not Ready in '{namespace}' within {timeout_s}s")
