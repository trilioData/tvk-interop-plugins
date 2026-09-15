"""
Customer-representative apps for feature testing, plus data-integrity checks.

The apps are declared as plain manifests rather than Helm charts so the tests
don't depend on chart availability or registry mirrors — Bitnami's registry
changes have broken chart installs on this cluster before. The one genuine Helm
release needed for Helm-based backup comes from the existing utils.HelmApp.

Data integrity is the point of this module. Every app is seeded with known
marker rows before backup; after restore the same query runs again and the
results must match exactly. A restore that "completes" while silently losing
rows is the failure this is designed to catch.
"""
import time

from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

CEPH_RBD = "ocs-storagecluster-ceph-rbd"


class FeatureApps:
    def __init__(self, kube):
        self.kube = kube
        self.core = kube.core
        self.apps = kube.apps

    # ---------- exec ----------

    def pod_name(self, namespace: str, label: str) -> str:
        pods = self.core.list_namespaced_pod(namespace, label_selector=label).items
        running = [p for p in pods if p.status.phase == "Running"]
        if not running:
            raise AssertionError(f"no Running pod for {label} in {namespace}")
        return running[0].metadata.name

    def exec(self, namespace: str, pod: str, argv: list[str], timeout_s: int = 120) -> str:
        return stream(
            self.core.connect_get_namespaced_pod_exec,
            pod, namespace, command=argv,
            stderr=True, stdin=False, stdout=True, tty=False,
            _request_timeout=timeout_s,
        )

    def exec_sh(self, namespace: str, label: str, script: str, timeout_s: int = 120) -> str:
        return self.exec(namespace, self.pod_name(namespace, label),
                         ["sh", "-c", script], timeout_s)

    # ---------- waiting ----------

    def wait_ready(self, namespace: str, expected: int, timeout_s: int = 900):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            pods = self.core.list_namespaced_pod(namespace).items
            ready = [p for p in pods
                     if p.status.phase == "Running"
                     and p.status.container_statuses
                     and all(c.ready for c in p.status.container_statuses)]
            if len(ready) >= expected:
                print(f"[apps] {namespace}: {len(ready)}/{expected} pods ready")
                return
            time.sleep(10)
        raise TimeoutError(f"{namespace}: only {len(ready)}/{expected} pods ready "
                           f"after {timeout_s}s")

    # ---------- deployment ----------

    def _apply(self, fn, *args):
        """Create, tolerating an existing object so reruns are idempotent."""
        try:
            return fn(*args)
        except ApiException as e:
            if e.status == 409:
                return None
            raise

    def deploy_mongodb(self, namespace: str, labels: dict):
        """StatefulSet + headless Service. Labels go on every object so a
        label-based BackupPlan selects the whole app including its PVC."""
        self._apply(self.core.create_namespaced_service, namespace, {
            "apiVersion": "v1", "kind": "Service",
            "metadata": {"name": "mongodb", "namespace": namespace, "labels": labels},
            "spec": {"clusterIP": "None", "selector": {"app": "mongodb"},
                     "ports": [{"port": 27017, "name": "mongo"}]},
        })
        self._apply(self.apps.create_namespaced_stateful_set, namespace, {
            "apiVersion": "apps/v1", "kind": "StatefulSet",
            "metadata": {"name": "mongodb", "namespace": namespace, "labels": labels},
            "spec": {
                "serviceName": "mongodb", "replicas": 1,
                "selector": {"matchLabels": {"app": "mongodb"}},
                "template": {
                    "metadata": {"labels": {**labels, "app": "mongodb"}},
                    "spec": {"containers": [{
                        "name": "mongodb", "image": "docker.io/library/mongo:7",
                        "ports": [{"containerPort": 27017}],
                        "env": [{"name": "MONGO_INITDB_ROOT_USERNAME", "value": "trilio"},
                                {"name": "MONGO_INITDB_ROOT_PASSWORD", "value": "trilio123"}],
                        "volumeMounts": [{"name": "data", "mountPath": "/data/db"}],
                    }]},
                },
                "volumeClaimTemplates": [{
                    "metadata": {"name": "data", "labels": labels},
                    "spec": {"accessModes": ["ReadWriteOnce"],
                             "storageClassName": CEPH_RBD,
                             "resources": {"requests": {"storage": "3Gi"}}},
                }],
            },
        })

    def deploy_suite(self, namespace: str):
        """Multi-component app: MariaDB (StatefulSet) + Redis (Deployment) plus a
        ConfigMap and Secret, so a namespace backup has metadata worth checking."""
        self._apply(self.core.create_namespaced_config_map, namespace, {
            "apiVersion": "v1", "kind": "ConfigMap",
            "metadata": {"name": "suite-config", "namespace": namespace},
            "data": {"app.name": "order-service", "app.tier": "production",
                     "retention.days": "30"},
        })
        self._apply(self.core.create_namespaced_secret, namespace, {
            "apiVersion": "v1", "kind": "Secret",
            "metadata": {"name": "suite-secret", "namespace": namespace},
            "type": "Opaque",
            "stringData": {"db-password": "trilio123", "api-token": "ft-token-9a3f"},
        })
        self._apply(self.core.create_namespaced_service, namespace, {
            "apiVersion": "v1", "kind": "Service",
            "metadata": {"name": "mariadb", "namespace": namespace},
            "spec": {"selector": {"app": "mariadb"}, "ports": [{"port": 3306}]},
        })
        self._apply(self.apps.create_namespaced_stateful_set, namespace, {
            "apiVersion": "apps/v1", "kind": "StatefulSet",
            "metadata": {"name": "mariadb", "namespace": namespace},
            "spec": {
                "serviceName": "mariadb", "replicas": 1,
                "selector": {"matchLabels": {"app": "mariadb"}},
                "template": {
                    "metadata": {"labels": {"app": "mariadb"}},
                    "spec": {"containers": [{
                        "name": "mariadb", "image": "docker.io/library/mariadb:11",
                        "ports": [{"containerPort": 3306}],
                        "env": [
                            {"name": "MARIADB_ROOT_PASSWORD",
                             "valueFrom": {"secretKeyRef": {"name": "suite-secret",
                                                            "key": "db-password"}}},
                            {"name": "MARIADB_DATABASE", "value": "orders"}],
                        "volumeMounts": [{"name": "data", "mountPath": "/var/lib/mysql"}],
                    }]},
                },
                "volumeClaimTemplates": [{
                    "metadata": {"name": "data"},
                    "spec": {"accessModes": ["ReadWriteOnce"],
                             "storageClassName": CEPH_RBD,
                             "resources": {"requests": {"storage": "3Gi"}}},
                }],
            },
        })
        self._apply(self.core.create_namespaced_persistent_volume_claim, namespace, {
            "apiVersion": "v1", "kind": "PersistentVolumeClaim",
            "metadata": {"name": "redis-data", "namespace": namespace,
                         "labels": {"ft-sched": "redis"}},
            "spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": CEPH_RBD,
                     "resources": {"requests": {"storage": "2Gi"}}},
        })
        self._apply(self.core.create_namespaced_service, namespace, {
            "apiVersion": "v1", "kind": "Service",
            "metadata": {"name": "redis", "namespace": namespace},
            "spec": {"selector": {"app": "redis"}, "ports": [{"port": 6379}]},
        })
        self._apply(self.apps.create_namespaced_deployment, namespace, {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": "redis", "namespace": namespace,
                         "labels": {"ft-sched": "redis"}},
            "spec": {
                "replicas": 1, "selector": {"matchLabels": {"app": "redis"}},
                "template": {
                    "metadata": {"labels": {"app": "redis", "ft-sched": "redis"}},
                    "spec": {
                        "containers": [{
                            "name": "redis", "image": "docker.io/library/redis:7-alpine",
                            "args": ["redis-server", "--appendonly", "yes", "--dir", "/data"],
                            "ports": [{"containerPort": 6379}],
                            "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}},
                            "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                        }],
                        "volumes": [{"name": "data",
                                     "persistentVolumeClaim": {"claimName": "redis-data"}}],
                    },
                },
            },
        })

    # ---------- seed + verify ----------
    # Each verify_* returns a comparable fingerprint; the tests assert equality
    # against the value captured before the backup.

    def seed_mongo(self, namespace: str, docs: int = 500):
        self.exec_sh(namespace, "app=mongodb",
                     f"mongosh -u trilio -p trilio123 --quiet --eval \""
                     f"db=db.getSiblingDB('ftdb');"
                     f"db.ft_marker.deleteMany({{}});"
                     f"for(let i=1;i<={docs};i++){{db.ft_marker.insertOne({{idx:i,note:'ft-doc-'+i}})}}\"",
                     timeout_s=300)

    def verify_mongo(self, namespace: str) -> str:
        out = self.exec_sh(namespace, "app=mongodb",
                           "mongosh -u trilio -p trilio123 --quiet --eval \""
                           "db=db.getSiblingDB('ftdb');"
                           "print(db.ft_marker.countDocuments()+'|'+db.ft_marker.findOne({idx:250}).note)\"",
                           timeout_s=180)
        return out.strip().splitlines()[-1].strip()

    def seed_mariadb(self, namespace: str):
        self.exec_sh(namespace, "app=mariadb",
                     "mariadb -uroot -ptrilio123 orders -e \""
                     "CREATE TABLE IF NOT EXISTS ft_marker(id INT AUTO_INCREMENT PRIMARY KEY,"
                     " note VARCHAR(64)); DELETE FROM ft_marker;"
                     " INSERT INTO ft_marker(note) VALUES('ft-a'),('ft-b'),('ft-c'),('ft-d'),('ft-e');\"",
                     timeout_s=180)

    def verify_mariadb(self, namespace: str) -> str:
        out = self.exec_sh(namespace, "app=mariadb",
                           "mariadb -uroot -ptrilio123 orders -N -B -e \""
                           "SELECT CONCAT(COUNT(*),'|',MD5(GROUP_CONCAT(note ORDER BY id)))"
                           " FROM ft_marker;\"",
                           timeout_s=180)
        return out.strip().splitlines()[-1].strip()

    def seed_redis(self, namespace: str):
        self.exec_sh(namespace, "app=redis",
                     "redis-cli MSET ft:k1 ft-val-1 ft:k2 ft-val-2 ft:k3 ft-val-3 "
                     "&& redis-cli BGSAVE", timeout_s=120)
        time.sleep(3)  # let BGSAVE reach the PVC before a backup snapshots it

    def verify_redis(self, namespace: str) -> str:
        out = self.exec_sh(namespace, "app=redis",
                           "echo \"$(redis-cli DBSIZE)|$(redis-cli GET ft:k1)\"",
                           timeout_s=120)
        return out.strip().splitlines()[-1].strip()

    def seed_mysql(self, namespace: str, label: str, rows: int = 200):
        """For the Helm release (stable/mysql via the interop mirror)."""
        self.exec_sh(namespace, label,
                     "mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" my-database -e \""
                     "CREATE TABLE IF NOT EXISTS ft_marker(id INT AUTO_INCREMENT PRIMARY KEY,"
                     " note VARCHAR(64)); DELETE FROM ft_marker;\" && "
                     f"for i in $(seq 1 {rows}); do echo \"INSERT INTO ft_marker(note) "
                     "VALUES('ft-row-$i');\"; done | "
                     "mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" my-database",
                     timeout_s=300)

    def verify_mysql(self, namespace: str, label: str) -> str:
        out = self.exec_sh(namespace, label,
                           "mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" my-database -N -B -e \""
                           "SELECT CONCAT(COUNT(*),'|',MD5(GROUP_CONCAT(note ORDER BY id)))"
                           " FROM ft_marker;\"",
                           timeout_s=180)
        return out.strip().splitlines()[-1].strip()

    # ---------- misc ----------

    def configmap_data(self, namespace: str, name: str) -> dict:
        return self.core.read_namespaced_config_map(name, namespace).data or {}

    def secret_value(self, namespace: str, name: str, key: str) -> str:
        import base64
        data = self.core.read_namespaced_secret(name, namespace).data or {}
        return base64.b64decode(data.get(key, "")).decode()

    def statefulset_image(self, namespace: str, name: str) -> str:
        sts = self.apps.read_namespaced_stateful_set(name, namespace)
        return sts.spec.template.spec.containers[0].image

    def statefulset_labels(self, namespace: str, name: str) -> dict:
        return self.apps.read_namespaced_stateful_set(name, namespace).metadata.labels or {}
