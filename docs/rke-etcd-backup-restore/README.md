# RKE ETCD BACKUP RESTORE

## Introduction to ETCD
Etcd is the persistent data store for Kubernetes. It is a distributed key-value store that records the state of all resources in a Kubernetes cluster.
Etcd is a distributed reliable key-value store which is simple, fast and secure. 
It acts like a backend service discovery and database, runs on different servers in Kubernetes clusters at the 
same time to monitor changes in clusters and to store state/configuration data that should to be accessed by a Kubernetes master or clusters.

## Backups and Disaster Recovery of RKE cluster:

RKE clusters can be configured to take snapshots of etcd. In a disaster scenario, you can restore these snapshots.
This snapshots can be shared outside cluster like s3 storage so that in case if we loose server, we will have backups to restore.

## ETCD backup and restore using rke-etcd-backup-restore

The plugin helps user to perform ETCD backup and restore of RKE1 clusters. This plugin allows user to store the snapshot on s3 storage created using TVK target.

### Important Notes for the plugin:
1. Please do not switch of any node in cluster while restore is in progress and do not abort restore task in between, else you may loose cluster accessibility**
2. Restore functionality will only work on same cluster from where the backup was taken**
3. Restore will only work if cluster is accessible and one of the etcd nodes in the cluster should be up and running.
4. Plugin is supported on RKE1 cluster(Local cluster created on Rancher server is not supported)

### Pre-reqs:
1. krew - kubectl-plugin manager. Install from [here](https://krew.sigs.k8s.io/docs/user-guide/setup/install/)
2. kubectl - kubernetes command-line tool. Install from [here](https://kubernetes.io/docs/tasks/tools/install-kubectl/)
3. Triliovault for kubernetes and TVK target. Install from [here](https://docs.trilio.io/kubernetes/use-triliovault/installing-triliovault)

## Installation, Upgrade, Removal of Plugins :

#### 1. With `krew`:

- Add TVK custom plugin index of krew:

  ```
  kubectl krew index add tvk-interop-plugin https://github.com/trilioData/tvk-interop-plugins.git
  ```

- Installation:

  ```
  kubectl krew install tvk-interop-plugin/rke-etcd-backup-restore
  ```

- Upgrade:

  ```
  kubectl krew upgrade rke-etcd-backup-restore
  ```

- Removal:

  ```
  kubectl krew uninstall rke-etcd-backup-restore
  ```
#### 2. Without `krew`:
1. List of available releases: https://github.com/trilioData/tvk-interop-plugins/releases
2. Choose a version of preflight plugin to install and check if release assets have preflight plugin's package[rke-etcd-backup-restore-${OS}.tar.gz]
  - To check OS & Architecture, execute command uname -a on linux/macOS
3. Set env variable `TVK_RKE_ETCD_BACKUP_RESTORE_VERSION=v1.x.x` [update with your desired version]. If `TVK_RKE_ETCD_BACKUP_RESTORE_VERSION` is not exported, `latest` tagged version
   will be considered.

###### Linux/macOS

- Bash or ZSH shells
```bash
(
  set -ex; cd "$(mktemp -d)" &&
  OS="$(uname)" &&
  if [[ -z ${TVK_RKE_ETCD_BACKUP_RESTORE_VERSION} ]]; then version=$(curl -s https://api.github.com/repos/trilioData/tvk-interop-plugins/releases/ | grep -oP '"tag_name": "\K(.*)(?=")'); fi &&
  echo "Installing version=${TVK_RKE_ETCD_BACKUP_RESTORE_VERSION}" &&
  package_name="rke-etcd-backup-restore-${OS}.tar.gz" &&
  curl -fsSLO "https://github.com/trilioData/tvk-interop-plugins/releases/download/"${TVK_RKE_ETCD_BACKUP_RESTORE_VERSION}"/${package_name}" &&
  tar zxvf ${package_name} && sudo mv rke-etcd-backup-restore /usr/local/bin/kubectl-rke_etcd_backup_restore
)
```
Verify installation with `kubectl rke-etcd-backup-restore --help`

## Usage

    ETCD Backup and restore on Rancher cluster. Available flags: -backup -restore.
       [-h] [-backup] [-restore] [--target-name TARGET_NAME]
       [--target-namespace TARGET_NAMESPACE] --rancher-url RANCHER_URL
       --bearer-token BEARER_TOKEN --cluster-name CLUSTER_NAME
       [--log-location LOG_LOC]

#### Arguments/Falgs:

| Parameter                     | Description
| :---------------------------- |:-------------:
| -backup                       | Flag to notify backup is to be taken.
| -restore                      | Falg to notify restore is to be performed.
| --target-name                 | The name of a single datastore on which etcd backup needs to be stored i.e. TVK target name.
| --target-namespace            | Namespace name in which TVK target is created.
| --rancher-url                 | Rancher server URL
| --bearer-token                | Token to access rancher server [More info here](https://rancher.com/docs/rancher/v2.5/en/user-settings/api-keys/)
| --cluster-name                | Cluster name to perform Backup/Restore on.
| --log-location                | Log file name along with path where the logs should be save default - /tmp/etcd-ocp-backup.log


#### Arguments details:

- **-backup**:
		Flag to notify the plugin to perform backup.
- **-restore**:
		Flag to notify the plugin to perform restore.
- **--target-name**:
		TVK target name.The target should be created and in available state.
		Currently S3 target type is supported. This target should be the target where the backups
		should be stored.
		This argument is mandatory if -backup flag is provided.
- **--target-namespace**:
		Namespace name in which TVK target resides.
		This argument is mandatory if -backup flag is provided.
- **--rancher-url**:
		This is the rancher server URL through which rancher can be accessed.
		should be given in the below form:  
		"https://\<rancher server ip\>/"  
                This is the URL to access rancher server.
		This is mandatory argument.
- **--bearer-token**:
		This is the token provided by rancher server to access its cluster/apis without using password.
		More info about how to get bearer-token can be found at https://rancher.com/docs/rancher/v2.5/en/user-settings/api-keys/
                The scope of API key should be "No scope" as to access API's, plugin needs access to complete scope of Rancher server
		This is mandatory argument.
- **--cluster-name**:
		Rancher server hosts many RKE cluster, so specify the one cluster name for which ETCD backup is to be taken.
		This is mandatory argument.
- **--log-location**:
		specify the log file location. default: /tmp/etcd-ocp-backup.log

#### Example:
 
 kubectl rke-etcd-backup-restore -backup --target-name <target name> --target-namespace <Target namespace> --rancher-url <https://rancher server ip/> --bearer-token <bearer_token> --cluster-name <cluster_name>

 kubectl rke-etcd-backup-restore -restore --rancher-url <https://rancher server ip/> --bearer-token <bearer_token> --cluster-name <cluster_name>

