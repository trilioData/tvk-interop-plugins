"""
Kubernetes operations via the official `kubernetes` Python package — no CLI.

Connectivity:
  1. If cfg.cluster.kubeconfig is set -> kubernetes.config.load_kube_config()
  2. Otherwise (OCP) -> obtain an OAuth bearer token using username/password
     (same flow `oc login` uses) and build a client Configuration with it.

The API server URL is derived from the console URL:
  https://console-openshift-console.apps.<domain>  ->  https://api.<domain>:6443
"""
import re
import time
import urllib.parse

import requests
import urllib3
from kubernetes import client, config as kube_config
from kubernetes.client.rest import ApiException

from config.settings import FrameworkConfig

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class KubeClient:
    def __init__(self, cfg: FrameworkConfig):
        self.cfg = cfg
        self._connect()
        self.core = client.CoreV1Api(self.api_client)
        self.apps = client.AppsV1Api(self.api_client)
        self.custom = client.CustomObjectsApi(self.api_client)
        # TVK compiles Schedule Policies into CronJobs, so the batch API is
        # needed to inspect what a schedule actually registered.
        self.batch = client.BatchV1Api(self.api_client)

    def grant_anyuid(self, namespace: str):
        """Allow every SA in the namespace to run as the image's own UID.

        OpenShift gives each namespace a random UID range, which breaks images
        expecting a fixed user (official mongo/mariadb/redis, and the Bitnami
        charts). This patches the `anyuid` SCC directly instead of shelling out
        to `oc adm policy`, keeping kube operations CLI-free like the rest of
        this client. Safe to call repeatedly.
        """
        group = f"system:serviceaccounts:{namespace}"
        try:
            scc = self.custom.get_cluster_custom_object(
                "security.openshift.io", "v1", "securitycontextconstraints", "anyuid")
        except ApiException as e:
            print(f"[kube] anyuid SCC unavailable ({e.status}) — not OpenShift?")
            return
        groups = scc.get("groups") or []
        if group in groups:
            return
        self.custom.patch_cluster_custom_object(
            "security.openshift.io", "v1", "securitycontextconstraints", "anyuid",
            {"groups": groups + [group]})
        print(f"[kube] granted anyuid to {group}")

    # ---------- connectivity ----------

    @property
    def _cluster_domain(self) -> str:
        """apps.<domain> part from the console URL."""
        host = urllib.parse.urlparse(self.cfg.cluster.console_url).hostname
        # console-openshift-console.apps.<your-cluster>.staging... -> apps.<your-cluster>...
        m = re.search(r"\bapps\..*$", host)
        if not m:
            raise ValueError(f"Cannot derive cluster domain from console URL: {host}")
        return m.group(0)

    @property
    def api_server_url(self) -> str:
        domain = self._cluster_domain[len("apps."):]
        return f"https://api.{domain}:6443"

    def _get_ocp_token(self) -> str:
        """OAuth token via the openshift-challenging-client (what `oc login` does)."""
        oauth_url = (f"https://oauth-openshift.{self._cluster_domain}"
                     "/oauth/authorize?response_type=token&client_id=openshift-challenging-client")
        r = requests.get(
            oauth_url,
            auth=(self.cfg.cluster.username, self.cfg.cluster.password),
            headers={"X-CSRF-Token": "1"},
            verify=False,
            allow_redirects=False,
            timeout=30,
        )
        location = r.headers.get("Location", "")
        m = re.search(r"access_token=([^&]+)", location)
        if not m:
            raise RuntimeError(
                f"Failed to obtain OCP OAuth token (status {r.status_code}). "
                f"Check username/password and that {oauth_url} is reachable.")
        return urllib.parse.unquote(m.group(1))

    def _connect(self):
        if self.cfg.cluster.kubeconfig:
            kube_config.load_kube_config(config_file=self.cfg.cluster.kubeconfig)
            self.api_client = client.ApiClient()
            self._token = None
            return
        if self.cfg.cluster.cluster_type in ("master", "credentials_db") or not self.cfg.cluster.console_url:
            raise RuntimeError(
                "No kubeconfig set. cluster_type "
                f"'{self.cfg.cluster.cluster_type}' cannot derive an OpenShift "
                "API from the manager URL. Set cluster.kubeconfig (or --kubeconfig) "
                "to the managed cluster so app/helm/restore CR waits can run.")
        # Username/password -> bearer token (OCP)
        token = self._get_ocp_token()
        self._token = token
        conf = client.Configuration()
        conf.host = self.api_server_url
        conf.verify_ssl = False
        conf.api_key = {"authorization": f"Bearer {token}"}
        self.api_client = client.ApiClient(conf)
        print(f"[kube] Connected to {conf.host} as {self.cfg.cluster.username}")

    def write_kubeconfig(self, path: str) -> str:
        """Write a kubeconfig (token-based, insecure TLS) for CLI tools like
        helm/oc. If a kubeconfig was already configured, return that instead."""
        if self.cfg.cluster.kubeconfig:
            return self.cfg.cluster.kubeconfig
        kc = f"""apiVersion: v1
kind: Config
clusters:
- name: tvk
  cluster:
    server: {self.api_server_url}
    insecure-skip-tls-verify: true
contexts:
- name: tvk
  context:
    cluster: tvk
    user: tvk
    namespace: default
current-context: tvk
users:
- name: tvk
  user:
    token: {self._token}
"""
        with open(path, "w") as f:
            f.write(kc)
        print(f"[kube] wrote temp kubeconfig for CLI tools -> {path}")
        return path

    # ---------- namespaces ----------

    def create_namespace(self, name: str):
        try:
            self.core.create_namespace(client.V1Namespace(
                metadata=client.V1ObjectMeta(name=name)))
            print(f"[kube] Namespace '{name}' created")
        except ApiException as e:
            if e.status != 409:  # already exists is fine
                raise

    def delete_namespace(self, name: str):
        try:
            self.core.delete_namespace(name)
            print(f"[kube] Namespace '{name}' deletion requested")
        except ApiException as e:
            if e.status != 404:
                raise

    # ---------- demo app ----------

    def install_demo_app(self):
        """Deploy a small stateful demo app (nginx + PVC) via the API."""
        a = self.cfg.app
        self.create_namespace(a.namespace)

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name=f"{a.release_name}-data"),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=client.V1VolumeResourceRequirements(
                    requests={"storage": "1Gi"}),
            ),
        )
        try:
            self.core.create_namespaced_persistent_volume_claim(a.namespace, pvc)
        except ApiException as e:
            if e.status != 409:
                raise

        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=a.release_name, labels={"app": a.release_name}),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": a.release_name}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": a.release_name}),
                    spec=client.V1PodSpec(
                        containers=[client.V1Container(
                            name="web",
                            image="nginxinc/nginx-unprivileged:stable",
                            ports=[client.V1ContainerPort(container_port=8080)],
                            volume_mounts=[client.V1VolumeMount(
                                name="data", mount_path="/data")],
                        )],
                        volumes=[client.V1Volume(
                            name="data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=f"{a.release_name}-data"))],
                    ),
                ),
            ),
        )
        try:
            self.apps.create_namespaced_deployment(a.namespace, deployment)
            print(f"[kube] Deployment '{a.release_name}' created in '{a.namespace}'")
        except ApiException as e:
            if e.status != 409:
                raise

        self._wait_pods_running(a.namespace, timeout_s=600)

    def _wait_pods_running(self, namespace: str, timeout_s: int = 600):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.verify_app_running(namespace, quiet=True):
                return
            time.sleep(10)
        raise TimeoutError(f"Pods in '{namespace}' not Running within {timeout_s}s")

    def verify_app_running(self, namespace: str | None = None, quiet: bool = False) -> bool:
        ns = namespace or self.cfg.app.namespace
        pods = self.core.list_namespaced_pod(ns).items
        if not pods:
            if not quiet:
                print(f"[kube] No pods found in namespace '{ns}'")
            return False
        ok = all(p.status.phase in ("Running", "Succeeded") for p in pods)
        if not quiet:
            for p in pods:
                print(f"[kube] {ns}/{p.metadata.name}: {p.status.phase}")
        return ok

    # ---------- generic resource read ----------

    def get_deployment_replicas(self, name: str, namespace: str) -> int | None:
        try:
            d = self.apps.read_namespaced_deployment(name, namespace)
            return d.spec.replicas
        except ApiException:
            return None

    # ---------- Trilio custom resources ----------

    TVK_GROUP = "triliovault.trilio.io"

    def _tvk_version(self) -> str:
        """Served API version for the triliovault.trilio.io group."""
        try:
            apis = client.ApisApi(self.api_client)
            for g in apis.get_api_versions().groups:
                if g.name == self.TVK_GROUP:
                    return g.preferred_version.version
        except Exception:
            pass
        return "v1"

    @staticmethod
    def _cr_status(obj: dict) -> str:
        """Pull the phase string out of a TVK CR status block."""
        st = obj.get("status") or {}
        return str(st.get("status") or st.get("phase") or "").strip()

    def wait_for_backup(self, namespace: str, backup_name: str | None = None,
                        timeout_s: int = 2700, poll_s: int = 20) -> dict:
        """Poll the 'backups.triliovault.trilio.io' CR until it reaches
        Available/Completed, raising on Failed or timeout (default 45 min).

        If backup_name is given, that CR is tracked; otherwise the most
        recently created backup in the namespace is used. Returns the CR.
        """
        version = self._tvk_version()
        plural = "backups"
        done = {"available", "completed", "succeeded"}
        failed = {"failed", "error"}
        deadline = time.time() + timeout_s
        print(f"[kube] Polling {plural}.{self.TVK_GROUP}/{version} in '{namespace}' "
              f"(timeout {timeout_s}s) for backup "
              f"'{backup_name or '<latest>'}'...")

        while time.time() < deadline:
            try:
                resp = self.custom.list_namespaced_custom_object(
                    self.TVK_GROUP, version, namespace, plural)
                items = resp.get("items", [])
            except ApiException as e:
                print(f"[kube] list backups failed ({e.status}) — retrying")
                items = []

            target = None
            if backup_name:
                target = next((i for i in items
                               if i.get("metadata", {}).get("name") == backup_name), None)
            if target is None and items:
                target = sorted(
                    items,
                    key=lambda i: i.get("metadata", {}).get("creationTimestamp", ""))[-1]

            if target is not None:
                name = target.get("metadata", {}).get("name", "?")
                status = self._cr_status(target)
                remaining = int(deadline - time.time())
                print(f"[kube] backup '{name}' status={status or '<none>'} "
                      f"({remaining}s left)")
                if status.lower() in done:
                    print(f"[kube] backup '{name}' completed: {status}")
                    return target
                if status.lower() in failed:
                    raise AssertionError(f"Backup '{name}' failed with status '{status}'")
            else:
                print(f"[kube] no backups found in '{namespace}' yet — waiting")

            time.sleep(poll_s)

        raise TimeoutError(
            f"Backup '{backup_name or '<latest>'}' in '{namespace}' did not "
            f"complete within {timeout_s}s")

    def delete_custom(self, plural: str, name: str, namespace: str):
        """Delete a namespaced TVK custom resource (ignore-not-found)."""
        version = self._tvk_version()
        try:
            self.custom.delete_namespaced_custom_object(
                self.TVK_GROUP, version, namespace, plural, name)
            print(f"[cleanup] deleted {plural}/{name} in '{namespace}'")
        except ApiException as e:
            if e.status == 404:
                print(f"[cleanup] {plural}/{name} not found in '{namespace}' — skip")
            else:
                print(f"[cleanup] delete {plural}/{name} failed ({e.status})")

    def delete_secret(self, name: str, namespace: str):
        try:
            self.core.delete_namespaced_secret(name, namespace)
            print(f"[cleanup] deleted secret/{name} in '{namespace}'")
        except ApiException as e:
            if e.status != 404:
                print(f"[cleanup] delete secret/{name} failed ({e.status})")

    def cleanup_resources(self, cfg):
        """Delete everything created in the run: restore, backup, backup plan,
        policy, target, secret, and the app + restore namespaces. Order:
        dependents first (restore/backup) then parents (plan/target)."""
        app_ns = cfg.res_ns(cfg.backup_namespace)
        restore_ns = cfg.restore_ns()
        print("[cleanup] removing run resources...")

        # restore lives in/around the restore namespace; try both namespaces
        for ns in {restore_ns, app_ns}:
            self.delete_custom("restores", cfg.restore_name, ns)
        self.delete_custom("backups", cfg.backup_name, app_ns)
        self.delete_custom("backupplans", cfg.backupplan_name, app_ns)
        self.delete_custom("policies", cfg.policy_name, cfg.res_ns(cfg.policy_namespace))
        self.delete_custom("targets", cfg.target.name, app_ns)
        self.delete_secret(f"{cfg.target.name}-secret", app_ns)

        # finally the namespaces (only the ones this framework creates)
        for ns in (restore_ns, cfg.app.namespace):
            self.delete_namespace(ns)

    def wait_for_restore(self, restore_name: str | None = None,
                         namespace: str | None = None,
                         timeout_s: int = 2700, poll_s: int = 20) -> dict:
        """Poll the 'restores.triliovault.trilio.io' CR until it reaches
        Completed/Available, raising on Failed or timeout (default 45 min).

        Searches cluster-wide (restores can land in different namespaces); if
        namespace is given it is searched first. Tracks restore_name if given,
        else the most recently created restore. Returns the CR.
        """
        version = self._tvk_version()
        plural = "restores"
        done = {"completed", "available", "succeeded"}
        failed = {"failed", "error"}
        deadline = time.time() + timeout_s
        print(f"[kube] Polling {plural}.{self.TVK_GROUP}/{version} (timeout "
              f"{timeout_s}s) for restore '{restore_name or '<latest>'}'...")

        while time.time() < deadline:
            items = []
            try:
                if namespace:
                    resp = self.custom.list_namespaced_custom_object(
                        self.TVK_GROUP, version, namespace, plural)
                    items = resp.get("items", [])
                if not items:
                    resp = self.custom.list_cluster_custom_object(
                        self.TVK_GROUP, version, plural)
                    items = resp.get("items", [])
            except ApiException as e:
                print(f"[kube] list restores failed ({e.status}) — retrying")

            target = None
            if restore_name:
                target = next((i for i in items
                               if i.get("metadata", {}).get("name") == restore_name), None)
            if target is None and items:
                target = sorted(
                    items,
                    key=lambda i: i.get("metadata", {}).get("creationTimestamp", ""))[-1]

            if target is not None:
                name = target.get("metadata", {}).get("name", "?")
                status = self._cr_status(target)
                remaining = int(deadline - time.time())
                print(f"[kube] restore '{name}' status={status or '<none>'} "
                      f"({remaining}s left)")
                if status.lower() in done:
                    print(f"[kube] restore '{name}' completed: {status}")
                    return target
                if status.lower() in failed:
                    raise AssertionError(f"Restore '{name}' failed with status '{status}'")
            else:
                print("[kube] no restores found yet — waiting")

            time.sleep(poll_s)

        raise TimeoutError(
            f"Restore '{restore_name or '<latest>'}' did not complete within {timeout_s}s")
