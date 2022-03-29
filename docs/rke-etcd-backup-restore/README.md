# RKE ETCD BACKUP RESTORE:

## ETCD:
Etcd is the persistent data store for Kubernetes. It is a distributed key-value store that records the state of all resources in a Kubernetes cluster.
Etcd is a distributed reliable key-value store which is simple, fast and secure. 
It acts like a backend service discovery and database, runs on different servers in Kubernetes clusters at the 
same time to monitor changes in clusters and to store state/configuration data that should to be accessed by a Kubernetes master or clusters.

## Backups and Disaster Recovery of RKE cluster:

RKE clusters can be configured to take snapshots of etcd. In a disaster scenario, you can restore these snapshots.
This snapshots can be shared outside cluster like s3 storage so that in case if we loose server, we will have backups to restore.

### Pre-reqs:
1. krew - kubectl-plugin manager. Install from here
2. kubectl - kubernetes command-line tool. Install from here
3. Triliovault for kubernetes and TVK target.

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

## Usage

usage: ETCD Backup and restore on Rancher cluster. Available flags: -backup -restore.
       [-h] [-backup] [-restore] [--target-name TARGET_NAME]
       [--target-namespace TARGET_NAMESPACE] --rancher-url RANCHER_URL
       --bearer-token BEARER_TOKEN --cluster-name CLUSTER_NAME
       [--log-location LOG_LOC]

optional arguments:
  -h, --help            show this help message and exit
  -backup
  -restore
  --target-name TARGET_NAME
                        The name of a single datastore on which etcd backup
                        needs to be shared
  --target-namespace TARGET_NAMESPACE
                        Namespace name where the target resides.
  --rancher-url RANCHER_URL
                        Rancher server URL
  --bearer-token BEARER_TOKEN
                        token to access rancher server
  --cluster-name CLUSTER_NAME
                        cluster name if it is not set in kube-system
  --log-location LOG_LOC
                        Log file name along with path where the logs should be
                        save. default - /tmp/etcd-ocp-backup.log

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
		"https://<rancher server ip>/"
		This is mandatory argument.
- **--bearer-token**:
		This is the token provided by rancher server to access its cluster/apis without using password.
		More info about how to get bearer-token can be found at https://rancher.com/docs/rancher/v2.5/en/user-settings/api-keys/
		This is mandatory argument.
- **--cluster-name**:
		Rancher server hosts many RKE cluster, so specify the one cluster name for which ETCD backup is to be taken.
		This is mandatory argument.
- **--log-location**:
		specify the log file location. default: /tmp/etcd-ocp-backup.log


