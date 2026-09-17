"""
Central configuration for the Trilio test framework.

All values can be overridden via CLI arguments (see conftest.py) or a YAML
config file passed with --config-file. This keeps the framework portable
across clusters (OCP, vanilla K8s, EKS, GKE, AKS, Rancher...).
"""
import os
from dataclasses import dataclass, field


@dataclass
class ClusterConfig:
    # Type of cluster: 'ocp' today; add 'vanilla', 'eks', 'gke', 'aks' later.
    cluster_type: str = "ocp"
    console_url: str = "https://console-openshift-console.apps.<your-cluster>"
    trilio_url: str = "https://trilio-system.apps.<your-cluster>/#/login"
    username: str = "kubeadmin"
    password: str = ""
    # kubeconfig path for CLI-level operations (app install, verification)
    kubeconfig: str = os.environ.get("KUBECONFIG", "")
    # credentials.db for cluster_type=master (https://master.k8strilio.net/).
    # Relative paths are resolved from the TVK-UI-Framework root.
    credentials_db: str = os.environ.get("TVK_CREDENTIALS_DB", "")


@dataclass
class TargetConfig:
    """Backup target (object store / NFS) details."""
    name: str = "auto-target"
    # Which target to create: 'objectstore' (S3/object store) or 'nfs'
    type: str = "objectstore"   # objectstore | s3 | nfs
    vendor: str = "AWS"         # ObjectStore vendor: AWS (default) | Ceph | MinIO | ...
    s3_url: str = "https://s3.amazonaws.com"
    bucket: str = ""
    region: str = "us-east-1"
    access_key: str = os.environ.get("TVK_S3_ACCESS_KEY", "")
    secret_key: str = os.environ.get("TVK_S3_SECRET_KEY", "")
    nfs_path: str = ""          # e.g. nfs-server:/exports/tvk
    threshold_capacity: str = "10Gi"
    # Namespace to create the target in. Leave empty to use the app namespace
    # (integrated runs). Set for standalone target runs. No suffix appended.
    namespace: str = ""
    # Turn ON 'Enable Browsing' during target creation (needed for restore
    # transforms). Default False. The helm_transform test forces this True
    # regardless of the config value.
    enable_browsing: bool = False


@dataclass
class TestAppConfig:
    """Demo application installed for backup/restore testing."""
    namespace: str = "tvk-test-app"
    helm_chart: str = "bitnami/mysql"          # any helm chart
    helm_repo_name: str = "bitnami"
    helm_repo_url: str = "https://charts.bitnami.com/bitnami"
    release_name: str = "tvk-demo-app"
    # Fallback: raw manifest to apply if helm is unavailable
    manifest_url: str = "https://k8s.io/examples/application/deployment.yaml"


@dataclass
class HelmAppConfig:
    """MySQL helm chart used for Helm-transformation tests (mirrors the shell
    install). Installed via the helm CLI; readiness checked via the K8s API."""
    release_name: str = "mysql-qa"
    chart: str = "stable/mysql"
    repo_name: str = "stable"
    repo_url: str = "https://charts.helm.sh/stable"
    image: str = "us-central1-docker.pkg.dev/tvk-solutions-330321/tvk-interop/mysql"
    image_tag: str = "latest"
    pull_policy: str = "IfNotPresent"
    busybox_image: str = "us-central1-docker.pkg.dev/tvk-solutions-330321/tvk-interop/busybox"
    busybox_tag: str = "1.32"
    label: str = "app=mysql-qa"     # pod label & backup-plan custom selector
    if_exists_proceed: bool = True   # proceed if release already present
    # Path to the helm binary. Empty = auto-detect (PATH, then ~/.local/bin).
    helm_bin: str = ""
    # Apply anyuid SCC + cluster-admin to the namespace's SAs. This needs
    # cluster-admin ('oc adm policy ...'); leave False to install without it.
    openshift: bool = False
    ready_timeout_s: int = 1200      # wait up to 20 min for pods Ready


@dataclass
class CassandraAppConfig:
    """Cassandra operator + datacenter used by the standalone cassandra flow.
    Install applies the YAMLs in utils/cassandra/; data seed runs
    insert-verify-data-500MB.sh. Namespace is NOT auto-suffixed."""
    namespace: str = "cass-oper-ns"
    operator_namespace: str = "openshift-operators"
    dc_name: str = "dc1"
    cluster_name: str = "cassandra"
    storage_class: str = ""          # empty = cluster default StorageClass
    operator_name: str = "cass-operator"
    pull_secret_name: str = "dockerhub-pull"
    # Seed size for insert-verify-data-500MB.sh (override for a faster dry run).
    target_size_mb: int = 500
    payload_size_bytes: int = 262144
    if_exists_proceed: bool = True
    openshift: bool = True          # grant anyuid + apply OLM subscription
    ready_timeout_s: int = 1200     # operator CSV + CassandraDatacenter
    insert_timeout_s: int = 3600


@dataclass
class FrameworkConfig:
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    target: TargetConfig = field(default_factory=TargetConfig)
    app: TestAppConfig = field(default_factory=TestAppConfig)
    helm_app: HelmAppConfig = field(default_factory=HelmAppConfig)
    cassandra: CassandraAppConfig = field(default_factory=CassandraAppConfig)
    backupplan_name: str = "auto-backupplan"
    # Namespace the backup plan should protect. Leave empty to use the
    # auto-created demo-app namespace; set it (in the YAML) to an EXISTING
    # namespace on the cluster when running the backup-plan test on its own.
    # NOTE: no random suffix is appended to this value.
    backup_namespace: str = ""
    # Existing target / scheduling policy to use in the backup plan when the
    # auto-created ones aren't present (e.g. running the backup-plan test
    # standalone). Leave empty to use the auto-created resources. No suffix
    # is appended to these values.
    backup_target: str = ""
    backup_scheduling_policy: str = ""
    # Backup plan to trigger a backup from. Leave empty to use the plan
    # created in this run; set to an EXISTING plan name for standalone runs.
    backup_from_plan: str = ""
    # Backup to check the status of in the UI. Leave empty to use the backup
    # created in this run; set to an EXISTING backup name for standalone runs.
    backup_check_name: str = ""
    # What the backup plan should capture inside the namespace:
    #   "namespace" -> entire namespace (default, works for our demo app)
    #   "helm"      -> a specific Helm release (set backup_helm_release)
    backup_component: str = "namespace"
    backup_helm_release: str = ""
    backup_name: str = "auto-backup"
    restore_name: str = "auto-restore"
    restore_namespace: str = "tvk-restore-ns"
    # ----- Restore transformation (applies to Helm / Custom backups only) -----
    transform_enabled: bool = False
    transform_type: str = ""          # "helm" | "custom"
    transform_name: str = "auto-transform"   # name given to the transform
    # Helm transform: full modified chart-values YAML pasted into the editor
    # (Restore Flags -> enable transform -> Transform Name -> values editor)
    transform_helm_values: str = ""
    # (legacy single key:value, kept for reference)
    transform_helm_key: str = ""
    transform_helm_value: str = ""
    # Optional post-restore verification of a deployment field changed by the
    # transform: e.g. resource 'tvk-demo' field replicas == expected.
    transform_verify_kind: str = ""       # e.g. "Deployment"
    transform_verify_name: str = ""       # resource name in restore namespace
    transform_verify_jsonpath: str = ""   # informational
    transform_verify_expected: str = ""
    # Custom transform: GVKO + operation + JSON-patch-style path + value
    transform_cr_group: str = ""      # e.g. "apps"
    transform_cr_version: str = ""    # e.g. "v1"
    transform_cr_kind: str = ""       # e.g. "Deployment"
    transform_cr_object: str = ""     # e.g. the resource name
    transform_operation: str = "Replace"  # Replace | Move | Remove | Add
    transform_path: str = ""          # e.g. "/spec/replicas"
    transform_value: str = ""         # e.g. "2"
    # Plan to restore from (its latest backup). Leave empty to use this run's
    # plan; set to an EXISTING plan for standalone restore runs.
    restore_from_plan: str = ""
    # Namespace to select in the restore wizard. Leave empty to pick the first
    # available option. No suffix is appended.
    restore_target_namespace: str = ""
    # Restore to check the status of in the UI. Leave empty to use the restore
    # created in this run; set to an EXISTING restore name for standalone runs.
    restore_check_name: str = ""
    policy_name: str = "auto-retention-policy"
    # Namespace to create the scheduling policy in. Leave empty to use the
    # same namespace as the other resources (app namespace, or backup_namespace
    # if set). Set explicitly for standalone policy runs. No suffix appended.
    policy_namespace: str = ""
    # If True, the cleanup test deletes the resources created in this run
    # (target, policy, backup plan, backup, restore, secret, namespaces).
    # If False, cleanup is skipped so the resources remain for inspection.
    cleanup_enabled: bool = False
    run_suffix: str = ""  # set per run in conftest: 3 random chars
    # Namespace the TVK control plane runs in. The feature-integration suite
    # keeps its shared Target and Policies here and references them across
    # namespaces, so one target serves every BackupPlan.
    tvk_namespace: str = "trilio-system"
    # Set True by the app-install step. When True (integrated run) every
    # resource is created in the app namespace and config namespace overrides
    # are IGNORED. When False (standalone) the config override is honored.
    app_installed: bool = False

    def res_ns(self, override: str = "") -> str:
        """Namespace for a created resource (target/policy/backupplan/backup).
        Integrated -> always the app namespace; standalone -> the config
        override (falling back to the app namespace)."""
        if self.app_installed:
            return self.app.namespace
        return override or self.app.namespace

    def restore_ns(self) -> str:
        """Restore target namespace: aligned with the backup namespace + '-ret'.
        Standalone honors restore_target_namespace if set."""
        if not self.app_installed and self.restore_target_namespace:
            return self.restore_target_namespace
        return f"{self.res_ns(self.backup_namespace)}-ret"
    screenshot_dir: str = "screenshots"
    default_timeout_ms: int = 60_000
    operation_timeout_s: int = 3600  # backups/restores can be slow (up to 1h)
