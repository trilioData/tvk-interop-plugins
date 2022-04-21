# OCP ETCD BACKUP RESTORE

## Introduction to ETCD
ETCD is the persistent data store for Kubernetes. It is a distributed key-value store that records the state of all resources in a Kubernetes cluster and it is simple, fast and secure. It acts like a backend service discovery and database. It runs on different servers in Kubernetes clusters at the 
same time, which enables it to monitor changes in clusters and store state/configuration data that are to be accessed by a Kubernetes master or clusters.

## Backups and Disaster Recovery (DR) of OCP clusters
ETCD data must be backed up before shutting down a cluster. ETCD is the key-value store for OpenShift Container Platform, which persists the state of all resource objects. Subsequently, ETCD backup plays a crucial role in disaster recovery. There are several situations where OpenShift Container Platform does not work as expected, such as:

* You have a cluster that is not functional following a restart because of unexpected conditions, such as node failure, or network connectivity issues.
* You have deleted something critical in the cluster by mistake.
* You have lost the majority of your control plane hosts, leading to ETCD quorum loss.

In disaster situations like above, you can always recover by restoring your cluster to its previous state using the saved ETCD snapshots. 

### Important Considerations about OCP Cluster Backups and DR

* Disaster recovery/Restore requires you to have at least one healthy control plane host (also known as the master host).
User should run this plugin on bastion node if user wants to perform restore.[Bastion host is the host which is created using same network as the cluster and can ping the nodes of cluster.] More information around bastion node - https://docs.openshift.com/container-platform/4.7/networking/accessing-hosts.html
* User has to only create bastion node which should be accessed using ssh. This plugin will itself create ssh connectivity from bastion to cluster nodes.

If user has only lost some crucial cluster information then user can restore from the snapshot saved using this plugin
If user has lost nodes, then user has to run restore using this plugin. Create nodes and add to cluster and then run post restore option from this plugin.
**Note: Restore functionality will only work on same cluster from where the backup was taken** 

You can get more information from : 
Source of information - https://access.redhat.com/documentation/en-us/openshift_container_platform/4.6/html-single/backup_and_restore/index

**Note: Please do not switch of any node in cluster while restore is in progress and do not abort restore task in between, else you may loose cluster accessibility**

### Pre-reqs:
1. krew - kubectl-plugin manager. Install from [here](https://krew.sigs.k8s.io/docs/user-guide/setup/install/)
2. kubectl - kubernetes command-line tool. Install from [here](https://kubernetes.io/docs/tasks/tools/install-kubectl/)
3. Triliovault for kubernetes and TVK target. Install from [here](https://docs.trilio.io/kubernetes/use-triliovault/installing-triliovault/)
4. oc - Install from [here](https://mirror.openshift.com/pub/openshift-v4/clients/ocp/)

## Installation, Upgrade, Removal of Plugins :

#### 1. With `krew`:

- Add TVK custom plugin index of krew:

  ```
  kubectl krew index add tvk-interop-plugin https://github.com/trilioData/tvk-interop-plugins.git
  ```

- Installation:

  ```
  kubectl krew install tvk-interop-plugin/ocp-etcd-backup-restore
  ```

- Upgrade:

  ```
  kubectl krew upgrade ocp-etcd-backup-restore
  ```

- Removal:

  ```
  kubectl krew uninstall ocp-etcd-backup-restore
  ```

## Usage

    ETCD Backup and restore on OCP. Available flags: -backup -restore.
       [-h] [-backup] [-restore] [--target-name TARGET_NAME]
       [--target-namespace TARGET_NAMESPACE] --api-server-url API_SERVER_URL
       --ocp-cluster-user OCP_CLUSTER_USER --ocp-cluster-pass OCP_CLUSTER_PASS
       [-p] [--log-location LOG_LOC]

Flags:

| Parameter                     | Description
| :---------------------------- |:-------------:
| -backup                       | Flag to notify backup is to be taken.
| -restore                      | Falg to notify restore is to be performed.
| --target-name                 | The name of a single datastore on which etcd backup needs to be stored. Target should be created in same namespace in which TVK resides.
| --target-namespace            | Namespace name where the target resides or TVK is installed.
| --api-server-url              | Api server URL to login cluster.
| --ocp-cluster-user            | Username to login cluster.
| --ocp-cluster-pass            | Password to login cluster
| -p                            | Denotes or notify plugin to perform post restore tasks.
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
                Target should be created in same namespace in which TVK is installed.
		This argument is mandatory if -backup flag is provided.
- **--target-namespace**:
		Namespace name in which TVK target resides or TVK is installed
		This argument is mandatory if -backup flag is provided.
- **--api-server-url**:
 		This argument is the api url for cluster.
		Its in the below format:  
		"https://api.<cluster_name>\.\<domain\>:6443"
                To check if URL is correct - try below command and see if it works.  
                "oc login \<api-server-url\> -u \<username\> -p \<password\>" 
                This is mandatory option.
                 
- **--ocp-cluster-user**:
		User name to access OCP cluster.  
                This is mandatory option.
- **--ocp-cluster-pass**:
		Password for the --ocp-cluster-user to access cluster.  
                This is mandatory option.
- **--log-location**:
		specify the log file location. default: /tmp/etcd-ocp-backup.log

#### Example

 kubectl ocp-etcd-backup-restore -backup --target-name <target_ns> --target-namespace <target_ns> --api-server-url "https://api.<clustername\>\.\<domain\>:6443" --ocp-cluster-user <user> --ocp-cluster-pass "<password>"

  kubectl ocp-etcd-backup-restore -restore --api-server-url "https://api.<clustername\>\.\<domain\>:6443" --ocp-cluster-user <user> --ocp-cluster-pass "<passwd>"
