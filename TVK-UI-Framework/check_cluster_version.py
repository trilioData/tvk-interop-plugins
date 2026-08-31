"""Read the OCP ClusterVersion (current version, channel, available updates).
Read-only — does NOT change anything."""
import re
import urllib.parse

import requests
import urllib3
from kubernetes import client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONSOLE = "https://console-openshift-console.apps.<your-cluster>"
USER = "kubeadmin"
PASSWORD = "PzJXa-2AJpX-2xL6c-XjHu6"

host = urllib.parse.urlparse(CONSOLE).hostname
domain = re.search(r"\bapps\..*$", host).group(0)            # apps.<your-cluster>...
api_url = f"https://api.{domain[len('apps.'):]}:6443"
oauth = (f"https://oauth-openshift.{domain}"
         "/oauth/authorize?response_type=token&client_id=openshift-challenging-client")

r = requests.get(oauth, auth=(USER, PASSWORD), headers={"X-CSRF-Token": "1"},
                 verify=False, allow_redirects=False, timeout=30)
token = urllib.parse.unquote(re.search(r"access_token=([^&]+)", r.headers["Location"]).group(1))

conf = client.Configuration()
conf.host = api_url
conf.verify_ssl = False
conf.api_key = {"authorization": f"Bearer {token}"}
api = client.CustomObjectsApi(client.ApiClient(conf))

cv = api.get_cluster_custom_object(
    "config.openshift.io", "v1", "clusterversions", "version")

print(f"API server     : {api_url}")
print(f"Current version: {cv['status']['desired']['version']}")
print(f"Channel        : {cv['spec'].get('channel', '<none>')}")
print(f"ClusterID      : {cv['spec'].get('clusterID', '?')}")

print("\nConditions:")
for c in cv["status"].get("conditions", []):
    if c["type"] in ("Available", "Failing", "Progressing"):
        print(f"  {c['type']}={c['status']}  {c.get('message','')[:120]}")

updates = cv["status"].get("availableUpdates") or []
print(f"\nAvailable updates ({len(updates)}):")
for u in updates:
    print(f"  -> {u.get('version')}")

cond_upd = [c for c in cv["status"].get("conditions", [])
            if c["type"] == "RetrievedUpdates"]
if cond_upd:
    print(f"\nRetrievedUpdates: {cond_upd[0]['status']} "
          f"{cond_upd[0].get('message','')[:160]}")
