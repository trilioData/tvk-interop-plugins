import errno
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime as dt
from kubernetes import client, config
from kubernetes.stream import stream
from kubernetes.client import configuration
from kubernetes.client.rest import ApiException
import random
import base64
import string
import sys
from shutil import copy2
import threading
from subprocess import DEVNULL, STDOUT
import subprocess
import time
import logging
import argparse


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
    #self.sleeper = sleeper
    #self.timer = timer
    kube_ns = api_instance.read_namespace(name="kube-system")
    self.kube_uid = kube_ns.metadata.uid
    self.etcd_dir = "tvk_etcd_bk_{1}_{0}".format(dt.now().strftime('%Y-%m-%d_%H-%M-%S'), self.kube_uid)
    self.etcd_backup_dir = os.path.join("/etc/kubernetes/static-pod-resources/etcd-member/", self.etcd_dir)
    

  def wait_for_job_success(
        self,
        job_name,
        namespace,
        wait_msg,
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
    wait_timeout = start + 60*runtime
    spin = '-\|/'
    idx=0
    # Ensure we found the job that we launched
    print(wait_msg)
    while not job:
      print(spin[idx % len(spin)], end="\r")
      idx += 1
      time.sleep(0.1)
      if int(time.time()) >= wait_timeout:
        self.logger.error('Timed out while waiting for job to launch')
        break
      #print(job_name)
      #print(namespace)
      jobs = self.api_batch.list_namespaced_job(namespace=namespace)
      job = next((j for j in jobs.items if j.metadata.name == job_name), None)
      #print(job) 
      #sys.exit()
      if not job:
        #print("I am here")
        self.logger.error('Job "{job_name}" not yet launched, waiting'.format(job_name=job_name))
        time.sleep(wait_time_between_attempts)

    #print("I am here")
    # Wait for job completed status#
    wait_timeout = start + 60*runtime
    spin = '-\|/'
    idx=0
    while True:
      print(spin[idx % len(spin)], end="\r")
      idx += 1
      time.sleep(0.1)
      if int(time.time()) >= wait_timeout:
        self.logger.error('Timed out while waiting for job to complete')
        break
      status = self.api_batch.read_namespaced_job_status(job_name, namespace=namespace).status
      if status.failed and status.failed > 0:
        self.logger.error('Encountered failed job pods with status: %s' % str(status))
      #print(status)
      # done waiting for pod completion
      if status.succeeded == num_pods_to_wait_for:
        break

  def create_backup_job(self):

    #create ranndo job name
    N = 3

    # generating random strings
    res = ''.join(random.choices(string.ascii_lowercase +
                             string.digits, k = N))

    self.bk_job_name = 'openshift-backup-{0}'.format(res)
    self.backup_ns = "ocp-backup-etcd"
    #create required service account and role_binding
    etcd_backup_job="""
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

    myFile = open("etcd-backup_job.yaml", "w")
    myFile.write(etcd_backup_job)
    myFile.close()

    cmd="kubectl apply -f etcd-backup_job.yaml 1>/dev/null 2>etcd-ocp-backup.log"
    proc = subprocess.Popen(cmd, stderr=sys.stderr, stdout=sys.stdout, shell=True)
    proc.communicate()
    if proc.returncode:
      err_msg = "command :{}, exitcode :{}".format(cmd, proc.returncode)
      self.logger.error(err_msg)
      retunr(1)

    cmd = "oc adm policy add-scc-to-user privileged -z openshift-backup -n ocp-backup-etcd;oc adm policy add-scc-to-user anyuid -z openshift-backup -n ocp-backup-etcd;oc adm policy add-cluster-role-to-user cluster-admin -z openshift-backup -n ocp-backup-etcd"

    proc = subprocess.Popen(cmd, stderr=None, stdout=DEVNULL, shell=True)
    proc.communicate()
    if proc.returncode:
      err_msg = "command :{}, exitcode :{}".format(cmd, proc.returncode)
      self.logger.error(err_msg)
      return(1)
    self.wait_for_job_success(self.bk_job_name, "ocp-backup-etcd", "Waiting for backup job to complete..")


  def store_target_data_to_etcd(self, target_name, target_namespace):
    #get pod list

    pod_list = self.api_instance.list_namespaced_pod(namespace='{0}'.format(self.etcdns), label_selector='app=etcd,etcd=true')
    for pod in pod_list.items:
      pod_tuple=next(((pod.spec.node_name, pod.metadata.name) for st in pod.status.conditions if st.type == "ContainersReady" and st.status == "True"), None) 
      self.etcd_pods[pod_tuple[0]] = pod_tuple[1]
    node_list = self.nodes
    obj_dict = get_dict_object(self.api_instance, self.custom_api, target_name, target_namespace, self.logger)
    for key1, val1 in obj_dict.items():
      #print("{0} {1}".format(key1, val1))
      for key,val in node_list.items():
        #command = ['/bin/bash', '-c', 'echo "hello"']
        command =  ['/bin/sh', '-c', 'ETCDCTL_ENDPOINTS=https://{0}:2379 etcdctl put /{1} {2}'.format(val, key1, val1)]
        resp = stream(self.api_instance.connect_get_namespaced_pod_exec, "{0}".format(self.etcd_pods[key]), self.etcdns,
              command=command,container='etcdctl',
              stderr=True, stdin=True,
              stdout=True, tty=False)
        #print("Response: " + resp)

    
  def delete_jobs(self, mover="true", backup="true"):

    if mover == "true":
        #get self.mover_nsi
        delete = self.api_batch.delete_namespaced_job(name=self.mover_job_name, body=client.V1DeleteOptions(), namespace=self.mover_ns)
        
    if backup == "true":
        delete = self.api_batch.delete_namespaced_job(name=self.bk_job_name, body=client.V1DeleteOptions(), namespace=self.backup_ns)

    return(delete)

  def create_backup_mover(self, target_name, target_ns="default"):
    N = 3
    # generating random strings
    res = ''.join(random.choices(string.ascii_lowercase, k = N))
 
    try:
      response = self.custom_api.list_cluster_custom_object(group="triliovault.trilio.io", version="v1", plural="triliovaultmanagers")
    except ApiException as e:
      print("Exception in getting TVK info")
      print(e)
      sys.exit(1)
    except BaseException as e:
      print("Exception in getting TVK info")
      print(e)
      sys.exit(1)
    TVK_ns=response['items'][0]['metadata']['namespace']
    serviceAccount="k8s-triliovault"
    serviceAccountName="k8s-triliovault"
    metamoverpod="etcd-datamover-{0}".format(str(res))
  
    #target_name = "demo-s3-target1"
    #target_ns = "default"

    #get healthy node
    #bk_node = 'oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{{range .items[*]}} {{.metadata.name}} {{" "}} {{.status.conditions[?(@.type=="Ready")].status}} {{" "}} {{"\\n"}} {{end}}' --no-headers | awk '$2=="True" {{ print $1}}' | head -1 | xargs -I {{}} --  oc debug node/{{}} -- bash -c 'chroot /host sudo -E'
    node_name = None
    ret = self.api_instance.list_node(label_selector="node-role.kubernetes.io/master")
    for node in ret.items:
      api_batch = self.api_instance.read_node_status(node.metadata.name)
      my_list=api_batch.status.conditions

      flag=0
      for i in my_list:
        if i.type == "Ready" and i.status == "True":
         self.nodes[node.metadata.name] = next((addr.address for addr in node.status.addresses if addr.type == "InternalIP"), None)

    if self.nodes:
      node_name = next(iter(self.nodes))
      self.logger.info("Taking backup on node {0}, please do not power off this machine".format(node_name))
    else:
      self.logger.error("No node is in healthy state..Exiting")
      return 1

    self.mover_job_name=metamoverpod
    self.mover_ns=TVK_ns
    #Copy code from storage to control plane
    metamover_pod="""
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
""".format(metamoverpod, target_ns, target_name, self.etcd_dir, serviceAccount, serviceAccountName, TVK_ns, node_name)

    myFile = open("metamover_pod.yaml", "w")
    myFile.write(metamover_pod)
    myFile.close()

    cmd="kubectl apply -f metamover_pod.yaml 1>/dev/null 2>etcd-ocp-backup.log"
    proc = subprocess.Popen(cmd, stderr=sys.stderr, stdout=sys.stdout, shell=True)
    proc.communicate()
    if proc.returncode:
      err_msg = "command :{}, exitcode :{}".format(cmd, proc.returncode)
      self.logger.error(err_msg)
      return(1)
    self.wait_for_job_success(self.mover_job_name, TVK_ns, "Waiting for moving backup to target..")
    logger.info("ETCD backup is completed")
    print("ETCD backup is completed and is stored with name: {0}".format(self.etcd_dir))


"""
    #get pod name created by job
    pod_name = None
    api_response = self.api_instance.list_namespaced_pod(namespace=TVK_ns, label_selector="job-name={0}".format(metamoverpod))
    for pod in api_response.items:
      pod_name=pod.metadata.name
    
    exec_command = ['/bin/bash', '-c', '"/usr/bin/python3 /opt/tvk/datastore-attacher/mount_utility/mount_by_target_crd/mount_datastores.py --target-namespace=etcd-manual --target-name=demo-s3-target1"']
    print("metamover pod name is {0}".format(pod_name))
    print("TVK_ns = {0}".format(TVK_ns))
    resp = stream(self.api_instance.connect_get_namespaced_pod_exec, pod_name, TVK_ns,
              command=exec_command,
              stderr=True, stdin=False,
              stdout=True, tty=False)
    print("Response: " + resp)
    exec_command = ['/bin/bash', '-c', 'cp /tmp/{0} /triliodata-temp/'.format(etcd_backup_dir)]
    resp = stream(self.api_instance.connect_get_namespaced_pod_exec, pod_name, TVK_ns,
              command=exec_command,
              stderr=True, stdin=True,
              stdout=True, tty=True)
    print("Response: " + resp)
"""
    

def get_target_secret_credentials(api_instance, secret_name, secret_namespace, logging):
  access_key = ""
  secret_key = ""
  try:
    if secret_name != "":
      secret = api_instance.read_namespaced_secret(name=secret_name, namespace=secret_namespace)
      access_key = base64.b64decode(secret.data['accessKey']).decode('utf-8')
      secret_key = base64.b64decode(secret.data['secretKey']).decode('utf-8')
      if access_key == "":
        logging.info('Unable to get access key for ObjectStore from secret')
      if secret_key == "":
        logging.info('Unable to get secret key for ObjectStore from secret')
  except ApiException as e:
    logging.error('Error while getting Secret :', e.reason)
  except BaseException as e:
    logging.error(e)
  finally:
    return access_key.strip(), secret_key.strip()



def get_dict_object(api_instance, custom_api, target_name, target_namespace, logger):
  #import pdb; pdb.set_trace()
  TARGET_CRD_GROUP = 'triliovault.trilio.io'  # str | the custom resource's group
  TARGET_CRD_PLURAL = 'targets'  # str | the custom resource's plural name.
  TARGET_CRD_VERSION = 'v1'  # str | the custom resource's version
  response = custom_api.get_namespaced_custom_object(TARGET_CRD_GROUP, TARGET_CRD_VERSION, target_namespace, TARGET_CRD_PLURAL, target_name)
  if 'url' in response["spec"]["objectStoreCredentials"]:
    s3_endpoint_url = response["spec"]["objectStoreCredentials"]["url"]
  if 'credentialSecret' in response["spec"]["objectStoreCredentials"]:
    secret_name = response["spec"]["objectStoreCredentials"]["credentialSecret"]["name"]
    secret_namespace = response["spec"]["objectStoreCredentials"]["credentialSecret"]["namespace"]
    access_key_id, access_key = get_target_secret_credentials(api_instance, secret_name, secret_namespace, logger)
  
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
    parser = argparse.ArgumentParser("ETCD Backup on OCP. Available flags: --target-name --target-namespace.")
    parser.add_argument('--target-name', dest="target_name", required=True,
                       help="The name of a single datastore on which etcd backup needs to be shared")
    parser.add_argument('--target-namespace', dest="target_namespace", help="Namespace name where the target resides.", required=True)
    parser.add_argument('--log-location', dest="log_loc", help="Log file name along with path where the logs should be save. default - /tmp/etcd-ocp-backup.log")


    args = parser.parse_args()

    return(args)
  except Exception as ex:
    logging.exception(ex)
    sys.exit(1)


if __name__ == '__main__':

  # Create kubernetes client object
  config.load_kube_config()
  api_instance = client.CoreV1Api()
  api_batch = client.BatchV1Api()
  custom_api= client.CustomObjectsApi()
  configuration.assert_hostname = False

  args = init()
  # Gets or creates a logger
  logger = logging.getLogger(__name__)  

  # set log level
  #logger.setLevel(logging.WARNING)

  # define file handler and set formatter
  if not args.log_loc:
      log_loc = "/tmp/etcd-ocp-backup.log"
  else:
      log_loc = args.log_loc
  file_handler = logging.FileHandler(log_loc)
  formatter    = logging.Formatter('%(asctime)s : %(levelname)s : %(name)s : %(message)s')
  file_handler.setFormatter(formatter)

  # add file handler to logger
  logger.addHandler(file_handler)
  logging.getLogger("urllib3").setLevel(logging.WARNING)
  etcd_bk = ETCDOcpBackup(api_instance, api_batch, custom_api, logger)
  etcd_bk.create_backup_job()
  etcd_bk.create_backup_mover(args.target_name, args.target_namespace)
  print("storing target info..")
  etcd_bk.store_target_data_to_etcd(args.target_name, args.target_namespace)
  etcd_bk.delete_jobs(mover="true", backup="true")
