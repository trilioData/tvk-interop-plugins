"""Switch ocp-cluster2 to channel eus-4.18 and trigger the upgrade to the
latest 4.18.z the update graph offers."""
import re
import time
import urllib.parse

import requests
import urllib3
from kubernetes import client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONSOLE = "https://console-openshift-console.apps.<your-cluster>"
USER = "kubeadmin"
PASSWORD = "PzJXa-2AJpX-2xL6c-XjHu6"
TARGET_CHANNEL = "eus-4.18"

host = urllib.parse.urlparse(CONSOLE).hostname
domain = re.search(r"\bapps\..*$", host).group(0)
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

G, V, P, NAME = "config.openshift.io", "v1", "clusterversions", "version"


def get_cv():
    return api.get_cluster_custom_object(G, V, P, NAME)


cv = get_cv()
print(f"Before: version={cv['status']['desired']['version']} "
      f"channel={cv['spec'].get('channel')}")

# 1) Set channel to eus-4.18
api.patch_cluster_custom_object(G, V, P, NAME, {"spec": {"channel": TARGET_CHANNEL}})
print(f"Channel set to {TARGET_CHANNEL}")

# 2) Wait for the update graph to expose 4.18.z releases
target = None
for attempt in range(20):  # up to ~5 min
    time.sleep(15)
    cv = get_cv()
    ups = cv["status"].get("availableUpdates") or []
    v418 = sorted(
        [u for u in ups if str(u.get("version", "")).startswith("4.18.")],
        key=lambda u: [int(x) for x in u["version"].split(".")],
        reverse=True)
    retrieved = [c for c in cv["status"].get("conditions", [])
                 if c["type"] == "RetrievedUpdates"]
    print(f"  poll {attempt+1}: {len(ups)} updates, {len(v418)} are 4.18.x"
          + (f" (RetrievedUpdates={retrieved[0]['status']})" if retrieved else ""))
    if v418:
        target = v418[0]
        break

if not target:
    print("\nNo 4.18.z update is offered yet on channel eus-4.18.")
    print("Available versions currently:")
    for u in (cv["status"].get("availableUpdates") or []):
        print(f"  -> {u.get('version')}")
    raise SystemExit("Cannot trigger upgrade — no 4.18 target in the update graph.")

# 3) Trigger the upgrade to the chosen 4.18.z (version + image, like `oc adm upgrade --to`)
desired = {"version": target["version"], "image": target["image"]}
api.patch_cluster_custom_object(G, V, P, NAME, {"spec": {"desiredUpdate": desired}})
print(f"\nUpgrade triggered -> {target['version']}")
print(f"  image: {target['image']}")

# 4) Confirm it started
time.sleep(10)
cv = get_cv()
for c in cv["status"].get("conditions", []):
    if c["type"] in ("Progressing", "Available", "Failing"):
        print(f"  {c['type']}={c['status']}  {c.get('message','')[:120]}")
