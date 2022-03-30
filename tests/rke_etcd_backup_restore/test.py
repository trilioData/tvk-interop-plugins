import pytest
import sys
import os
import io
sys.path.append(f"{os.getcwd()}/internal/utils")
import util as rke
sys.path.append(f"{os.getcwd()}/tools/rke_etcd_backup_plugin")

def test_backup(config_param):
    ret_val = rke.run(
        f"sudo python3 tools/rke_etcd_backup_plugin/rke-etcd-backup-restore.py -backup --target-name {config_param['target-name']} --target-namespace {config_param['target-namespace']} --rancher-url {config_param['rancher-url']} --bearer-token {config_param['bearer-token']} --cluster-name {config_param['cluster-name']}")
    assert ret_val == 0

#@patch('builtins.input', lambda restore_id: "")
def test_restore(config_param, monkeypatch):
    ret_val = rke.run(
        "{{ echo ''; echo '{0}'; }} | sudo python3 tools/rke_etcd_backup_plugin/rke-etcd-backup-restore.py -restore --rancher-url {1} --bearer-token {2} --cluster-name {3}".format(format(config_param['target-secretkey']), config_param['rancher-url'], config_param['bearer-token'], config_param['cluster-name']))
    assert ret_val == 0
