# TrilioVault for Kubernetes tvk-quickstart plugin

**tvk-quickstart** is a kubectl plugin which installs TrilioVault for Kuberentes (TVK), configures UI, creates target and run some sample backup/res on TrilioVault for Kuberentes (TVK) and provides option to uninstall it.
It installs the TVK Operator, the TVM Application, configures the TVK Management Console, creates NFS/s3 target and executes sample backup and restore operations.
This plugin is tested on OCP,RKE,GKE,DO kubernetes clusters.

## Pre-requisites:

1. All the prerequisites that are required for TVK installation.[refer](https://docs.trilio.io/kubernetes/getting-started-3/getting-started/install-and-configure)
2. S3cmd. Install from [here](https://s3tools.org/s3cmd)
3. yq(version >= 4). Information can be found @[here](https://github.com/mikefarah/yq) 
4. oc, if running for OCP cluster - Install from here [here](https://mirror.openshift.com/pub/openshift-v4/clients/ocp/)

**Supported OS and Architectures**:

OS:
- Linux
- darwin


## tvk-quickstart plugin performs the following tasks:

- Preflight check:
	Performs preflight checks to ensure that all requirements are satisfied.
- **TVK Installation**:
	**Installs TVK along with TVM and does License installation** 
- TVK Management Console Configuration:
        Even after above configuation, users has an option to choose from ['Loadbalancer','Nodeport','PortForwarding'] to access the console using tvk-quickstart plugin.
- Target Creation:
	Creates and validate the target where backups are stored. Users can create S3 (DigitalOCean Spaces / AWS S3) or NFS based target.  
- Run Sample Tests of Backup and Restore:
        Run sample tests for ['Label_based','Namespace_based','Operator_based','Helm_based'] applications. By default, 'Label_based' backup tests are run against a MySQL Database application, 'Namespace_based' tests against a Wordpress application, 'Operator_based' tests against MySQL Database operator application,'Helm_based' tests against a Mongo Database helm based application.
- TVK uninstall:
	Uninstalls TVK and its associated resources.

## Installation, Upgrade, Removal of Plugins :

#### 1. With `krew`:

- Add TVK custom plugin index of krew:

  ```
  kubectl krew index add tvk-interop-plugin https://github.com/trilioData/tvk-interop-plugins.git
  ```

- Installation:

  ```
  kubectl krew install tvk-interop-plugin/tvk-quickstart
  ```  

- Upgrade:

  ```
  kubectl krew upgrade tvk-quickstart
  ```  

- Removal:

  ```
  kubectl krew uninstall tvk-quickstart
  ```

#### 2. Without `krew`:

1. List of available releases: https://github.com/trilioData/tvk-interop-plugins/releases
2. Choose a version of preflight plugin to install and check if release assets have preflight plugin's package[tvk-quickstart.tar.gz]
3. Set env variable `version=v1.x.x` [update with your desired version]. If `version` is not exported, `latest` tagged version
   will be considered.

##### Linux/macOS

- Bash or ZSH shells
```bash
(
  set -ex; cd "$(mktemp -d)" &&
  if [[ -z ${version} ]]; then version=$(curl -s https://api.github.com/repos/trilioData/tvk-interop-plugins/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")'); fi &&
  echo "Installing version=${version}" &&
  curl -fsSLO "https://github.com/trilioData/tvk-interop-plugins/releases/download/"${version}"/tvk-quickstart.tar.gz" &&
  tar zxvf tvk-quickstart.tar.gz && sudo mv tvk-quickstart/tvk-quickstart /usr/local/bin/kubectl-tvk_quickstart
)
```
Verify installation with `kubectl tvk-quickstart --help`

##### Windows
NOT SUPPORTED


## Usage

There are two way to use the tvk-quickstart plugin:
1. Interactive
2. Non-interactive


## Ways to execute the plugin

**1. Interactive**:
        The plugin asks for various inputs that enable it to perform installation and deployment operations. 
        For interactive installation of TVK operator and manager, configure TVK UI, create a target and run sameple backup restore, run below command:

kubectl tvk-quickstart [options] 

Flags:

| Parameter                     | Description   
| :---------------------------- |:-------------:
| -h, --help			| Shows brief help
| -n, --noninteractive          | Runs script in non-interactive mode.for this you need to provide config file
| -i, --install-tvk             | Installs TVK and it's free trial license.
| -c, --configure-ui            | Configures TVK UI.
| -t, --target                  | Creates Target for backup and restore jobs
| -s, --sample-test		| Creates sample backup and restore jobs
| -p, --preflight		| Checks if all the pre-requisites are satisfied
| -v, --verbose			| Runs the plugin in verbose mode
| -u, --uninstall-tvk		| Uninstalls TVK and related resources


```shell script
kubectl tvk-quickstart -i -c -t -s
kubectl tvk-quickstart -n /tmp/input_config
kubectl tvk-quickstart -u
```

**2. Non-interactive**:
	tvk-quickstart can be executed in a non-interactive method by leveraging values from an input_config file. To use the plugin in a non-interactive way, create an input_config (https://github.com/trilioData/tvk-interop-plugins/blob/main/tests/tvk-quickstart/input_config) file. After creating the input config file, run the following command to execute the plugin in a non-interactive fashion. The non-interative method will perform preflight checks, installation, configuration (Management Console and Target) as well as run sample backup and restore tests similar to the interactive mode but in a single workflow.

Sample input_config file can be found here:
https://github.com/trilioData/tvk-interop-plugins/blob/main/tests/tvk-quickstart/input_config

This sample_config input file leverages your credentials and DNS information to create/configure a target, and to configure the management console leveraging a Kubernetes LoadBalancer.

```shell script
kubectl tvk-quickstart -n
```

## 'input_config' /input parameter details

- **PREFLIGHT**:
	This parameter is to check whether or not preflight should be executed.It accepts one of the value from [True, False]
	More info around this can be found @[here](https://github.com/trilioData/tvk-plugins/tree/main/docs/preflight)
- **proceed_even_PREFLIGHT_fail**:
	This option is dependent of PREFLIGHT execution.If a user wish to proceed even if few checks failed in preflight execution, user need to set this variable to y/Y. This variable accepts one of the value from [Y,y,n,N].
- **TVK_INSTALL**:
	This parameter is to check whether or not TVK should be installed.It accepts one of the value from [True, False]
- **CONFIGURE_UI**:
	This parameter is to check whether or not TVK UI should be configured.It accepts one of the value from [True, False]
- **TARGET**:
	This parameter is to check whether or not TVK Target should be created.It accepts one of the value from [True, False]
	***Note***: Target type "Readymade_Minio" requires 4GB per node, else the target creation will fail.
- **SAMPLE_TEST**: 
	This parameter is to check whether or not sample test should be executed.It accepts one of the value from [True, False]
- **storage_class**:
	This parameter expects storage_class name which should be used across plugin execution. If kept empty, the storage_class annoted with 'default' label would be considered. If there is no such class, the plugin would likely fail.
- **operator_version**:
	This parameter expects user to specify the TVK operator version to install as a part of tvk installation process.
	The compatibility/bersion can be found @[here](https://docs.trilio.io/kubernetes/use-triliovault/compatibility-matrix#triliovaultmanager-and-tvk-application-compatibility). If this parameter is empty, by default TrilioVault operator version  2.1.0 will get installed.
- **triliovault_manager_version**:
	This parameter expects user to specify the TVK manager version to install as a part of tvk installation process.
        The compatibility/bersion can be found @[here](https://docs.trilio.io/kubernetes/use-triliovault/compatibility-matrix#triliovaultmanager-and-tvk-application-compatibility). If this parameter is empty, by default TrilioVault operator version  2.1.0 will get installed.
- **tvk_ns**:
	This parameter expects user to specify the namespace in which user wish tvk to get installed in.
- **if_resource_exists_still_proceed**:
	This parameter is to check whether plugin should proceed for other operationseven if resources exists.It accepts one of the value from [Y,y,n,N]
- **ui_access_type**:
	Specify the way in which TVK UI should be configured. It accepts one of the value from ['Loadbalancer','Nodeport','PortForwarding']
- **domain**:
	The value of this parameter is required when 'ui_access_type == Loadbalancer'.Specify the domain name which has been registered with a registrar and under which you wish to create record in. More info around this parameter can be found @[here](https://docs.digitalocean.com/products/networking/dns/)
- **tvkhost_name**:
	The value of this parameter is required when 'ui_access_type == Loadbalancer OR ui_access_type == Nodeport'. The value of this parameter will be the hostname by which the TVK management console will be accessible through a web browser.
- **cluster_name**:
	The value of this parameter is required when 'ui_access_type == Loadbalancer OR ui_access_type == Nodeport'. If kept blank, the active cluster name will be taken.
- **vendor_type**:
	The value of this parameter is required to create target. Specify the vendor name under which target needs to be created. Currently supported value is one for the ['Digital_Ocean','Amazon_AWS']
- **doctl_token**:
	The value of this parameter is required to create target. Specify the token name to authorize user.A token that allows it to query and manage DO account details and resources for user.
- **target_type**:
	Target is a location where TrilioVault stores backup.Specify type of target to create.It accepts one of the value from ['NFS','S3']. More information can be found @[here](https://docs.trilio.io/kubernetes/getting-started/getting-started-1#step-2-create-a-target)
- **access_key**:
	This parameter is required when 'target_type == S3'.This is used for bucket S3 access/creation. The value should be consistent with the vendor_type you select.
- **secret_key**:
	This parameter is required when 'target_type == S3'.This is used for bucket S3 access/creation. The value should be consistent with the vendor_type you select.
- **host_base**:
	This parameter is required when 'target_type == S3'.specify the s3 endpoint for the region your Spaces/Buckets are in.
	More information can be found @[here](https://docs.digitalocean.com/products/spaces/resources/s3cmd/#enter-the-digitalocean-endpoint)
- **host_bucket**:
	The value of this parameter should be URL template to access s3 bucket/spaces.This parameter is required when 'target_type == S3'.
	Generally it's value is '%(bucket)s.<value of host_base>' . This is the URL to access the bucket/space.
- **gpg_passphrase**:
	This parameter is for an optional encryption password. Unlike HTTPS, which protects files only while in transit, GPG encryption prevents others from reading files both in transit and while they are stored.  More information can be found @[here](https://docs.digitalocean.com/products/spaces/resources/s3cmd/#optional-set-an-encryption-password)
- **bucket_location**:
	Specify the location where the s3 bucket for target should be created. This parameter is specific to AWS vendor_type.The value can be one from ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-northeast-1', 'ap-southeast-1', 'ap-southeast-2', 'sa-east-1'].
- **bucket_name**:
	Specify the name for the bucket to be created or looked for target creation.
- **target_name**:
	Specify the name for the target that needs to be created.
- **target_namespace**:
	Specify the namespace name in which target should be created in. User should have permission to create/modify/access the namespace.
- **nfs_server**:
	The server Ip address or the fully qualified nfs server name. This paramere is required when 'target_type == NFS'
- **nfs_path**:
	Specify the exported path which can be mounted for target creation. This paramere is required when 'target_type == NFS'
- **nfs_options**:
	Specify if any other NFS option needs to be set. Additional values for the nfsOptions field can be found @[here](https://docs.trilio.io/kubernetes/architecture/apis-and-command-line-reference/custom-resource-definitions-application-1#triliovault.trilio.io/v1.NFSCredentials)
- **thresholdCapacity**:
	Capacity at which the IO operations are performed on the target.Units supported - [Mi,Gi,Ti]
- **csi_loghorn**:
        If valid csidriver is not present on cluster, it confirms to install longhorn CSI driver - [Y,N]
- **bk_plan_name**:
	Specify the name for backup plan creation for the sample application. Default value is 'trilio-test-backup'.
- **bk_plan_namespace**:
	Specify the namespace in which the application should get installed and the backup plan will get created. Default value is 'trilio-test-backup'.
- **backup_name**:
	 Specify the name for backup to be created for the sample application. Default value is 'trilio-test-backup'.
- **backup_namespace**:
	Specify the namespace in which backup should get created. Default value is 'trilio-test-backup'.
- **backup_way**:
	Specify the way in which backup should be taken.Supported values  ['Label_based','Namespace_based','Operator_based','Helm_based', 'Transformation'].
	For Label_based, MySQL application would be installed and sample backup/restore will be showcased.
	For Namespace_based, Wordpress application would be installed and sample backup/restore will be showcased.
	For Operator_based, MySQL operator  would be installed and sample backup/restore will be showcased.
	For Helm_based, Mongodb  application would be installed and sample backup/restore will be showcased.
        For Transformation, PostgreSQL application would get installed, backup would be taken and during restore, it will showcase how the transformation works.
- **restore**:
	Specify whether or not restore should be executed. Allowed values are one from the  [True, False] list.
- **restore_name**:
	Specify the name for the restore. Default value is 'tvk-restore'.
- **restore_namespace**:
	Specify the namespace in which backup should be restored. Default value is 'tvk-restore'.
