import logging
import argparse
import sys
import os
import errno
import json
import yaml
import time
import base64
import urllib
import boto3
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from kubernetes.client.rest import ApiException
from kubernetes.client import configuration
from kubernetes import client, config


class ETCDbackup():
    """This class performs ETCD backup on
    RKE cluster.
    """

    def __init__(
            self,
            logger,
            api_instance,
            custom_api,
            api_batch,
            server_url,
            token,
            target_nm,
            target_ns,
            cluster_name=None):
        self.server_url = server_url
        self.token = token
        self.target_name = target_nm
        self.target_namespace = target_ns
        self.api_instance = api_instance
        self.custom_api = custom_api
        self.api_batch = api_batch
        self.logger = logger
        self.cluster_name = cluster_name
        if self.cluster_name is None:
            self.cluster_name = get_cluster_name()
            if self.cluster_name is None:
                print(
                    "Cluster name is not set in kube-system, please provide through arguments")
                sys.exit(1)
        key_list = self.token.split(":")
        auth = HTTPBasicAuth(
            f"{key_list[0]}", f"{key_list[1]}")
        self.auth = auth
        url = f"{self.server_url}v3/clusters?name={self.cluster_name}"
        resp = requests.get(url, verify=False, auth=self.auth)
        json_resp = resp.json()
        for item in json_resp['data']:
            self.cluster_id = item['id']

    def etcd_bk(self):
        """
        This function is use to perform ETCD backup
        """
        url = f"{self.server_url}v3/etcdbackups"
        target_obj = parse_target(self.api_instance, self.custom_api,
                                  self.target_name, self.target_namespace, self.logger)
        etcdconfig = {
            "clusterId": self.cluster_id,
            "manual": True,
            "name": "",
            "namespaceId": ""}
        if target_obj['certs'] == "":
            s3config = {
                "bucketName": target_obj['s3Bucket'],
                "region": target_obj['regionName'],
                "endpoint": target_obj['s3EndpointUrl'].split("//")[1],
                "accessKey": target_obj['accessKeyID'],
                "secretKey": target_obj['accessKey'],
                "customCa": ""}
        else:
            s3config = {
                "bucketName": target_obj['s3Bucket'],
                "region": target_obj['regionName'],
                "endpoint": target_obj['s3EndpointUrl'].split("//")[1],
                "accessKey": target_obj['accessKeyID'],
                "secretKey": target_obj['accessKey'],
                "customCa": target_obj['certs']}
        print("Checking if cluster target storage is same as provided...")
        url_cluster = f"{self.server_url}v3/clusters/{self.cluster_id}"
        resp_check = requests.get(url_cluster, verify=False, auth=self.auth)
        resp_json = resp_check.json()

        changed = 1
        rke_config = 'rancherKubernetesEngineConfig'
        if resp_json['rancherKubernetesEngineConfig']['services']['etcd']['backupConfig']['s3BackupConfig']:
            for item in 'accessKey', 'bucketName', 'endpoint':
                if s3config[item] != resp_json[rke_config]['services']['etcd']['backupConfig']['s3BackupConfig'].get(item, {
                }):
                    changed = 1
                    break
                else:
                    changed = 0
                    break
        if changed == 0:
            print("Provided S3 target is already set")
        else:
            print("Updating cluster to set new s3 etcd target..")
            resp_json['rancherKubernetesEngineConfig']['services']['etcd']['backupConfig']['s3BackupConfig'] = s3config
            resp_put = requests.put(
                url_cluster,
                verify=False,
                auth=self.auth,
                data=json.dumps(resp_json))
            if resp_put.status_code == 200 or resp_put.status_code == 201:
                runtime = 20
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
                            'Timed out while waiting for backup to complete')
                        break
                    resp_get = requests.get(
                        url_cluster, verify=False, auth=self.auth)
                    json_resp = resp_get.json()
                    if json_resp['state'] == "active" and json_resp['transitioning'] == "no":
                        print("Cluster Updated")
                        break
            else:
                print("Error in setting new etcd target for current cluster")
                sys.exit()
        response = requests.post(
            url,
            verify=False,
            auth=self.auth,
            data=json.dumps(etcdconfig))
        resp_data = response.content
        response_file = json.loads(resp_data.decode('utf-8'))
        print("Backup Started")
        print(
            f"Waiting for backup - {response_file['id']} to complete")
        # wait for ETCD backup to complete
        query = {
            "clusterId": self.cluster_id,
            "created": response_file['created']}
        end_point = urllib.parse.urlencode(query)
        url = f"{self.server_url}v3/etcdbackups?{end_point}"
        runtime = 20
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
                    'Timed out while waiting for backup to complete')
                break
            resp = requests.get(url, verify=False, auth=self.auth)
            json_resp = resp.json()
            status = [
                (i['name'],
                 i['created']) for i in json_resp['data'] for j in i['status']['conditions'] if (
                    j['type'] == 'Completed' and j['status'] == 'True')]
            if status:
                print(
                    f"Backup is completed - {status[0][0]} {status[0][1]}")
                break

# This class is use to holds its data members and member functions
# use to prform ETCD restore


class ETCDrestore():
    """ This class expects user to provide
    object from kubernetes.client.CoreV1Api, kubernetes.client.BatchV1Api,
    kubernetes.client.CustomObjectsApi and kubernetes.client.CoreV1Api,
    kubernetes.client.BatchV1Api, kubernetes.client.CustomObjectsApi
    """

    def __init__(
            self,
            logger,
            api_instance,
            custom_api,
            api_batch,
            server_url,
            token,
            cluster_name=None):
        self.server_url = server_url
        self.token = token
        self.api_instance = api_instance
        self.custom_api = custom_api
        self.api_batch = api_batch
        self.logger = logger
        self.cluster_name = cluster_name
        if self.cluster_name is None:
            self.cluster_name = get_cluster_name()
            # print("cluster name {0}".format(self.cluster_name))
            if self.cluster_name is None:
                print(
                    "Cluster name is not set in kube-system, "
                    "please provide through arguments")
                sys.exit(1)
        key_list = self.token.split(":")
        auth = HTTPBasicAuth(
            f"{ key_list[0]}", f"{key_list[1]}")
        self.auth = auth
        url = f"{self.server_url}/v3/clusters?name={self.cluster_name}"
        resp = requests.get(url, verify=False, auth=self.auth)
        json_resp = resp.json()
        for item in json_resp['data']:
            self.cluster_id = item['id']

    def etcd_rest(self):
        """This function is use to restore ETCD from
        its backup.
        """
        url = f"{self.server_url}v3/etcdbackups"
        query = {"clusterId": self.cluster_id}
        end_point = urllib.parse.urlencode(query)
        url = f"{self.server_url}v3/etcdbackups?{end_point}"
        resp = requests.get(url, verify=False, auth=self.auth)
        json_resp = resp.json()

        data = []
        data_access_key = {}
        max_creation = tuple()
        for i in json_resp['data']:
            status = [(i['name'], i['created']) for j in i['status']['conditions'] if (
                j['type'] == 'Completed' and j['status'] == 'True')]
            if not status:
                if i['backupConfig']['s3BackupConfig'] is None:
                    data_tuple = (
                        i['name'],
                        i['created'],
                        "Local",
                        "NA",
                        "NA",
                        "Unavailable")
                else:
                    data_tuple = (
                        i['name'],
                        i['created'],
                        "S3",
                        i['backupConfig']['s3BackupConfig']['endpoint'],
                        i['backupConfig']['s3BackupConfig']['bucketName'],
                        "Unavailable")
                    data_access_key[i['name']] = [
                        i['backupConfig']['s3BackupConfig'].get(
                            'accessKey', ''),
                        i['backupConfig']['s3BackupConfig']['bucketName']]

            else:
                if i['backupConfig']['s3BackupConfig'] is None:
                    data_tuple = (
                        i['name'],
                        i['created'],
                        "Local",
                        "NA",
                        "NA",
                        "Available")
                else:
                    data_tuple = (
                        i['name'],
                        i['created'],
                        "S3",
                        i['backupConfig']['s3BackupConfig']['endpoint'],
                        i['backupConfig']['s3BackupConfig']['bucketName'],
                        "Available")
                    data_access_key[i['name']] = [i['backupConfig']['s3BackupConfig'][
                        'accessKey'], i['backupConfig']['s3BackupConfig']['bucketName']]
            if len(max_creation) == 0 or max_creation[1] < data_tuple[1]:
                max_creation = data_tuple
            data.append(data_tuple)
        print("Below are the backup and there details")
        # import pdb; pdb.set_trace()
        data_frame = pd.DataFrame.from_records(
            data,
            columns=[
                'Name',
                'Date_Created',
                'Target_Type',
                "Endpoint",
                "Bucket",
                "Availability"])
        data_frame.set_index('Name', inplace=True)
        print(data_frame)
        try:
            restore_id = input(
                f"Please provide the name of backup to restore: ({max_creation[0]})")
        except EOFError:
            restore_id = ""
        if restore_id == "":
            restore_id = max_creation[0]
        s3config = {}
        # get backup info
        query = {"name": restore_id}
        end_point = urllib.parse.urlencode(query)
        bk_url_ext = f"{self.cluster_id}/etcdbackups?{end_point}"
        bk_url = f"{self.server_url}v3/clusters/{bk_url_ext}"
        bk_resp = requests.get(bk_url, verify=False, auth=self.auth)
        if not (bk_resp.status_code == 200 or bk_resp.status_code == 201):
            print("Error in getting selected backup information")
            sys.exit()
        bk_json = bk_resp.json()
        if bk_json["data"][0]["backupConfig"]["s3BackupConfig"]:
            s3storage = 1
            s3config = {}
            bk_name = bk_json["data"][0]["filename"]
            filename = os.path.basename(bk_name)
            for item in 'accessKey', 'bucketName', 'endpoint', 'customCa':
                s3config[item] = bk_json["data"][0]["backupConfig"]["s3BackupConfig"].get(item,
                                                                                          "")

        if restore_id in data_access_key:
            print("\nChecking if cluster target storage is same as provided...")
            url_cluster = f"{self.server_url}v3/clusters/{self.cluster_id}"
            resp_check = requests.get(
                url_cluster, verify=False, auth=self.auth)
            resp_json = resp_check.json()
            changed = 1
            rke_name = 'rancherKubernetesEngineConfig'
            #import pdb; pdb.set_trace()
            if resp_json['rancherKubernetesEngineConfig']['services']['etcd']['backupConfig']['s3BackupConfig']:
                for item in 'accessKey', 'bucketName', 'endpoint', 'customCa':
                    if s3config.get(item, "") != resp_json[rke_name].get('services', {}).get('etcd', {}).get(
                        'backupConfig', {}).get(
                            's3BackupConfig', {}).get(item, {}):
                        changed = 1
                        break
                    else:
                        changed = 0
            if changed == 0:
                print("Provided S3 target is already set")
                secret_key = input(
                    "Please provide secret key for the below s3 target "
                    f"details: \naccessKey: {s3config['accessKey']} "
                    f"\n bucketName: {s3config['bucketName']}\n "
                    f"endpoint: {s3config['endpoint']}\n - ")
                s3config['secretKey'] = secret_key
            else:
                secret_key = input(
                    f"Please provide secret key for the below s3 target "
                    f"details: \naccessKey: {s3config['accessKey']} "
                    f"\n bucketName: {s3config['bucketName']}\n "
                    f"endpoint: {s3config['endpoint']}\n - ")
                s3config['secretKey'] = secret_key
                s3config_bk = resp_json['rancherKubernetesEngineConfig']['services']['etcd']['backupConfig']['s3BackupConfig']
                print("Updating cluster to set new s3 etcd target..")
                resp_json['rancherKubernetesEngineConfig']['services']['etcd']['backupConfig']['s3BackupConfig'] = s3config
                resp_put = requests.put(
                    url_cluster,
                    verify=False,
                    auth=self.auth,
                    data=json.dumps(resp_json))
                if resp_put.status_code == 200:
                    runtime = 30
                    start = int(time.time())
                    wait_timeout = start + 60 * runtime
                    spin = '-\\|/'
                    idx = 0
                    while True:
                        print(spin[idx % len(spin)], end="\r")
                        idx += 1
                        time.sleep(0.1)
                        if int(time.time()) >= wait_timeout:
                            print("Timeout")
                            self.logger.error(
                                'Timed out while waiting for backup to complete')
                            break
                        resp_get = requests.get(
                            url_cluster, verify=False, auth=self.auth)
                        json_resp = resp_get.json()
                        if json_resp['state'] == "active" and json_resp['transitioning'] == "no":
                            "Cluster Updated"
                            break
                else:
                    print("Error in setting new etcd target for current cluster")
                    sys.exit

        # Check if selected backup is available
        print("Checking if backup is available in target")
        # print(s3config)
        s3 = get_resource(s3config)
        if s3:
            bucket = get_bucket(s3, s3config['bucketName'])
            if bucket:
                file_exists = isfile_s3(bucket, filename)
                if file_exists:
                    print("Backup exists")
                else:
                    print("Selected backup not found")
                    sys.exit()
            else:
                print("Error in getting bucket details")
        else:
            print("Error in getting object")

        # Delete created files
        try:
            os.remove("ca-bundle.pem")
        except OSError as exception:
            if exception.errno != errno.ENOENT:  # check no such file or directory
                raise
        # Finally restoring
        print("restore is in progress")
        url = f'{self.server_url}v3/clusters/{self.cluster_id}?action=restoreFromEtcdBackup'
        resp_rest = requests.post(url, verify=False, auth=self.auth, data=json.dumps(
            {'etcdBackupId': f'{self.cluster_id}:{restore_id}', 'restoreRkeConfig': None}))
        url_cluster = f"{self.server_url}v3/clusters/{self.cluster_id}"
        if resp_rest.status_code == 200 or resp_rest.status_code == 201:
            runtime = 60
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
                        'Timed out while waiting for restore to complete')
                    break
                try:
                    resp_get = requests.get(
                        url_cluster, verify=False, auth=self.auth)
                except BaseException as e:
                    continue
                json_resp = resp_get.json()
                if json_resp.get(
                        'state',
                        "") == "active" and json_resp.get(
                        'transitioning',
                        "") == "no":
                    print("Restore completed")
                    break
        else:
            print("Restore failed")
            sys.exit()


def get_resource(config: dict = {}):
    """Loads the s3 resource.

    Expects AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to be in the environment
    or in a config dictionary.
    Looks in the environment first."""

    session = boto3.session.Session()
    if config['customCa'] != "":
        cert_fd_nm = "ca-bundle.pem"
        certs_fd = open(cert_fd_nm, "w")
        certs_fd.write(config['customCa'])
        certs_fd.close()
        stor_obj = session.resource(service_name='s3',
                                    aws_access_key_id=config['accessKey'],
                                    aws_secret_access_key=config['secretKey'],
                                    endpoint_url="https://{0}".format(
                                        config['endpoint']),
                                    verify='ca-bundle.pem')
    else:
        stor_obj = session.resource(service_name='s3',
                                    aws_access_key_id=config['accessKey'],
                                    aws_secret_access_key=config['secretKey'],
                                    endpoint_url="https://{0}".format(config['endpoint']))
    return stor_obj


def get_bucket(s3, s3_uri: str):
    """Get the bucket from the resource.
    A thin wrapper, use with caution.

    Example usage:

    >> bucket = get_bucket(get_resource(), s3_uri_prod)"""
    return s3.Bucket(s3_uri)


def isfile_s3(bucket, key: str) -> bool:
    """Returns T/F whether the file exists."""
    objs = list(bucket.objects.filter(Prefix=key))
    return len(objs) == 1 and objs[0].key == key


def get_cluster_name():
    """
    This function is use to get cluster name
    from current context
    """
    cluster_config = config.kube_config.list_kube_config_contexts()
    cluster_name = cluster_config[1]['context']['cluster']
    if cluster_name == "":
        return None
    return cluster_name


def get_target_secret_credentials(api_instance, secret_name, secret_namespace, logging):
    """
    Function to get target credentials from target
    created using TVK
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
            certs_en = secret.data.get('ca-bundle.pem')
            if certs_en is not None:
                certs_en = base64.b64decode(certs_en).decode('utf-8')
            if access_key == "":
                logging.info(
                    'Unable to get access key for ObjectStore from secret')
            if secret_key == "":
                logging.info(
                    'Unable to get secret key for ObjectStore from secret')
    except ApiException as exception:
        logging.error('Error while getting Secret :', exception.reason)
    except BaseException as exception:
        logging.error(exception)
    finally:
        if certs_en is not None:
            return access_key.strip(), secret_key.strip(), certs_en.strip()
        return access_key.strip(), secret_key.strip(), ""


def parse_target(
        api_instance,
        custom_api,
        target_name,
        target_namespace,
        logger):
    """
    Function to parse target created using TVK
    and get target information.
    """
    TARGET_CRD_GROUP = 'triliovault.trilio.io'  # str | the custom resource's group
    TARGET_CRD_PLURAL = 'targets'  # str | the custom resource's plural name.
    TARGET_CRD_VERSION = 'v1'  # str | the custom resource's version
    response = custom_api.get_namespaced_custom_object(
        TARGET_CRD_GROUP,
        TARGET_CRD_VERSION,
        target_namespace,
        TARGET_CRD_PLURAL,
        target_name)
    if 'url' in response["spec"]["objectStoreCredentials"]:
        s3_endpoint_url = response["spec"]["objectStoreCredentials"].get(
            "url", "")
    elif response["spec"]["vendor"] == "AWS":
        s3_endpoint_url = "https://s3.amazonaws.com"
    else:
        print("Please specify url/s3endpoint in target manifest")
        sys.exit(1)
    #import pdb; pdb.set_trace()
    certs = ""
    if 'credentialSecret' in response["spec"]["objectStoreCredentials"]:
        secret_name = response["spec"]["objectStoreCredentials"]["credentialSecret"]["name"]
        secret_namespace = response["spec"]["objectStoreCredentials"]["credentialSecret"]["namespace"]
        access_key_id, access_key, certs = get_target_secret_credentials(
            api_instance, secret_name, secret_namespace, logger)

    else:
        access_key_id = response["spec"]["objectStoreCredentials"]["accessKey"]
        access_key = response["spec"]["objectStoreCredentials"]["secretKey"]
        certs = response["spec"]["objectStoreCredentials"].get('ca-bundle.pem')

    if response["spec"]["objectStoreCredentials"].get("region", "") == "":
        region = "us-east-1"

    obj_dict = {
        'id': response["metadata"]["uid"],
        'storageType': response["spec"]["type"],
        'name': response["metadata"]["name"],
        'namespace': response["metadata"]["namespace"],
        'accessKeyID': access_key_id,
        'accessKey': access_key,
        's3Bucket': response["spec"]["objectStoreCredentials"]["bucketName"],
        'regionName': response["spec"]["objectStoreCredentials"].get("region"),
        'storageNFSSupport': "TrilioVault",
        's3EndpointUrl': s3_endpoint_url,
        'vendor': response["spec"]["vendor"],
        'certs': certs
    }
    return obj_dict


def generate_kubeconfig(server_url, token, path, cluster_name):
    key_list = token.split(":")
    auth = HTTPBasicAuth(
        f"{key_list[0]}", f"{key_list[1]}")
    auth = auth
    get_url = f"{server_url}v3/clusters?name={cluster_name}"
    resp = requests.get(get_url, verify=False, auth=auth)
    json_resp = resp.json()
    try:
        for item in json_resp['data']:
            cluster_id = item['id']
    except KeyError:
        print("Authentication Error - Unauthorized 401: must authenticate")
        sys.exit()
    except BaseException as e:
        print(e)
        print("Error in Getting kubeconfig")
        sys.exit()

    url = f"{server_url}v3/clusters/"\
        f"{cluster_id}?action=generateKubeconfig"
    resp = requests.post(url, verify=False, auth=auth)
    out_resp = json.loads(resp.content)
    try:
        yaml_resp = yaml.safe_load(out_resp["config"])
    except KeyError:
        print("Not able to connect to cluster")
        sys.exit()
    except BaseException as e:
        print(e)
        print("Error in connecting cluster")
        sys.exit()
    with open(path, "w") as outfile:
        yaml.dump(yaml_resp, outfile)


def init():
    """
    Function to get arguments from user and parse it
    """
    try:
        parser = argparse.ArgumentParser(
            "ETCD Backup and restore on Rancher cluster. "
            "Available flags: -backup -restore.")
        parser.add_argument('-backup', action="store_true")
        parser.add_argument('-restore', action="store_true")
        parser.add_argument(
            '--target-name',
            dest="target_name",
            help="The name of a single datastore on which etcd "
            "backup needs to be shared")
        parser.add_argument(
            '--target-namespace',
            dest="target_namespace",
            help="Namespace name where the target resides.")
        parser.add_argument(
            '--rancher-url',
            dest="rancher_url",
            help="Rancher server URL",
            required=True)
        parser.add_argument(
            '--bearer-token',
            dest="bearer_token",
            help="Token to access rancher server",
            required=True)
        parser.add_argument(
            '--cluster-name',
            dest="cluster_name",
            help="Cluster name",
            required=True)
        parser.add_argument(
            '--log-location',
            dest="log_loc",
            help="Log file name along with path where the logs "
            "should be save. default - /tmp/etcd-rke-backup.log")

        args = parser.parse_args()

        return args
    except Exception as ex:
        logging.exception(ex)
        sys.exit(1)


def main():

    args = init()
    # Gets or creates a logger
    logger = logging.getLogger(__name__)

    # set log level
    logger.setLevel(logging.DEBUG)
    # logger.setLevel(logging.WARNING)

    # define file handler and set formatter
    if not args.log_loc:
        log_loc = "/tmp/etcd-rke-backup.log"
    else:
        log_loc = args.log_loc
    file_handler = logging.FileHandler(log_loc)
    formatter = logging.Formatter(
        '%(asctime)s : %(levelname)s : %(name)s : %(message)s')
    file_handler.setFormatter(formatter)

    # add file handler to logger
    logger.addHandler(file_handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # supress insecure connection error
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    # Check if server url ends with '\'
    if not args.rancher_url.endswith('/'):
        args.rancher_url = args.rancher_url + '/'

    # Generate kubeconfig from the rancher server
    generate_kubeconfig(args.rancher_url, args.bearer_token,
                        '/tmp/etcd_bk_rest_kubeconfig', args.cluster_name)

    # Create kubernetes client object
    config.load_kube_config('/tmp/etcd_bk_rest_kubeconfig')
    api_instance = client.CoreV1Api()
    api_batch = client.BatchV1Api()
    custom_api = client.CustomObjectsApi()
    configuration.assert_hostname = False

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

    if args.backup is True:
        if not args.target_name or not args.target_namespace:
            print("For backup, user would need to provide target_name and its namespace")
            sys.exit()
        etcd_obj = ETCDbackup(
            logger,
            api_instance,
            custom_api,
            api_batch,
            args.rancher_url,
            args.bearer_token,
            args.target_name,
            args.target_namespace,
            args.cluster_name)
        etcd_obj.etcd_bk()
    elif args.restore is True:
        print('Warning: Restoring to a previous cluster state can be '
              'destructive and destablizing action to take '
              'on a running cluster.')
        rest_confirm = input(
            f"Do you want to continue? (y/n): ")
        if rest_confirm != 'Y' and rest_confirm != 'y':
            #print("Input Y/y to confirm and continue")
            sys.exit(1)
        etcd_obj = ETCDrestore(
            logger,
            api_instance,
            custom_api,
            api_batch,
            args.rancher_url,
            args.bearer_token,
            args.cluster_name)
        etcd_obj.etcd_rest()
    else:
        print("Please select at least one flag from backup and restore")


if __name__ == '__main__':
    main()
