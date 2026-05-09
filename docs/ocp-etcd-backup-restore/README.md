# OCP ETCD BACKUP RESTORE

## Introduction to ETCD
ETCD is the persistent data store for Kubernetes. It is a distributed key-value store that records the state of all resources in a Kubernetes cluster and it is simple, fast and secure. It acts like a backend service discovery and database. It runs on different servers in Kubernetes clusters at the 
same time, which enables it to monitor changes in clusters and store state/configuration data that are to be accessed by a Kubernetes master or clusters.

## Backups and Disaster Recovery (DR) of OCP clusters
ETCD data must be backed up before shutting down a cluster. ETCD is the key-value store for OpenShift Container Platform, which persists the state of all resource objects. Subsequently, ETCD backup plays a crucial role in disaster recovery. There are several situations where OpenShift Container Platform does not work as expected, such as:

* You have a cluster that is not functional following a restart because of unexpected conditions, such as node failure, or network connectivity issues.
* You have deleted something critical in the cluster by mistake.
* You have lost the majority of your control plane hosts, leading to ETCD quorum loss.

In disaster situations like above, you can always recover by restoring your cluster to its previous state using the saved ETCD snapshots. Some important considerations to keep in mind about OCP Cluster Backups and DR:

* Disaster recovery/Restore requires you to have at least one healthy control plane host (also known as the master host).
User should run this plugin on bastion node if user wants to perform restore.[Bastion host is the host which is created using same network as the cluster and can ping the nodes of cluster.] More information around bastion node - https://docs.openshift.com/container-platform/4.7/networking/accessing-hosts.html
* User has to only create bastion node which should be accessed using ssh. This plugin will itself create ssh connectivity from bastion to cluster nodes.

***Source of information - https://access.redhat.com/documentation/en-us/openshift_container_platform/4.6/html-single/backup_and_restore/index***

## ETCD backup and restore using ocp-etcd-backup-restore plugin
The plugin helps the user to perform ETCD backup and restore of OCP clusters. If a user has lost some crucial cluster information, then they can restore from the snapshot saved using this plugin. If the user has lost nodes, they must recreate all the non-recovery control plane machines and then run '-p' option from this plugin to redeploy ETCD. Some important considerations to keep in mind about the plugin:

* The plugin supports s3 as backup target
* Restore functionality will only work on same cluster from where the backup was taken
* Please do not switch of any node in cluster while restore is in progress and do not abort restore task in between, else you may loose cluster accessibility


## Plugin Pre-reqs:
1. krew - kubectl-plugin manager. Install from [here](https://krew.sigs.k8s.io/docs/user-guide/setup/install/).
2. kubectl kubernetes command-line tool. Install from [here](https://kubernetes.io/docs/tasks/tools/install-kubectl/).
3. Triliovault for kubernetes and TVK target. Install from [here](https://docs.trilio.io/kubernetes/use-triliovault/installing-triliovault/)
4. oc - Install from [here](https://mirror.openshift.com/pub/openshift-v4/clients/ocp/).
5. Linux or macOS are supported. Windows is not supported at this time.


## Installation, Upgrade, Removal of Plugins :

### Using krew:

| Action                                  | Command                                                                                           |
| --------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Add the TVK custom plugin index of krew | `kubectl krew index add tvk-interop-plugin` https://github.com/trilioData/tvk-interop-plugins.git |
| Perform the installation                | `kubectl krew install tvk-interop-plugin/ocp-etcd-backup-restore`                                          |
| Upgrade the plugin                      | `kubectl krew upgrade ocp-etcd-backup-restore`                                                             |
| Uninstall the plugin                    | `kubectl krew uninstall ocp-etcd-backup-restore`                                                           |


### Without krew:
If the krew plugin manager is not an option, you may still install the ocp-etcd-backup-restore plugin without krew using the following steps:

1. Navigate to this list of available releases: https://github.com/trilioData/tvk-interop-plugins/releases.
2. Choose a version of preflight plugin to install and check if release assets have preflight plugin's package[ocp-etcd-backup-restore-${OS}.tar.gz]
3. Set env variable version `TVK_OCP_ETCD_BACKUP_RESTORE_VERSION=[INSERT VERSION HERE]`. If the version is not exported, then the latest tagged version will be considered.
4. Run this Bash or ZSH shells command to download and install the ocp-etcd-backup-restore plugin without krew:

   ```bash
   (
     set -ex; cd "$(mktemp -d)" &&
     OS="$(uname)" &&
     if [[ -z ${TVK_OCP_ETCD_BACKUP_RESTORE_VERSION} ]]; then version=$(curl -s https://api.github.com/repos/trilioData/tvk-interop-plugins/releases/ | grep -oP '"tag_name": "\K(.*)(?=")'); fi &&
     echo "Installing version=${TVK_OCP_ETCD_BACKUP_RESTORE_VERSION}" &&
     package_name="ocp-etcd-backup-restore-${OS}.tar.gz" &&
     curl -fsSLO "https://github.com/trilioData/tvk-interop-plugins/releases/download/"${TVK_OCP_ETCD_BACKUP_RESTORE_VERSION}"/${package_name}" &&
     tar zxvf ${package_name} && sudo mv ocp-etcd-backup-restore /usr/local/bin/kubectl-ocp_etcd_backup_restore
   )
   ```
5. Verify installation using the command: `kubectl ocp-etcd-backup-restore --help`


## Usage

    ETCD Backup and restore on OCP. Available flags: -backup -restore.
       [-h] [-backup] [-restore] [--target-name TARGET_NAME]
       [--target-namespace TARGET_NAMESPACE] --api-server-url API_SERVER_URL
       --ocp-cluster-user OCP_CLUSTER_USER --ocp-cluster-pass OCP_CLUSTER_PASS
       [-p] [--log-location LOG_LOC]

Arguments/Flags:

| Flag                          | Argument Details
| :---------------------------- |:-------------
| -backup                       | Flag to notify the plugin to perform a backup.
| -restore                      | Flag to notify the plugin to perform a restore.
| --target-name                 | The name of a single datastore on which ETCD backup is to be stored. The target should be s3 and created in same namespace in which TVK resides and it should be available. This argument is mandatory if -backup flag is provided.
| --target-namespace            | Namespace name where the target resides or TVK is installed. This argument is mandatory if -backup flag is provided.
| --api-server-url              | Api server URL to login cluster. It follows this format:  `https://api.<cluster_name>.<domain>:6443"` To check if URL is correct, use this command to check if it works: `"oc login <api-server-url> -u <username> -p <password>"` This is a mandatory argument.
| --ocp-cluster-user            | Username to access/login the OCP cluster. This is mandatory.
| --ocp-cluster-pass            | Password for the --ocp-cluster-user to access/login the OCP cluster. This is mandatory.
| -p                            | Denotes or notify plugin to perform post restore tasks.
| --log-location                | Log file name along with path where the logs should be saved. Default: /tmp/etcd-ocp-backup.log


**Examples:**
A user may specify more than one option with each command execution. For example, to create a backup with a configured target name and associated namespace, and to set the cluster API URL with the associated username and password, execute the following single command:

`kubectl ocp-etcd-backup-restore -backup --target-name <target_ns> --target-namespace <target_ns> --api-server-url "https://api.<clustername>.<domain>:6443" --ocp-cluster-user <user> --ocp-cluster-pass "<password>"`

Then, to restore from the same cluster API URL with the associated username and password, execute the following single command:
`kubectl ocp-etcd-backup-restore -restore --api-server-url "https://api.<clustername>.<domain>:6443" --ocp-cluster-user <user> --ocp-cluster-pass "<passwd>"`
