import os
import random
import base64
import string
import sys
import threading
from subprocess import DEVNULL
import subprocess
import time
import logging
import argparse
import datetime
import json
import urllib3
import paramiko
import boto3
from Crypto.PublicKey import RSA
from kubernetes.client.rest import ApiException
from kubernetes.client import configuration
from kubernetes.stream import stream
from kubernetes import client, config
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_WAIT_TIMEOUT = 86400.0  # 1 day
DEFAULT_WAIT_BETWEEN_ATTEMPTS = 1.0  # 1 second
DEFAULT_JOB_POD_COUNT = 1  # expect job:pod to be 1:1 by default


class ETCDOcpBackup:
    def __init__(self, api_instance, api_batch, custom_api, logger):
        self.api_instance = api_instance
        self.custom_api = custom_api
        self.api_batch = api_batch
        self.logger = logger
        self.nodes = dict()
        self.etcdns = "openshift-etcd"
        self.labels = "app=etcd,etcd=true"
        self.etcd_pods = dict()
        try:
            kube_ns = self.api_instance.read_namespace(name="kube-system")
        except BaseException as exception:
            self.logger.error("Error in getting information about "
                              "'kube-system' namespace")
        self.kube_uid = kube_ns.metadata.uid
        datime = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.etcd_dir = f"tvk_etcd_bk_{self.kube_uid}_{datime}"
        self.etcd_backup_dir = os.path.join(
            "/etc/kubernetes/static-pod-resources/etcd-member/", self.etcd_dir)

    def create_backup_job(self):

        # create random job name
        str_len = 3

        # generating random strings
        res = ''.join(random.choices(string.ascii_lowercase +
                                     string.digits, k=str_len))

        self.bk_job_name = f'openshift-backup-{res}'
        self.backup_ns = "ocp-backup-etcd"
        # create required service account and role_binding
        etcd_backup_job = """
apiVersion: v1
kind: Namespace
metadata:
  name: ocp-backup-etcd
  labels:
    app: openshift-backup
  annotations:
    openshift.io/node-selector: ''
---
kind: ServiceAccount
apiVersion: v1
metadata:
  name: openshift-backup
  namespace: ocp-backup-etcd
  labels:
    app: openshift-backup
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cluster-etcd-backup
  labels:
    app: openshift-backup
rules:
- apiGroups: [""]
  resources:
     - "nodes"
  verbs: ["get", "list"]
- apiGroups: [""]
  resources:
     - "pods"
     - "pods/log"
  verbs: ["get", "list", "create", "delete", "watch"]
---
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: openshift-backup
  labels:
    app: openshift-backup
subjects:
  - kind: ServiceAccount
    name: openshift-backup
    namespace: ocp-backup-etcd
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-etcd-backup
---
apiVersion: batch/v1
kind: Job
metadata:
  name: {2}
  namespace: ocp-backup-etcd
spec:
  activeDeadlineSeconds: 43200
  backoffLimit: 0
  completions: 1
  parallelism: 1
  template:
    spec:
      containers:
      - command:
        - /bin/sh
        - -c
        - oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{{range .items[*]}} {{.metadata.name}} {{" "}} {{.status.conditions[?(@.type=="Ready")].status}} {{" "}} {{"\\n"}} {{end}}' --no-headers | awk '$2=="True" {{ print $1}}' | xargs -I {{}} --  oc debug node/{{}} -- bash -c 'chroot /host sudo -E mkdir -p {0} && chroot /host sudo -E /usr/local/bin/cluster-backup.sh {1}'
        image: registry.redhat.io/openshift4/ose-cli:v4.8
        imagePullPolicy: IfNotPresent
        name: backup
        resources:
          limits:
            cpu: 500m
            memory: 512Mi
          requests:
            cpu: 10m
            memory: 10Mi
        securityContext:
          allowPrivilegeEscalation: true
          capabilities:
            add:
            - SYS_ADMIN
            drop:
            - ALL
          privileged: true
          readOnlyRootFilesystem: true
          runAsNonRoot: false
          runAsUser: 0
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
      dnsPolicy: ClusterFirst
      restartPolicy: Never
      schedulerName: default-scheduler
      securityContext:
        runAsNonRoot: false
        runAsUser: 0
      serviceAccount: "openshift-backup"
      serviceAccountName: "openshift-backup"
      terminationGracePeriodSeconds: 30
""".format(self.etcd_backup_dir, self.etcd_backup_dir, self.bk_job_name)

        backup_file = open("etcd-backup_job.yaml", "w")
        backup_file.write(etcd_backup_job)
        backup_file.close()

        cmd = "kubectl apply -f etcd-backup_job.yaml 1>/dev/null 2>etcd-ocp-backup.log"
        proc = subprocess.Popen(cmd, stderr=sys.stderr,
                                stdout=sys.stdout, shell=True)
        proc.communicate()
        if proc.returncode:
            err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
            self.logger.error(err_msg)
            retunr(1)

        cmd = "oc adm policy add-scc-to-user privileged -z openshift-backup "\
            "-n ocp-backup-etcd;oc adm policy add-scc-to-user anyuid -z "\
            "openshift-backup -n ocp-backup-etcd;oc adm policy "\
            "add-cluster-role-to-user cluster-admin -z "\
            "openshift-backup -n ocp-backup-etcd"

        proc = subprocess.Popen(cmd, stderr=None, stdout=DEVNULL, shell=True)
        proc.communicate()
        if proc.returncode:
            err_msg = "command :{}, exitcode :{}".format(cmd, proc.returncode)
            self.logger.error(err_msg)
            return 1
        wait_for_job_success(
            self,
            self.bk_job_name,
            "ocp-backup-etcd",
            "Waiting for backup job to complete..")

    def store_target_data_to_etcd(self, target_name, target_namespace):
        # get pod list

        try:
            pod_list = self.api_instance.list_namespaced_pod(
                namespace=f'{self.etcdns}',
                label_selector='app=etcd,etcd=true')
        except BaseException as exception:
            self.logger.error(f"Error in getting pods in {self.etcdns}"
                              " namespace")
        for pod in pod_list.items:
            pod_tuple = next(((pod.spec.node_name, pod.metadata.name)
                             for st in pod.status.conditions if st.type ==
                              "ContainersReady" and st.status ==
                              "True"), None)
            self.etcd_pods[pod_tuple[0]] = pod_tuple[1]
        node_list = self.nodes
        obj_dict = get_dict_object(
            self.api_instance,
            self.custom_api,
            target_name,
            target_namespace,
            self.logger)
        for key1, val1 in obj_dict.items():
            for key, val in node_list.items():
                command = [
                    '/bin/sh',
                    '-c',
                    f'ETCDCTL_ENDPOINTS=https://{val}:2379 etcdctl put /{key1} {val1}']
                try:
                    stream(
                        self.api_instance.connect_get_namespaced_pod_exec,
                        f"{self.etcd_pods[key]}",
                        self.etcdns,
                        command=command,
                        container='etcdctl',
                        stderr=True,
                        stdin=True,
                        stdout=True,
                        tty=False)
                except BaseException as exception:
                    self.logger.error("Error in adding target info in ETCD")
                    sys.exit(1)

    def delete_jobs(self, mover="true", backup="true"):
        """
        Function to delete jobs created for performing backup and restore.
        """

        try:
            if mover == "true":
                delete = self.api_batch.delete_namespaced_job(
                    name=self.mover_job_name,
                    body=client.V1DeleteOptions(),
                    namespace=self.mover_ns)

            if backup == "true":
                delete = self.api_batch.delete_namespaced_job(
                    name=self.bk_job_name, body=client.V1DeleteOptions(),
                    namespace=self.backup_ns)
        except BaseException as exception:
            self.logger.error("Error deleting jobs")
            self.logger.error(f"Exception: {exception}")
            sys.exit(1)

        return delete

    def create_backup_mover(self, target_name, target_ns="default"):
        """
        Function to create Backup mover pod and run it which will move
        backup to provided s3 target
        """
        str_len = 3
        # generating random strings
        res = ''.join(random.choices(string.ascii_lowercase, k=str_len))

        TVK_ns = target_ns
        serviceaccount = "k8s-triliovault"
        serviceaccountname = "k8s-triliovault"
        metamoverpod = "etcd-datamover-{0}".format(str(res))

        node_name = None
        ret = self.api_instance.list_node(
            label_selector="node-role.kubernetes.io/master")
        for node in ret.items:
            try:
                api_batch = self.api_instance.read_node_status(
                    node.metadata.name)
                my_list = api_batch.status.conditions

            except BaseException as exception:
                self.logger.error("Error in reading node's status")
                sys.exit(1)

                flag = 0
            for i in my_list:
                if i.type == "Ready" and i.status == "True":
                    self.nodes[node.metadata.name] = next(
                        (addr.address for addr in node.status.addresses
                         if addr.type == "InternalIP"), None)

        if self.nodes:
            node_name = next(iter(self.nodes))
            self.logger.info(
                f"Taking backup on node {node_name}, please do not power "
                "off this machine")
        else:
            self.logger.error("No node is in healthy state..Exiting")
            return 1

        self.mover_job_name = metamoverpod
        self.mover_ns = TVK_ns
        # Copy code from storage to control plane
        metamover_pod = """
apiVersion: batch/v1
kind: Job
metadata:
  name: {0}
  namespace: {6}
spec:
  activeDeadlineSeconds: 43200
  backoffLimit: 0
  completions: 1
  parallelism: 1
  template:
    spec:
      containers:
      - command:
        - /bin/sh
        - -c
        - ' /usr/bin/python3 /opt/tvk/datastore-attacher/mount_utility/mount_by_target_crd/mount_datastores.py --target-namespace={1} --target-name={2};cp -r /tmp/{3} /triliodata/'
        image: eu.gcr.io/amazing-chalice-243510/metamover:2.6.1
        imagePullPolicy: IfNotPresent
        name: backup
        resources:
          limits:
            cpu: 500m
            memory: 512Mi
          requests:
            cpu: 10m
            memory: 10Mi
        securityContext:
          allowPrivilegeEscalation: true
          capabilities:
            add:
            - SYS_ADMIN
            drop:
            - ALL
          privileged: true
          readOnlyRootFilesystem: true
          runAsNonRoot: false
          runAsUser: 0
        volumeMounts:
        - mountPath: /tmp
          name: etcd-backup-dir
        - mountPath: /triliodata-temp
          name: trilio-temp
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
      nodeName: {7}
      volumes:
      - hostPath:
          path: /etc/kubernetes/static-pod-resources/etcd-member
          type: ""
        name: etcd-backup-dir
      - emptyDir: {{}}
        name: trilio-temp
      dnsPolicy: ClusterFirst
      restartPolicy: Never
      schedulerName: default-scheduler
      securityContext:
        runAsNonRoot: false
        runAsUser: 0
      serviceAccount: {4}
      serviceAccountName: {5}
      terminationGracePeriodSeconds: 30
""".format(metamoverpod, target_ns, target_name, self.etcd_dir,
           serviceaccount, serviceaccountname, TVK_ns, node_name)

        myFile = open("metamover_pod.yaml", "w")
        myFile.write(metamover_pod)
        myFile.close()

        cmd = "kubectl apply -f metamover_pod.yaml 1>/dev/null" \
            "2>etcd-ocp-backup.log"
        proc = subprocess.Popen(cmd, stderr=sys.stderr,
                                stdout=sys.stdout, shell=True)
        proc.communicate()
        if proc.returncode:
            err_msg = "command :{}, exitcode :{}".format(cmd, proc.returncode)
            self.logger.error(err_msg)
            return 1
        wait_for_job_success(
            self,
            self.mover_job_name,
            TVK_ns,
            "Waiting for moving backup to target..")
        self.logger.info("ETCD backup is completed")
        self.logger.info("ETCD backup is completed and is stored"
                         f"with name: {self.etcd_dir}")

def wait_for_job_success(
    api_obj,
    job_name,
    namespace,
    wait_msg,
    keep_pod_active=0,
    wait_timeout=DEFAULT_WAIT_TIMEOUT,
    wait_time_between_attempts=DEFAULT_WAIT_BETWEEN_ATTEMPTS,
    num_pods_to_wait_for=DEFAULT_JOB_POD_COUNT,
    ):
    '''Poll a job for successful completion.
    Args:
    job_name (str): Name of the job to wait for.
    namespace (str): Namespace in which the job is located.
    wait_timeout (numeric, optional): Timeout after which to give up and raise exception.
           Defaults to DEFAULT_WAIT_TIMEOUT.
    wait_time_between_attempts (numeric, optional): Wait time between polling attempts. Defaults
           to DEFAULT_WAIT_BETWEEN_ATTEMPTS.
    '''
    job = None
    runtime = 10
    start = int(time.time())
    wait_timeout = start + 60 * runtime
    spin = '-\\|/'
    idx = 0
    # Ensure we found the job that we launched
    print(wait_msg)
    while not job:
        print(spin[idx % len(spin)], end="\r")
        idx += 1
        time.sleep(0.1)
        if int(time.time()) >= wait_timeout:
            api_obj.logger.error('Timed out while waiting for job to launch')
            sys.exit(1)
        try:
            jobs = api_obj.api_batch.list_namespaced_job(namespace=namespace)
        except BaseException as exception:
            api_obj.logger.error(f"Error in getting job information in "
                                  "namespace {namespace}")
        job = next(
            (j for j in jobs.items if j.metadata.name == job_name), None)
        if not job:
            api_obj.logger.warning(
                f'Job "{job_name}" not yet launched, waiting')
            time.sleep(wait_time_between_attempts)

    # Wait for job completed status#
    wait_timeout = start + 60 * runtime
    spin = '-\\|/'
    idx = 0
    while True:
        print(spin[idx % len(spin)], end="\r")
        idx += 1
        time.sleep(0.1)
        if int(time.time()) >= wait_timeout:
            api_obj.logger.error(
                'Timed out while waiting for job to complete')
            sys.exit(1)
        try:
            status = api_obj.api_batch.read_namespaced_job_status(
                job_name, namespace=namespace).status
        except BaseException as exception:
            api_obj.logger.error(f"Error in reading job {job_name} status")
            sys.exit()
        if status.failed and status.failed > 0:
            api_obj.logger.error(
                f'Encountered failed job pods with status: {status}')
        # done waiting for pod completion
        if status.succeeded == num_pods_to_wait_for:
            break
        if keep_pod_active == 1:
            break


class ETCDOcpRestore:
    def __init__(self, api_instance, api_batch, logger):
        self.api_instance = api_instance
        self.api_batch = api_batch
        self.logger = logger
        try:
            kube_ns = api_instance.read_namespace(name="kube-system")
        except BaseException as exception:
            self.logger.error("Error in getting information about "
                              "'kube-system' namespace")
        self.kube_uid = kube_ns.metadata.uid
        self.ssh_dict = dict()
        self.s3_info = dict()
        self.node_name = None
        self.nodes = []
        self.nodes_dict = dict()
        self.etcdns = "openshift-etcd"
        self.labels = "app=etcd,etcd=true"
        self.etcd_pods = dict()
        try:
            ret = self.api_instance.list_node(
                label_selector="node-role.kubernetes.io/master")
            for node in ret.items:
                api_batch = self.api_instance.read_node_status(
                    node.metadata.name)
                my_list = api_batch.status.conditions
                flag = 0
                for i in my_list:
                    if i.type == "Ready":
                        flag = 1
                        break
                if flag == 1:
                    if i.status == "True":
                        self.logger.info(
                            f"Restoring on node {node.metadata.name}")
                        self.node_name = node.metadata.name
                        break
        except BaseException as exception:
            self.logger.error(f"Error while reading node {node.metadata.name}"
                              " status")
        if flag == 0:
            self.logger.error("No node is in healthy state..Exiting")
            return 1

    def create_ssh_connectivity_between_nodes(self):
        """
        Function to create ssh connectivity between nodes
        """
        key = RSA.generate(1024)
        pemfile = open("private.pem", "wb")
        pemfile.write(key.exportKey('PEM'))
        pemfile.close()

        pubkey = key.publickey()
        pemfile = open("public.pem", "wb")
        pemfile.write(pubkey.exportKey('OpenSSH'))
        pemfile.close()

        with open('public.pem', 'r') as file:
            mykey = file.read()
        merge_patch = f"""
spec:
  config:
    passwd:
      users:
      - name: core
        sshAuthorizedKeys:
        - |
          {mykey}"""

        patchfile = open("merge_patch.yaml", "w")
        patchfile.write(merge_patch)
        patchfile.close()

        try:
            cmd = "kubectl get mc 99-master-ssh"
            proc = subprocess.Popen(cmd, stderr=None, stdout=DEVNULL,
                                shell=True)
            proc.communicate()
            if proc.returncode:
                self.logger.error("There is no machine configuration "
                        "name 99-master-ssh, creating 99-master-ssh")
                secret = api_instance.read_namespaced_secret(
                    name='master-user-data',
                    namespace='openshift-machine-api').data
                ignit_ver = json.loads(base64.b64decode(
                    secret['userData']))['ignition']['version']
                mach_conf = f"""
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  labels:
    machineconfiguration.openshift.io/role: master
  name: 99-master-ssh
spec:
  config:
    ignition:
      version: {ignit_ver}
  extensions: null
  fips: false
  kernelArguments: null
  kernelType: ""
  osImageURL: ""
"""
                master_file = open("master_ssh.yaml", "w")
                master_file.write(mach_conf)
                master_file.close()

                cmd = "kubectl apply -f master_ssh.yaml "\
                        "1>/dev/null 2>etcd-ocp-backup.log"
                proc = subprocess.Popen(cmd, stderr=sys.stderr,
                                stdout=sys.stdout, shell=True)
                proc.communicate()
                os.remove("master_ssh.yaml")
                if proc.returncode:
                    err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
                    self.logger.error(err_msg)
                    self.logger.error("Error in creating machine configuration")
                    sys.exit(1)
            time.sleep(10)
            resp = client.CustomObjectsApi().get_cluster_custom_object(
                group="machineconfiguration.openshift.io",
                version="v1",
                plural="machineconfigpools",
                name="master")
        except BaseException as exception:
            self.logger.error("Error in getting cluster custom object "
                              f"machineconfiguration for master nodes")
            sys.exit(1)
        old_ver = resp['metadata']['generation']

        obj = subprocess.Popen(
            'kubectl patch mc 99-master-ssh --type merge '
            '--patch "$(cat merge_patch.yaml)"',
            shell=True,
            stdout=subprocess.PIPE)
        subprocess_return = obj.stdout.read()
        print(subprocess_return)

        time.sleep(10)
        # wait till all the machines are updated

        new_ver = old_ver + 1
        runtime = 10
        start = int(time.time())
        wait_timeout = start + 60 * runtime
        spin = '-\\|/'
        idx = 0
        print("Waiting for machineconfiguration to patch successfully...")
        while True:
            if int(time.time()) >= wait_timeout:
                self.logger.error(
                    'Timed out while waiting for successfully patching '
                    ' machineconfiguration.')
                sys.exit(1)
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.2)
            resp = client.CustomObjectsApi().get_cluster_custom_object(
                group="machineconfiguration.openshift.io",
                version="v1",
                plural="machineconfigpools",
                name="master")
            old_ver = resp['metadata']['generation']
            if old_ver == new_ver:
                machinecount = resp['status']['machineCount']
                readymachine = resp['status']['readyMachineCount']
                if machinecount == readymachine:
                    break

        self.logger.info("SSH connections between nodes are established")

    def create_restore_job(self, restore_path, server, user, passwd):

        # create ranndo job name
        str_len = 3
        # generating random strings
        res = ''.join(random.choices(string.ascii_lowercase +
                                     string.digits, k=str_len))

        self.restore_etcd_job = f'openshift-restore-{res}'
        self.restore_ns = "ocp-restore-etcd"
        # create required service account and role_binding
        try:
            ssh_control_plane = paramiko.SSHClient()
            ssh_control_plane.set_missing_host_key_policy(
                paramiko.AutoAddPolicy())
            ssh_control_plane.connect(
                self.node_name, username='core', key_filename='private.pem')
        except paramiko.SSHException as sshexception:
            self.logger.error("Unable to establish SSH connection: "
                              f"{sshexception}")
        self.ssh_dict[self.node_name] = ssh_control_plane
        self.logger.info(f"Starting cluster-restore on node {self.node_name}")
        stdin, stdout, stderr = ssh_control_plane.exec_command(
            f'sudo -E /usr/local/bin/cluster-restore.sh {restore_path}')
        for line in stdout:
            self.logger.info(line)
        ret_code = stdout.channel.recv_exit_status()
        if ret_code != 0:
            self.logger.error(f"Restore failed with error {stderr}")
            self.logger.info("Please wait while the cluster is "
                             "restored to original state")
            stdout1 = ssh_control_plane.exec_command(
                'sudo -E /tmp/cluster-restore-reversed.sh')
            main(self.nodes[1:], self.ssh_dict, "/tmp/start_pod.sh", "False")
            self.post_restore_task(server, user, passwd)
        #for line in stdout:
        # # Process each line in the remote output
        #    self.logger.info(line)

    def check_ssh_connectivity(self):
        """
        Function to check if ssh connectivity is alive
        """
        value = self.ssh_dict.get(self.node_name)
        if value and value.get_transport() is not None:
            # check if ssh is still alive
            if value.get_transport().is_active() == "True":
                self.logger.info(
                    f"ssh connectivity for node {self.node_name} is alive")
            else:
                ret = get_ssh_connection(self.node_name, self.ssh_dict)
        else:
            ret = get_ssh_connection(self.node_name, self.ssh_dict)
        if ret != 0:
            self.error("Error in getting ssh connection "
                f"with node {self.node_name}")
            sys.exit(1)


    def create_metamover_and_display_available_restore(
            self, target_name, file_path):

        self.check_ssh_connectivity()

        stdin, stdout, stderr = self.ssh_dict[self.node_name].exec_command(
            'sudo mkdir /home/secret_file/;sudo chmod -R 777 /home/secret_file/')
        ret_code = stdout.channel.recv_exit_status()
        if ret_code != 0:
            self.logger(
                f"Error in creating folder on node {self.node_name}")
            sys.exit(1)
        # copying file containing crednetials on host
        sftp = self.ssh_dict[self.node_name].open_sftp()
        sftp.put(file_path, '/home/secret_file/trilio-secret')
        sftp.close()

        str_len = 3

        # generating random strings
        res = ''.join(random.choices(string.ascii_lowercase +
                                     string.digits, k=str_len))
        etcd_metamover_restore = f"etcd-metamover-restore-{res}"
        restore_ns = "ocp-restore-etcd"
        serviceaccount = "openshift-restore"
        serviceaccountname = "openshift-restore"

        etcd_metamover_job = """

apiVersion: v1
kind: Namespace
metadata:
  name: {restore_ns}
  labels:
    app: openshift-restore
  annotations:
    openshift.io/node-selector: ''
---
kind: ServiceAccount
apiVersion: v1
metadata:
  name: openshift-restore
  namespace: {restore_ns}
  labels:
    app: openshift-restore
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cluster-etcd-restore
  labels:
    app: openshift-restore
rules:
- apiGroups: [""]
  resources:
     - "nodes"
  verbs: ["get", "list"]
- apiGroups: [""]
  resources:
     - "pods"
     - "pods/log"
  verbs: ["get", "list", "create", "delete", "watch"]
---
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: openshift-restore
  labels:
    app: openshift-restore
subjects:
  - kind: ServiceAccount
    name: openshift-restore
    namespace: {restore_ns}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-etcd-restore
---
apiVersion: batch/v1
kind: Job
metadata:
  name: {etcd_metamover_restore}
  namespace: {restore_ns}
spec:
  activeDeadlineSeconds: 43200
  backoffLimit: 0
  completions: 1
  parallelism: 1
  template:
    spec:
      containers:
      - command:
        - /bin/sh
        - -c
        - ' /usr/bin/python3 /opt/tvk/datastore-attacher/mount_utility/mount_by_secret/mount_datastores.py --target-name={target_name} && while true; do sleep 30; done'
        image: eu.gcr.io/amazing-chalice-243510/metamover:2.6.1
        imagePullPolicy: IfNotPresent
        name: backup
        resources:
          limits:
            cpu: 500m
            memory: 512Mi
          requests:
            cpu: 10m
            memory: 10Mi
        securityContext:
          allowPrivilegeEscalation: true
          capabilities:
            add:
            - SYS_ADMIN
            drop:
            - ALL
          privileged: true
          readOnlyRootFilesystem: true
          runAsNonRoot: false
          runAsUser: 0
        volumeMounts:
        - mountPath: /tmp
          name: etcd-backup-dir
        - mountPath: /triliodata-temp
          name: trilio-temp
        - mountPath: /etc/secret
          name: target-secret
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
      nodeName: {node_name}
      volumes:
      - hostPath:
          path: /etc/kubernetes/static-pod-resources/etcd-member
          type: ""
        name: etcd-backup-dir
      - emptyDir: {{}}
        name: trilio-temp
      - hostPath:
          path: /home/secret_file
          type: ""
        name: target-secret
      dnsPolicy: ClusterFirst
      restartPolicy: Never
      schedulerName: default-scheduler
      securityContext:
        runAsNonRoot: false
        runAsUser: 0
      serviceAccount: {service_account}
      serviceAccountName: {service_account_name}
      terminationGracePeriodSeconds: 30
""".format(
            restore_ns=restore_ns,
            etcd_metamover_restore=etcd_metamover_restore,
            target_name=target_name,
            node_name=self.node_name,
            service_account=serviceaccount,
            service_account_name=serviceaccountname)

        meta_file = open("metamover_pod.yaml", "w")
        meta_file.write(etcd_metamover_job)
        meta_file.close()

        cmd = "kubectl apply -f metamover_pod.yaml"
        proc = subprocess.Popen(cmd, stderr=sys.stderr,
                                stdout=sys.stdout, shell=True)
        proc.communicate()
        if proc.returncode:
            err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
            self.logger.error(err_msg)
            return 1

        cmd = "oc adm policy add-scc-to-user privileged -z openshift-restore "\
            "-n ocp-restore-etcd;oc adm policy add-scc-to-user anyuid -z "\
            "openshift-restore -n ocp-restore-etcd;oc adm policy "\
            "add-cluster-role-to-user cluster-admin -z "\
            "openshift-restore -n ocp-restore-etcd"

        proc = subprocess.Popen(cmd, stderr=sys.stderr,
                                stdout=sys.stdout, shell=True)
        proc.communicate()
        if proc.returncode:
            err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
            self.logger.error(err_msg)
            return 1

        wait_for_job_success(self, etcd_metamover_restore, restore_ns,
                                  "Mounting target..", 1)
        #self.logger.info("Mounted target successfully")

        time.sleep(10)
        ls_cmd = f"ls -d /triliodata/tvk_etcd_bk_{self.kube_uid}_*"
        pod_name = None
        try:
            response = self.api_instance.list_namespaced_pod(
                namespace=restore_ns,
                label_selector=f"job-name={etcd_metamover_restore}")
        except ApiException as exception:
            self.logger.error("Error in listing pod in namespae {restore_ns}")
            sys.exit(1)
        for pod in response.items:
            pod_name = pod.metadata.name

        # print(pod_name)

        try:
            response = self.api_instance.read_namespaced_pod_status(
                pod_name, restore_ns)
        except ApiException as exception:
            self.logger.error(f"Error in reading pod {pod_name} "
                              f"status in namespae {restore_ns}")
            sys.exit(1)
        status = "NotReady"
        runtime = 10
        start = int(time.time())
        wait_timeout = start + 60 * runtime
        spin = '-\\|/'
        idx = 0
        print("Waiting for mounting target and getting available backups..")
        while True:
            try:
                response = self.api_instance.read_namespaced_pod_status(
                    pod_name, restore_ns)
            except ApiException as exception:
                self.logger.error(f"Error in reading pod {pod_name} "
                                  f"status in namespae {restore_ns}")
            conditions = response.status.conditions
            status_list = [sub.status for sub in conditions]
            if 'False' not in status_list:
                self.logger.info("Pod is in running state")
                break
            if not response.status.container_statuses[0].state.waiting and \
                not response.status.container_statuses[
                0].state.running and response.status.container_statuses[
                    0].state.terminated != "None":
                self.logger.error("Pod is not in running state")
                sys.exit(1)
            if int(time.time()) >= wait_timeout:
                self.logger.error(
                    f'Timed out while waiting for pod {pod_name} in namespace'
                    f' {restore_ns} to be in ready state')
                sys.exit(1)
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.1)
        time.sleep(5)
        exec_command = ['/bin/sh', '-c', ls_cmd]
        try:
            resp = stream(
                self.api_instance.connect_get_namespaced_pod_exec,
                pod_name,
                restore_ns,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False)
        except ApiException as exception:
            self.logger.error(f"Error in executing {ls_cmd} on pod {pod_name}")
        except BaseException as exception:
            self.logger.error(f"Error in executing {ls_cmd} on pod {pod_name}")
            self.logger.error(exception)
            sys.exit(1)

        rest_list = []
        rest_list_new = []
        rest_list = resp.splitlines()
        rest_list.sort(reverse=True)
        base_directory = rest_list[0].rsplit("/", 1)[0]
        i = 0
        for item in rest_list:
            dir_list = item.rsplit("/", 1)
            rest_list_new.append(dir_list[1])
            print(dir_list[1])
            i = i + 1
        default_bk = rest_list[0].rsplit("/", 1)[1]
        try:
            selected = input(
            f"Please select the backup to be restored: ({default_bk})")
        except EOFError:
            selected=""
        if selected == "":
            selected = rest_list[0].rsplit("/", 1)[1]
    
        #import pdb; pdb.set_trace()
        #check if backup files are present in selected directory
        resp = check_objects(self, default_bk)

        if resp == 1:
            self.logger.error("No backup files are present in selected "\
                    "directory, please check the backup once..")
            sys.exit(1)

        # copy selected folder in the host

        cpy_cmd = f"cp -r {base_directory}/{selected} /tmp/"

        print(cpy_cmd)
        exec_command = ['/bin/sh', '-c', cpy_cmd]
        try:
            resp = stream(
                api_instance.connect_get_namespaced_pod_exec,
                pod_name,
                restore_ns,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False)
        except ApiException as exception:
            self.logger.error(
                f"Error in executing {cpy_cmd} on pod {pod_name}")
        except BaseException as exception:
            self.logger.error(
                f"Error in executing {cpy_cmd} on pod {pod_name}")
            self.logger.error(exception)
            sys.exit(1)
        selected_loc = "/etc/kubernetes/static-pod-resources/"\
            f"etcd-member/{selected}"
        return selected_loc
        #logger.info("ETCD backup is completed")

    def stop_static_pods(self):
        """
        Functon to stop all etcd specific active static pods on active nodes
        """
        # Get nodes which are in Ready state
        try:
            ret = self.api_instance.list_node(
                label_selector="node-role.kubernetes.io/master")
            for node in ret.items:
                ret_resp = api_instance.read_node_status(node.metadata.name)
                node_conditions = ret_resp.status.conditions
                for condition in node_conditions:
                    if (condition.type == 'Ready' and condition.status == 'True'):
                        self.nodes.append(node.metadata.name)
        except ApiException as exception:
            self.logger.error(f"Error in getting nodes information")
        except BaseException as exception:
            self.logger.error(f"Error in getting nodes information")
            self.logger.error(exception)
            sys.exit(1)
        long_string = """
#!/usr/bin/env bash
echo 'Moving etcd-pod.yaml to /tmp'
sudo mv /etc/kubernetes/manifests/etcd-pod.yaml /tmp
var1=$(sudo crictl ps | grep etcd | grep -v operator)
echo 'Waiting for etcd pod to stop..'
while [ "$var1" != "" ]; do
  var1=$(sudo crictl ps | grep etcd | grep -v operator)
done
echo 'Moving kube-apiserver-pod.yaml to /tmp'
sudo mv /etc/kubernetes/manifests/kube-apiserver-pod.yaml /tmp
var2=$(sudo crictl ps | grep kube-apiserver | grep -v operator)
echo 'Waiting for kube-apiserver pod to stop...'
while [ "$var2" != "" ]; do
  var2=$(sudo crictl ps | grep kube-apiserver | grep -v operator)
done
echo 'Moving ETCD directory....'
sudo mv /var/lib/etcd/ /tmp
echo 'done'"""

        stop_pod = open("/tmp/stop_pod.sh", "w")
        stop_pod.write(long_string)
        stop_pod.close()

        restore_back = """
#!/usr/bin/env bash
echo 'Moving /tmp/etcd-pod.yaml to /etc/kubernetes/manifests'
sudo mv /tmp/etcd-pod.yaml /etc/kubernetes/manifests/etcd-pod.yaml
var1=$(sudo crictl ps | grep etcd | grep -v operator)
echo 'Waiting for etcd pod to start..'
while [ "$var1" == "" ]; do
  var1=$(sudo crictl ps | grep etcd | grep -v operator)
done
echo 'Moving /tmp/kube-apiserver-pod.yaml to /etc/kubernetes/manifests'
sudo mv /tmp/kube-apiserver-pod.yaml /etc/kubernetes/manifests/kube-apiserver-pod.yaml
var2=$(sudo crictl ps | grep kube-apiserver | grep -v operator)
echo 'Waiting for kube-apiserver pod to start...'
while [ "$var2" == "" ]; do
  var2=$(sudo crictl ps | grep kube-apiserver | grep -v operator)
done
echo 'Moving ETCD directory....'
sudo mv /tmp/etcd /var/lib/etcd/
echo 'done'"""

        start_pod = open("/tmp/start_pod.sh", "w")
        start_pod.write(restore_back)
        start_pod.close()

        control_plane_reversed = """
#!/usr/bin/env bash

### Created by cluster-etcd-operator. DO NOT edit.

set -o errexit
set -o pipefail
set -o errtrace

# example
# ./cluster-restore-reversed.sh

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root"
  exit 1
fi

source_required_dependency /etc/kubernetes/static-pod-resources/etcd-certs/configmaps/etcd-scripts/etcd.env
source_required_dependency /etc/kubernetes/static-pod-resources/etcd-certs/configmaps/etcd-scripts/etcd-common-tools

function usage() {
  echo 'Path to the directory containing backup files is required: ./cluster-restore-reversed.sh'
}



function wait_for_containers_to_start() {
  local containers=("$@")

  for container_name in "${containers[@]}"; do
    echo "Waiting for container ${container_name} to start"
    while [[ -z $(sudo crictl ps --label io.kubernetes.container.name="kube-apiserver" -q) ]]; do
      echo -n "."
      sleep 1
    done
    echo "complete"
  done
}

STATIC_POD_LIST=("kube-apiserver-pod.yaml" "kube-controller-manager-pod.yaml" "kube-scheduler-pod.yaml")
STATIC_POD_CONTAINERS=("etcd" "etcdctl" "etcd-metrics" "kube-controller-manager" "kube-apiserver" "kube-scheduler")


# Move manifests and stop static pods
if [ ! -d "$MANIFEST_STOPPED_DIR" ]; then
  echo "No such file or directory - $MANIFEST_STOPPED_DIR"
  exit 1
fi

# Move static pod manifests out of MANIFEST_DIR
for POD_FILE_NAME in "${STATIC_POD_LIST[@]}" etcd-pod.yaml; do
  echo "...starting ${POD_FILE_NAME}"
  [ ! -f "${MANIFEST_DIR}/${POD_FILE_NAME}" ] && continue
  mv "${MANIFEST_STOPPED_DIR}/${POD_FILE_NAME}" "${MANIFEST_DIR}"
done

# wait for every static pod container to start
#wait_for_containers_to_start "${STATIC_POD_CONTAINERS[@]}"

if [ ! -d "${ETCD_DATA_DIR_BACKUP}" ]; then
  echo "No such fil or directory ${ETCD_DATA_DIR_BACKUP}"
fi

# backup old data-dir
if [ -d "${ETCD_DATA_DIR}/member" ]; then
  echo "Moving etcd data-dir ${ETCD_DATA_DIR_BACKUP}/member to ${ETCD_DATA_DIR}"
  mv "${ETCD_DATA_DIR_BACKUP}"/member "${ETCD_DATA_DIR}"
fi

# wait for every static pod container to start
wait_for_containers_to_start "${STATIC_POD_CONTAINERS[@]}"

    """
        reverse_rest = open("/tmp/cluster-restore-reversed.sh", "w")
        reverse_rest.write(control_plane_reversed)
        reverse_rest.close()

        main(self.nodes[1:], self.ssh_dict, "/tmp/stop_pod.sh", "True")
        for node in self.nodes:
            sftp = self.ssh_dict[node].open_sftp()
            sftp.put("/tmp/start_pod.sh", '/tmp/start_pod.sh')
            sftp.put("/tmp/cluster-restore-reversed.sh",
                     "/tmp/cluster-restore-reversed.sh")
            sftp.close()

        return self.nodes

    def create_triliosecret(self):
        """
        Function use to get trilio target information
        """
        try:
            ret = self.api_instance.list_node(
                label_selector="node-role.kubernetes.io/master")
            for node in ret.items:
                api_batch = self.api_instance.read_node_status(
                    node.metadata.name)
                my_list = api_batch.status.conditions

                flag = 0
                for i in my_list:
                    if i.type == "Ready" and i.status == "True":
                        self.nodes_dict[node.metadata.name] = next(
                            (addr.address for addr in node.status.addresses if
                             addr.type == "InternalIP"), None)
        except ApiException as exception:
            self.logger.error(f"Error in getting nodes information")
        except BaseException as exception:
            self.logger.error(f"Error in getting nodes information")
            self.logger.error(exception)
            sys.exit(1)

        if not self.nodes_dict:
            self.logger.error("No node is in healthy state..Exiting")
            return 1

        pod_list = self.api_instance.list_namespaced_pod(
            namespace=f'{self.etcdns}', label_selector='app=etcd,etcd=true')
        for pod in pod_list.items:
            pod_tuple = next(((pod.spec.node_name, pod.metadata.name)
                             for st in pod.status.conditions if st.type == \
                              "ContainersReady" and st.status == "True"),
                             None)
            self.etcd_pods[pod_tuple[0]] = pod_tuple[1]
        etcd_node_name = next(iter(self.nodes_dict))
        for i in [
            'accessKey',
            'accessKeyID',
            'regionName',
            's3Bucket',
            's3EndpointUrl',
            'storageNFSSupport',
                'name']:
            command = [
                '/bin/sh',
                '-c',
                f'ETCDCTL_ENDPOINTS=https://{self.nodes_dict[etcd_node_name]}:2379 etcdctl get /{i}']
            try:
                resp = stream(
                    self.api_instance.connect_get_namespaced_pod_exec,
                    f"{self.etcd_pods[etcd_node_name]}",
                    self.etcdns,
                    command=command,
                    container='etcdctl',
                    stderr=True,
                    stdin=True,
                    stdout=True,
                    tty=False)
            except ApiException as exception:
                self.logger.error(
                    "Error in getting target info from pod "
                    f"{self.etcd_pods[etcd_node_name]} in namespace "
                    f"{self.etcdns}")
            except BaseException as exception:
                self.logger.error(
                    "Error in getting target info from pod "
                    f"{self.etcd_pods[etcd_node_name]} in namespace "
                    f"{self.etcdns}")
                self.logger.error(exception)
                sys.exit(1)
            try:
                self.s3_info[i] = resp.splitlines()[1]
            except IndexError as exception:
                self.logger.error(
                    "Error in getting target information "
                    "where the backup is stored, please check if "
                    "atleast one backup is performed or there are some changes"
                    " in etcd")
        trilio_secret = """
datastore:
- metaData:
    accessKey: "{access_key}"
    accessKeyID: "{access_id}"
    objectLockingEnabled: false
    regionName: region
    s3Bucket: "{bucket}"
    s3EndpointUrl: "{url}"
    storageDasDevice: none
    storageNFSSupport: TrilioVault
  name: {name}
  storageType: s3
""".format(access_key=self.s3_info['accessKey'],
           access_id=self.s3_info['accessKeyID'],
           region=self.s3_info['regionName'],
           bucket=self.s3_info['s3Bucket'],
           url=self.s3_info['s3EndpointUrl'],
           name=self.s3_info['name'])

        secret_file = open("trilio-secret", "w")
        secret_file.write(trilio_secret)
        secret_file.close()
    
        return self.s3_info['name']

    def get_nodes(self):
        """
        Function to get ssh connectivity of Ready nodes
        """
        try:
            ret = self.api_instance.list_node(
                label_selector="node-role.kubernetes.io/master")
            for node in ret.items:
                ret_resp = api_instance.read_node_status(node.metadata.name)
                node_conditions = ret_resp.status.conditions
                for condition in node_conditions:
                    if (condition.type == 'Ready' and condition.status == 'True'):
                        self.nodes.append(node.metadata.name)
        except ApiException as exception:
            self.logger.error(f"Error in getting nodes information")
        except BaseException as exception:
            self.logger.error(f"Error in getting nodes information")
            self.logger.error(exception)
            sys.exit(1)
        for host in self.nodes:
            ret_code = get_ssh_connection(host, self.ssh_dict)
            if ret_code != 0:
                self.create_ssh_connectivity_between_nodes()


    def check_and_approve_csr(self):
        """
        Function to get and approve pending CSRs
        """
        try:
            cert_instance = client.CertificatesV1Api()
            resp = cert_instance.list_certificate_signing_request()
        except BaseException as exception:
            self.logger.error(f"Error in listing CSR certificates")
            self.logger.error(exception)
            self.logger.info("Please run the plugin with -p option "\
                    "i.e. try post restore task again")
            sys.exit(1)
        csrlist = []
        for i in resp.items:
            if i.status.conditions is None:
                csrlist.append(i.metadata.name)
        if csrlist:
            self.logger.info("Approving pending CSR's")
            for cert in csrlist:
                cmd = f'oc adm certificate approve {cert}'
                proc = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    shell=True)
                output, err = proc.communicate()
                if proc.returncode:
                    print(f"CSR {csr} Approval failed")
                    print("Please check CSR and run post restore tasks")
                    sys.exit(1)
                print(output)

    def post_restore_task(self, server, user, passwd):
        # restart kubelet on all nodes
        # for host in self.nodes:
        #  get_ssh_connection(host, self.ssh_dict)
        # Check if all required pods are up on recovery node
        self.check_ssh_connectivity()
        runtime = 30
        start = int(time.time())
        wait_timeout = start + 60 * runtime
        ret_code_dict = dict()
        ret_code_list = []
        spin = '-\\|/'
        idx = 0
        self.logger.info("Waiting for etcd,kube-apiserver,"
                         "kube-controller-manager,kube-schedule pod to be up "
                         "and running..")
        while True:
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.2)
            stdin, stdout, stderr = self.ssh_dict[self.nodes[0]].exec_command(
                'sudo crictl ps | grep "etcd " | grep Running')
            ret_code = stdout.channel.recv_exit_status()
            ret_code_dict["etcd"] = ret_code
            stdin, stdout, stderr = self.ssh_dict[self.nodes[0]].exec_command(
                'sudo crictl ps | grep "kube-apiserver" | grep Running')
            ret_code1 = stdout.channel.recv_exit_status()
            ret_code_dict["kube-apiserver"] = ret_code1
            stdin, stdout, stderr = self.ssh_dict[self.nodes[0]].exec_command(
                'sudo crictl ps | grep "kube-controller-manager" | grep Running')
            ret_code2 = stdout.channel.recv_exit_status()
            ret_code_dict["kube-controller-manager"] = ret_code2
            stdin, stdout, stderr = self.ssh_dict[self.nodes[0]].exec_command(
                'sudo crictl ps | grep "kube-schedule" | grep Running')
            ret_code3 = stdout.channel.recv_exit_status()
            ret_code_dict["kube-schedule"] = ret_code3
            if all(value == 0 for value in ret_code_dict.values()):
                break
            if int(time.time()) >= wait_timeout:
                ret_code_list = [key for key,
                                 val in ret_code_dict.items if val != 0]
                self.logger.error('Timed out while waiting for static pods '
                                  f'{ret_code} to start on node '
                                  f'{self.ssh_dict[self.nodes[0]]}')
                sys.exit(1)
        for node in self.nodes:
            stdout = self.ssh_dict[node].exec_command(
                'sudo systemctl restart kubelet.service')[1]
            for line in stdout:
                # Process each line in the remote output
                print(line)
            runtime = 10
            start = int(time.time())
            wait_timeout = start + 60 * runtime
            status = 'inactive'
            for host in self.nodes:
                get_ssh_connection(host, self.ssh_dict)
            while True:
                ret = self.ssh_dict[node].exec_command(
                    "sudo systemctl status kubelet.service | "
                    "grep Active | awk '{print $2}'")[1]
                status = [line for line in ret]
                if status[0].strip('\n') == 'active':
                    break
                if int(time.time()) >= wait_timeout:
                    self.logger.error(
                        'Timed out while waiting for kubelet to '
                        f'start on node {node}')
                    sys.exit(1)

        runtime = 20
        # After kubelet is active, check static pods on all nodes
        start = int(time.time())
        wait_timeout = start + 60 * runtime
        spin = '-\\|/'
        idx = 0
        print("Waiting for etcd pod to come up..")
        while True:
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.1)
            stdin, stdout, stderr = self.ssh_dict[self.nodes[0]].exec_command(
                'sudo crictl ps | grep "etcd " | grep Running')
            ret_code = stdout.channel.recv_exit_status()
            if ret_code == 0:
                break
            if int(time.time()) >= wait_timeout:
                self.logger.error(
                    f'Timed out while waiting for static pod {node} '\
                    'to be in Running state')
                self.logger.info("Please run post restore task again")
                sys.exit(1)
        runtime = 15
        start = int(time.time())
        wait_timeout = start + 60 * runtime
        spin = '-\\|/'
        idx = 0
        while True:
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.1)
            if int(time.time()) >= wait_timeout:
                self.logger.error(
                    'Timed out while waiting for all etcd pods to be '\
                    'in Running state')
                self.logger.info("Please run post restore task again")
                sys.exit(1)
            time.sleep(5)
            cmd = "kubectl get pods -n openshift-etcd | grep -v "\
                "etcd-quorum-guard | grep etcd | grep Running"
            proc = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                shell=True)
            output, err = proc.communicate()
            if proc.returncode:
                err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
                self.logger.warning("Error in getting etcd pod status, "\
                                  "check if user is logged in")
                time.sleep(10)
                self.logger.warning(err_msg)
                self.logger.warning("Lost cluster accessibility, trying to "\
                                  "login again")
                ret_val = login_cluster(server, user, passwd, self.logger)
                if ret_val:
                    self.logger.warning("Error in logging..trying again")
                else:
                    config.load_kube_config()
                    self.api_instance = client.CoreV1Api()
                    self.api_batch = client.BatchV1Api()
                    configuration.assert_hostname = False
                continue
            nlines = output.count(b'\n')
            if nlines >= 1:
                break
        self.check_and_approve_csr()
        while True:
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.1)
            stdin, stdout, stderr = self.ssh_dict[self.nodes[0]].exec_command(
                'sudo crictl ps | grep "etcd " | grep Running')
            ret_code = stdout.channel.recv_exit_status()
            if ret_code == 0:
                break
            if int(time.time()) >= wait_timeout:
                self.logger.error(
                    f'Timed out while waiting for static pod {node} '\
                    'to be in Running state')
                self.logger.info("Please run post restore task again")
                sys.exit(1)
        nodes_len = len(self.nodes)
        patch_and_verify_nodes_pods(
            group="operator.openshift.io",
            version="v1",
            plural="etcds",
            name="cluster",
            nodes_len=nodes_len,
            logger=self.logger,
            field_manager="MergePatch")
        patch_and_verify_nodes_pods(
            group="operator.openshift.io",
            version="v1",
            plural="kubeapiservers",
            name="cluster",
            nodes_len=nodes_len,
            logger=self.logger,
            field_manager="MergePatch")
        patch_and_verify_nodes_pods(
            group="operator.openshift.io",
            version="v1",
            plural="kubecontrollermanagers",
            name="cluster",
            nodes_len=nodes_len,
            logger=self.logger,
            field_manager="MergePatch")
        patch_and_verify_nodes_pods(
            group="operator.openshift.io",
            version="v1",
            plural="kubeschedulers",
            name="cluster",
            nodes_len=nodes_len,
            logger=self.logger,
            field_manager="MergePatch")
        runtime = 20
        start = int(time.time())
        wait_timeout = start + 60 * runtime
        spin = '-\\|/'
        idx = 0
        self.logger.info("Post restore, checking if the etcd pod on "
                         "all nodes  are up and running...")
        while True:
            print(spin[idx % len(spin)], end="\r")
            idx += 1
            time.sleep(0.1)
            if int(time.time()) >= wait_timeout:
                self.logger.error(
                    'Timed out while waiting for all etcd pods to be in '
                    'Running state')
                sys.exit(1)
            cmd = "kubectl get pods -n openshift-etcd | grep -v"\
                " etcd-quorum-guard | grep etcd | grep Running"
            proc = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                shell=True)
            output, err = proc.communicate()
            if proc.returncode:
                err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
                self.logger.error(err_msg)
                self.logger.warning("Error in getting etcd pod status, "
                                  "check if user is logged in")
                time.sleep(5)
                self.logger.warning("Lost cluster accessibility, trying "
                                  "to login again")
                login_cmd = input(
                    'Please access console and provide the token command: ')
                log_proc = subprocess.Popen(
                    login_cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    shell=True)
                log_out, log_err = log_proc.communicate()
                if log_proc.returncode:
                    self.logger.warning("Error in logging..trying again")
                continue
            nlines = output.count(b'\n')
            if nlines == nodes_len:
                break
        self.logger.info("Restore is successfully completed!")


def patch_and_verify_nodes_pods(
        group,
        version,
        plural,
        name,
        nodes_len,
        logger,
        field_manager="MergePatch"):
    """
    Function to Patch and verify nodes
    """
    datime = datetime.datetime.now(datetime.timezone.utc)
    body = {
        "spec":
        {
            "forceRedeploymentReason": f"recovery-{datime.isoformat()}"
        }
    }
    # get revision and number of nodes
    retry = 5
    while retry > 0:
        try:
            resp = client.CustomObjectsApi().get_cluster_custom_object_status(
                group=group, version=version, plural=plural, name=name)
            old_rev = resp["status"]["latestAvailableRevision"]
            break
        except ApiException as exception:
            logger.warning(
                f"Exception when getting {plural} {name} info using "
                f"get_cluster_custom_object_status - {exception}")
            logger.info("Retrying...")
        except BaseException as exception:
            logger.warning(f"BaseException caught before patching {exception}")
            logger.warning(
                "Exception when getting {plural} {name} pod status through "
                "CustomObjectsApi")
            logger.info("Retrying it again..")
            config.load_kube_config()
            configuration.assert_hostname = False
        retry = retry - 1
    if retry <= 0:
        logger.info("Restore is completed, just run post_restore_task")
        sys.exit(1)
    try:
        resp = client.CustomObjectsApi()
        resp.patch_cluster_custom_object(
            group=group,
            version=version,
            plural=plural,
            name=name,
            body=body,
            field_manager=field_manager)
        logger.info(f"Patched {plural}")
        time.sleep(5)
    except ApiException as exception:
        logger.error(
            "Exception when patching {plural} {name} for redeployment "
            "through CustomObjectsApi - {exception}")
        logger.info("Restore is completed, just run post_restore_task")
        sys.exit(1)

    # Verify all node
    runtime = 20
    start = int(time.time())
    wait_timeout = start + 60 * runtime
    new_rev = old_rev + 1
    reason = ""
    print(
        "Waiting for all nodes to be at latest version "
        f"after patching {plural}")
    retry = 5
    spin = '-\\|/'
    idx = 0
    while retry > 0:
        try:
            old_msg = ""
            while True:
                print(spin[idx % len(spin)], end="\r")
                idx += 1
                time.sleep(0.1)
                if int(time.time()) >= wait_timeout:
                    logger.error(
                        'Timed out while waiting for all nodes to be at '
                        'new etcd cluster revision')
                    sys.exit(1)
                resp = client.CustomObjectsApi().get_cluster_custom_object(
                    group=group, version=version, plural=plural, name=name)
                val_dict = resp["status"]["conditions"]
                status = [i for i in val_dict if i["type"]
                          == 'NodeInstallerProgressing']
                message = status[0]['message']
                if old_msg == "" or old_msg != message:
                    old_msg = message
                    logger.info(f"After patching {plural}, out of {nodes_len}, "\
                        f"{message}")
                if message == f"{nodes_len} nodes are at revision {new_rev}":
                    reason = status[0]['reason']
                    if reason == "AllNodesAtLatestRevision":
                        logger.info(
                            "All nodes are at the latest revision after "
                            f"{plural} {name} redeployment")
                        break
        except ApiException as exception:
            logger.warning(
                f"Exception when getting {plural} {name} pod status through "
                "CustomObjectsApi")
            logger.info("Retrying it again..")
            config.load_kube_config()
            api_instance = client.CoreV1Api()
            api_batch = client.BatchV1Api()
            configuration.assert_hostname = False
            time.sleep(15)
        except BaseException as exception:
            logger.warning(f"BaseException caught after patching {exception}")
            logger.warning(
                f"Exception when getting {plural} {name} pod status "
                "through CustomObjectsApi")
            logger.info("Retrying it again..")
            config.load_kube_config()
            configuration.assert_hostname = False
            time.sleep(15)
        if reason == "AllNodesAtLatestRevision":
            break
        retry = retry - 1
    if retry <= 0:
        logger.info("Restore is completed, just run post_restore_task")
        sys.exit(1)


def get_ssh_connection(host, ssh_dict):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(host, username='core', key_filename='private.pem')
        ssh_dict[host] = ssh_client
    except paramiko.SSHException as sshexception:
        print(f"Unable to establish SSH connection: {sshexception}")
        return 1
    except BaseException as exception:
        print(f"Unable to establish SSH connection: {exception}")
        return 1
    return 0

def workon(host, ssh_dict, file_path, get_ssh="True"):
    # Connect to remote host
    if get_ssh == "True":
        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_client.connect(
                host,
                username='core',
                key_filename='private.pem')
            print("copying file")
            # Setup sftp connection and transmit this script
            sftp = ssh_client.open_sftp()
            sftp.put(file_path, file_path)
            sftp.close()
        except paramiko.SSHException as sshexception:
            print(f"Unable to establish SSH connection: {sshexception}")
            sys.exit(1)
        except BaseException as exception:
            print(f"Unable to establish SSH connection: {exception}")
            sys.exit(1)

    # Run the transmitted script remotely without args and show its output.
    # SSHClient.exec_command() returns the tuple (stdin,stdout,stderr)
    if get_ssh == "False":
        ssh_client = ssh_dict[host]
    stdout = ssh_client.exec_command(f'sh {file_path}')[1]
    for line in stdout:
        # Process each line in the remote output
        print(line)

    ssh_dict[host] = ssh_client


def main(nodes, ssh_dict, file_path, get_ssh):
    """
    Function to create thread to execute file on different nodes
    """
    threads = []
    for node in nodes:
        # print(h)
        thread = threading.Thread(target=workon, args=(
            node, ssh_dict, file_path, get_ssh,))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


def get_target_secret_credentials(
        api_instance,
        secret_name,
        secret_namespace,
        logging):
    """
    Function to get TVK target secret credentials
    """
    access_key = ""
    secret_key = ""
    try:
        if secret_name != "":
            secret = api_instance.read_namespaced_secret(
                name=secret_name, namespace=secret_namespace)
            access_key = base64.b64decode(
                secret.data['accessKey']).decode('utf-8')
            secret_key = base64.b64decode(
                secret.data['secretKey']).decode('utf-8')
            if access_key == "":
                logging.error(
                    'Unable to get access key for ObjectStore from secret')
            if secret_key == "":
                logging.error(
                    'Unable to get secret key for ObjectStore from secret')
    except ApiException as e:
        logging.error('Error while getting Secret :', e.reason)
    except BaseException as e:
        logging.error(e)
    finally:
        return access_key.strip(), secret_key.strip()


def login_cluster(server, user, password, logger):
    args = init()
    #Connect kuberenets cluster
    cmd = f"oc login {server} --username={user} --password={password} --insecure-skip-tls-verify"
    proc = subprocess.Popen(cmd, stderr=sys.stderr,
                            stdout=sys.stdout, shell=True)
    proc.communicate()
    if proc.returncode:
        err_msg = f"command :{cmd}, exitcode :{proc.returncode}"
        logger.error("Error while logging cluster")
        logger.error(err_msg)
        return(1)
    return(0)


def check_objects(obj, filename):
    """
    function to check if backup files are present in provided filename
    """
    #checking if backup files are available in target
    session = boto3.session.Session()
    s3 = session.resource(service_name='s3',
                      aws_access_key_id=obj.s3_info['accessKeyID'],
                      aws_secret_access_key=obj.s3_info['accessKey'],
                      endpoint_url=obj.s3_info['s3EndpointUrl'])

    if s3:
        bucket = s3.Bucket(obj.s3_info['s3Bucket'])
        if bucket:
            objs = list(bucket.objects.filter(Prefix=f"{filename}/"))
            if len(objs) >= 2:
                obj.logger.info("Backup fils are present in target")
            else:
                obj.logger.error("No backup files found, please check if "\
                        "files are present and retry..")
                return 1
        else:
            obj.logger.error("No bucket is present in specified "\
                    "target..exiting..")
            return 1
    else:
        obj.logger.error("Error in getting s3 object, please check credentials..")
        return 1


def get_dict_object(
        api_instance,
        custom_api,
        target_name,
        target_namespace,
        logger):
    """
    Function to get target information from TVK target CRD
    """
    #import pdb; pdb.set_trace()
    TARGET_CRD_GROUP = 'triliovault.trilio.io'  # str | the custom resource's group
    TARGET_CRD_PLURAL = 'targets'  # str | the custom resource's plural name.
    TARGET_CRD_VERSION = 'v1'  # str | the custom resource's version
    try:
        response = custom_api.get_namespaced_custom_object(
            TARGET_CRD_GROUP,
            TARGET_CRD_VERSION,
            target_namespace,
            TARGET_CRD_PLURAL,
            target_name)
    except ApiException as exception:
        logger.error("Exception in getting Target {target_name} info")
    except BaseException as exception:
        logger.error("Exception in getting Target {target_name} info")
        logger.error(exception)
    if 'url' in response["spec"]["objectStoreCredentials"]:
        s3_endpoint_url = response["spec"]["objectStoreCredentials"]["url"]
    if 'credentialSecret' in response["spec"]["objectStoreCredentials"]:
        secret_name = response["spec"]["objectStoreCredentials"][
            "credentialSecret"]["name"]
        secret_namespace = response["spec"]["objectStoreCredentials"][
            "credentialSecret"]["namespace"]
        access_key_id, access_key = get_target_secret_credentials(
            api_instance, secret_name, secret_namespace, logger)

    else:
        access_key_id = response["spec"]["objectStoreCredentials"]["accessKey"]
        access_key = response["spec"]["objectStoreCredentials"]["secretKey"]

    obj_dict = {
        'id': response["metadata"]["uid"],
        'storageType': response["spec"]["type"],
        'name': response["metadata"]["name"],
        'namespace': response["metadata"]["namespace"],
        'accessKeyID': access_key_id,
        'accessKey': access_key,
        's3Bucket': response["spec"]["objectStoreCredentials"]["bucketName"],
        'regionName': response["spec"]["objectStoreCredentials"]["region"],
        'storageNFSSupport': "TrilioVault",
        's3EndpointUrl': s3_endpoint_url,
        'vendor': response["spec"]["vendor"]
    }
    return obj_dict


def init():
    try:
        parser = argparse.ArgumentParser(
            "ETCD Backup and restore on OCP. Available flags: "
            "-backup -restore.")
        parser.add_argument('-backup', action="store_true")
        parser.add_argument('-restore', action="store_true")
        parser.add_argument(
            '--target-name',
            dest="target_name",
            help="The name of a single datastore on which etcd backup needs "
            "to be shared. Target should be created in same namespace "
            "in which TVK is installed")
        parser.add_argument('--target-namespace', dest="target_namespace",
                            help="Namespace name where the target resides "
                            "or TVK is installed.")
        parser.add_argument('--api-server-url', dest="api_server_url",
                            help="Api server URL to login cluster.",
                            required=True)
        parser.add_argument('--ocp-cluster-user', dest="ocp_cluster_user",
                            help="username used to login cluster.",
                            required=True)
        parser.add_argument('--ocp-cluster-pass', dest="ocp_cluster_pass",
                            help="password to login cluster",
                            required=True)
        parser.add_argument('-p', action='store_true',
                       help="If users want to run only post restore tasks")
        parser.add_argument(
            '--log-location',
            dest="log_loc",
            help="Log file name along with path where the logs should be save"
            " default - /tmp/etcd-ocp-backup.log")

        args = parser.parse_args()

        return args
    except Exception as ex:
        logging.exception(ex)
        sys.exit(1)


if __name__ == '__main__':

    args = init()


    # Gets or creates a logger
    logger = logging.getLogger(__name__)

    # set log level
    logger.setLevel(logging.DEBUG)

    #Connect kuberenets cluster
    ret_val = login_cluster(args.api_server_url, 
            args.ocp_cluster_user, args.ocp_cluster_pass, logger)
    if ret_val:
        sys.exit()

    # Create kubernetes client object
    config.load_kube_config()
    api_instance = client.CoreV1Api()
    api_batch = client.BatchV1Api()
    custom_api = client.CustomObjectsApi()
    configuration.assert_hostname = False


    # define file handler and set formatter
    if not args.log_loc:
        log_loc = "/tmp/etcd-ocp-backup.log"
    else:
        log_loc = args.log_loc
    file_handler = logging.FileHandler(log_loc)
    formatter = logging.Formatter(
        '%(asctime)s : %(levelname)s : %(name)s : %(message)s')
    file_handler.setFormatter(formatter)

    # add file handler to logger
    logger.addHandler(file_handler)
    logging.getLogger("urllib3").setLevel(logging.DEBUG)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)
   
    if args.backup is True:
        if not args.target_name or not args.target_namespace \
                or not args.api_server_url or not args.ocp_cluster_user \
                or not args.ocp_cluster_pass:
            print("For backup, user would need to provide "\
                    " logging credentials and target_name and its namespace")
            sys.exit()
        etcd_bk = ETCDOcpBackup(api_instance, api_batch, custom_api, logger)
        etcd_bk.create_backup_job()
        etcd_bk.create_backup_mover(args.target_name, args.target_namespace)
        etcd_bk.delete_jobs(mover="true", backup="true")
        print("storing target info..")
        etcd_bk.store_target_data_to_etcd(
            args.target_name, args.target_namespace)
    elif args.restore is True:
        etcd_bk = ETCDOcpRestore(api_instance, api_batch, logger)
        if not args.api_server_url or not args.ocp_cluster_user \
                or not args.ocp_cluster_pass:
            print("Please provide server, user and password to login cluster")
            sys.exit()
        if args.p is False:
            target_name = etcd_bk.create_triliosecret()
            #import pdb; pdb.set_trace()
            etcd_bk.create_ssh_connectivity_between_nodes()
            restore_path = etcd_bk.create_metamover_and_display_available_restore(
                target_name, "trilio-secret")
            nodes = etcd_bk.stop_static_pods()

            etcd_bk.create_restore_job(restore_path, args.api_server_url,
                    args.ocp_cluster_user, args.ocp_cluster_pass)
            etcd_bk.post_restore_task(args.api_server_url,
                    args.ocp_cluster_user, args.ocp_cluster_pass)
        else:
            #import pdb; pdb.set_trace()
            nodes = etcd_bk.get_nodes()
            etcd_bk.post_restore_task(args.api_server_url, 
                    args.ocp_cluster_user, args.ocp_cluster_pass)
    else:
        print("Please select at least one flag from backup and restore")
