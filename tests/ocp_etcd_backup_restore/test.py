import pytest
import sys
import os
import io
sys.path.append(f"{os.getcwd()}/internal/utils")
import util as rke
sys.path.append(f"{os.getcwd()}/tools/ocp_etcd_backup_restore")

def test_backup(config_param):
    ret_val = rke.run(
        f"python3 tools/ocp_etcd_backup_plugin/ocp_etcd_backup_restore.py -backup --target-name {config_param['target-name']} --target-namespace {config_param['target-namespace']} --api-server-url {config_param['server']} --ocp-cluster-user {config_param['user']} --ocp-cluster-pass {config_param['passwd']}")
    assert ret_val == 0

def test_restore(config_param):
    ret_val = rke.run(
        "echo '' | python3 tools/ocp_etcd_backup_plugin/ocp_etcd_backup_restore.py -restore --api-server-url {0} --ocp-cluster-user {1} --ocp-cluster-pass {2}".format(config_param['server'], config_param['user'], config_param['passwd']))
    assert ret_val == 0
