"""Poll the OCP upgrade until it reaches 4.18.43 or fails. Prints progress
every few minutes; exits 0 on success, 2 on failure."""
import re
import sys
import time
import urllib.parse

import requests
import urllib3
from kubernetes import client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONSOLE = "https://console-openshift-console.apps.<your-cluster>"
USER = "kubeadmin"
PASSWORD = "PzJXa-2AJpX-2xL6c-XjHu6"
TARGET = "4.18.43"
POLL_S = 180


def connect():
    host = urllib.parse.urlparse(CONSOLE).hostname
    domain = re.search(r"\bapps\..*$", host).group(0)
    api_url = f"https://api.{domain[len('apps.'):]}:6443"
    oauth = (f"https://oauth-openshift.{domain}"
             "/oauth/authorize?response_type=token&client_id=openshift-challenging-client")
    r = requests.get(oauth, auth=(USER, PASSWORD), headers={"X-CSRF-Token": "1"},
                     verify=False, allow_redirects=False, timeout=30)
    token = urllib.parse.unquote(
        re.search(r"access_token=([^&]+)", r.headers["Location"]).group(1))
    conf = client.Configuration()
    conf.host = api_url
    conf.verify_ssl = False
    conf.api_key = {"authorization": f"Bearer {token}"}
    return client.CustomObjectsApi(client.ApiClient(conf))


def cond(cv, t):
    for c in cv["status"].get("conditions", []):
        if c["type"] == t:
            return c
    return {}


deadline = time.time() + 3 * 3600  # 3h safety cap
api = connect()
while time.time() < deadline:
    try:
        cv = api.get_cluster_custom_object(
            "config.openshift.io", "v1", "clusterversions", "version")
    except Exception as e:
        # token expiry / API blip during control-plane reboot — reconnect
        print(f"[watch] API read failed ({e}); reconnecting...", flush=True)
        time.sleep(30)
        try:
            api = connect()
        except Exception:
            pass
        continue

    version = cv["status"]["desired"]["version"]
    prog = cond(cv, "Progressing")
    failing = cond(cv, "Failing")
    avail = cond(cv, "Available")
    ts = time.strftime("%H:%M:%S")
    print(f"[watch {ts}] version={version} "
          f"Progressing={prog.get('status')} Failing={failing.get('status')} "
          f"| {prog.get('message','')[:110]}", flush=True)

    if failing.get("status") == "True":
        print(f"\n[watch] !!! UPGRADE FAILING: {failing.get('message','')}", flush=True)
        sys.exit(2)

    if (version == TARGET and prog.get("status") == "False"
            and avail.get("status") == "True"):
        print(f"\n[watch] *** UPGRADE COMPLETE: cluster is now {TARGET} ***", flush=True)
        sys.exit(0)

    time.sleep(POLL_S)

print("[watch] safety timeout reached (3h) — upgrade still not complete", flush=True)
sys.exit(1)
