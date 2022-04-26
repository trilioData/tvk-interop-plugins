# RKE ETCD BACKUP RESTORE

## Introduction to ETCD
ETCD is the persistent data store for Kubernetes. It is a distributed key-value store that records the state of all resources in a Kubernetes cluster and it is simple, fast and secure. It acts like a backend service discovery and database. It runs on different servers in Kubernetes clusters at the same time, which enables it to monitor changes in clusters and store state/configuration data that are to be accessed by a Kubernetes master or clusters.

## Backups and Disaster Recovery of RKE cluster:

RKE clusters can be configured to take snapshots of ETCD, which can later be used to retore from, in the event of a disaster scenario. These snapshots can be shared outside a cluster like in S3 storage, so that if the server is lost, it is still possible to perform a restore.

## ETCD backup and restore using rke-etcd-backup-restore

The rke-etcd-backup-restore plugin helps the user to perform ETCD backup and restore of RKE clusters, by enabling the user to store the snapshot on S3 storage created using a TVK target. Some important considerations for the plugin:
* No node in the cluster should be switched off while restore is in progress.
* Never abort a restore task while it is in progress, or you may loose cluster accessibility.
* Restore functionality only works on the same cluster from where the backup was taken
* Restore only works if firstly, the cluster is accessible and secondly, if one of the ETCD nodes in the cluster is up and running.

## Pre-reqs:
1. krew - kubectl-plugin manager. Install from [here](https://krew.sigs.k8s.io/docs/user-guide/setup/install/).
2. kubectl - kubernetes command-line tool. Install from [here](https://kubernetes.io/docs/tasks/tools/install-kubectl/).
3. Triliovault for kubernetes and TVK target. Install from [here](https://docs.trilio.io/kubernetes/use-triliovault/installing-triliovault).

## Installation, Upgrade, Removal of Plugins

### Using krew

| Action                                  | Command                                                                                           |
| --------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Add the TVK custom plugin index of krew | `kubectl krew index add tvk-interop-plugin` https://github.com/trilioData/tvk-interop-plugins.git |
| Perform the installation                | `kubectl krew install tvk-interop-plugin/rke-etcd-backup-restore`                                          |
| Upgrade the plugin                      | `kubectl krew upgrade rke-etcd-backup-restore`                                                             |
| Uninstall the plugin                    | `kubectl krew uninstall rke-etcd-backup-restore`                                                           |

### Without krew
If the krew plugin manager is not an option, you may still install the rke-etcd-backup-restore plugin without krew using the following steps:

1. List of available releases: https://github.com/trilioData/tvk-interop-plugins/releases
2. Choose a version of preflight plugin to install and check if release assets have preflight plugin's package[rke-etcd-backup-restore-${OS}.tar.gz]. To check your operating system and architecture, execute command `uname -a` on your linux/macOS.
3. Set env variable `TVK_RKE_ETCD_BACKUP_RESTORE_VERSION=[INSERT VERSION HERE]`. If `TVK_RKE_ETCD_BACKUP_RESTORE_VERSION` is not exported, the `latest` tagged version is considered.
4. Run this Bash or ZSH shells command to download and install the rke-etcd-backup-restore plugin without krew:

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
5. Verify installation using the command: `kubectl rke-etcd-backup-restore --help`

## Usage

    ETCD Backup and restore on Rancher cluster. Available flags: -backup -restore.
       [-h] [-backup] [-restore] [--target-name TARGET_NAME]
       [--target-namespace TARGET_NAMESPACE] --rancher-url RANCHER_URL
       --bearer-token BEARER_TOKEN --cluster-name CLUSTER_NAME
       [--log-location LOG_LOC]

Arguments/Flags:

| Flag                          | Details
| :---------------------------- |:-------------
| -backup                       | Flag to notify the plugin to perform a backup.
| -restore                      | Flag to notify the plugin to perform a restore.
| --target-name                 | The name of a single datastore on which ETCD backup is to be stored. The target should be created in same namespace in which TVK resides and it should be available. This argument is mandatory if -backup flag is provided.
| --target-namespace            | Namespace name where the target resides or TVK is installed. This argument is mandatory if -backup flag is provided.
| --rancher-url                 | This is the URL through which Rancher can be accessed. It follows this format: `"https://\<rancher server ip\>/"`
| --bearer-token                | This is the token provided by the Rancher server to access its cluster/apis without using password. For more information, refer to [here](https://rancher.com/docs/rancher/v2.5/en/user-settings/api-keys/). The API key should be set to "no scope" because in order to access APIs, the plugin must have access to the complete scope of the Rancher server. This is mandatory argument.
| --cluster-name                | Cluster name to perform backup/restore on.
| --log-location                | Log file name along with path where the logs should be saved. Default: /tmp/etcd-rke-backup.log


**Examples:**
A user may specify more than one option with each command execution. For example, to create a backup with a configured target name and associated namespace, and to set the Rancher access URL with the associated bearer token, as well as naming the cluster for backup, execute the following single command:

`kubectl rke-etcd-backup-restore -backup --target-name <target name> --target-namespace <Target namespace> --rancher-url <https://rancher server ip/> --bearer-token <bearer_token> --cluster-name <cluster_name>
`

Then, to restore from the same cluster, set the Rancher access URL with the associated bearer token, as well as naming the cluster for restore, execute the following single command:
`kubectl rke-etcd-backup-restore -restore --rancher-url <https://rancher server ip/> --bearer-token <bearer_token> --cluster-name <cluster_name>`

