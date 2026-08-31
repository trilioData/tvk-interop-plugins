"""Diagnose the degraded machine-config operator: clusteroperator detail,
MachineConfigPools, and node states. Read-only."""
import re
import urllib.parse

import requests
import urllib3
from kubernetes import client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONSOLE = "https://console-openshift-console.apps.<your-cluster>"
USER, PASSWORD = "kubeadmin", "PzJXa-2AJpX-2xL6c-XjHu6"

host = urllib.parse.urlparse(CONSOLE).hostname
domain = re.search(r"\bapps\..*$", host).group(0)
api_url = f"https://api.{domain[len('apps.'):]}:6443"
oauth = (f"https://oauth-openshift.{domain}"
         "/oauth/authorize?response_type=token&client_id=openshift-challenging-client")
r = requests.get(oauth, auth=(USER, PASSWORD), headers={"X-CSRF-Token": "1"},
                 verify=False, allow_redirects=False, timeout=30)
token = urllib.parse.unquote(re.search(r"access_token=([^&]+)", r.headers["Location"]).group(1))
conf = client.Configuration()
conf.host, conf.verify_ssl = api_url, False
conf.api_key = {"authorization": f"Bearer {token}"}
ac = client.ApiClient(conf)
co = client.CustomObjectsApi(ac)
core = client.CoreV1Api(ac)

print("=== clusteroperator/machine-config ===")
mco = co.get_cluster_custom_object("config.openshift.io", "v1", "clusteroperators", "machine-config")
for c in mco["status"].get("conditions", []):
    if c["type"] in ("Degraded", "Progressing", "Available"):
        print(f"  {c['type']}={c['status']}: {c.get('message','')[:300]}")

print("\n=== MachineConfigPools ===")
mcps = co.list_cluster_custom_object("machineconfiguration.openshift.io", "v1", "machineconfigpools")
for m in mcps.get("items", []):
    name = m["metadata"]["name"]
    st = m.get("status", {})
    conds = {c["type"]: c["status"] for c in st.get("conditions", [])}
    print(f"  {name}: machineCount={st.get('machineCount')} "
          f"updated={st.get('updatedMachineCount')} ready={st.get('readyMachineCount')} "
          f"degraded={st.get('degradedMachineCount')} "
          f"Updated={conds.get('Updated')} Updating={conds.get('Updating')} "
          f"Degraded={conds.get('Degraded')}")
    for c in st.get("conditions", []):
        if c["type"] in ("Degraded", "NodeDegraded") and c["status"] == "True":
            print(f"      -> {c['type']}: {c.get('message','')[:300]}")

print("\n=== Nodes ===")
for n in core.list_node().items:
    name = n.metadata.name
    ready = next((c.status for c in n.status.conditions if c.type == "Ready"), "?")
    ann = n.metadata.annotations or {}
    state = ann.get("machineconfiguration.openshift.io/state", "?")
    reason = ann.get("machineconfiguration.openshift.io/reason", "")
    sched = "SchedulingDisabled" if (n.spec.unschedulable) else ""
    print(f"  {name}: Ready={ready} mcoState={state} {sched} {reason[:120]}")
