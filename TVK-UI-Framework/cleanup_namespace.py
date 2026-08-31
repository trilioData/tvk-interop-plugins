"""
Standalone namespace cleanup.

Deletes all Trilio custom resources (backups, restores, backupplans, targets,
policies) in a namespace, then deletes the namespace itself (which cascades
every other resource in it). Custom resources are removed first so their
finalizers don't block the namespace deletion; finalizers are force-cleared if
a CR is stuck.

Cluster connection is read from a YAML config (default config/example-config.yaml),
or overridden with --console/--user/--password.

Usage:
  python cleanup_namespace.py <namespace> [<namespace2> ...]
  python cleanup_namespace.py tvk-test-app-i7b --config config/example-config.yaml
  python cleanup_namespace.py my-ns --console https://console-... --user kubeadmin --password ***
  python cleanup_namespace.py my-ns --keep-namespace      # only delete TVK CRs, keep the ns
"""
import argparse
import re
import sys
import time
import urllib.parse

import requests
import urllib3
import yaml
from kubernetes import client
from kubernetes.client.rest import ApiException

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TVK_GROUP = "triliovault.trilio.io"
TVK_PLURALS = ["restores", "backups", "backupplans", "policies", "targets",
               "hooks", "cleanuppolicies"]


def connect(console, user, password):
    host = urllib.parse.urlparse(console).hostname
    domain = re.search(r"\bapps\..*$", host).group(0)
    api_url = f"https://api.{domain[len('apps.'):]}:6443"
    oauth = (f"https://oauth-openshift.{domain}"
             "/oauth/authorize?response_type=token&client_id=openshift-challenging-client")
    r = requests.get(oauth, auth=(user, password), headers={"X-CSRF-Token": "1"},
                     verify=False, allow_redirects=False, timeout=30)
    loc = r.headers.get("Location", "")
    m = re.search(r"access_token=([^&]+)", loc)
    if not m:
        sys.exit(f"Failed to get token (status {r.status_code}). Check credentials.")
    token = urllib.parse.unquote(m.group(1))
    conf = client.Configuration()
    conf.host = api_url
    conf.verify_ssl = False
    conf.api_key = {"authorization": f"Bearer {token}"}
    print(f"[cleanup] connected to {api_url} as {user}")
    return client.ApiClient(conf)


def tvk_version(ac):
    try:
        for g in client.ApisApi(ac).get_api_versions().groups:
            if g.name == TVK_GROUP:
                return g.preferred_version.version
    except Exception:
        pass
    return "v1"


def clear_finalizers(co, version, ns, plural, name):
    """Force-remove finalizers so a stuck CR can be deleted."""
    try:
        co.patch_namespaced_custom_object(
            TVK_GROUP, version, ns, plural, name, {"metadata": {"finalizers": []}})
        print(f"[cleanup]   cleared finalizers on {plural}/{name}")
    except ApiException:
        pass


def delete_tvk_resources(ac, ns):
    co = client.CustomObjectsApi(ac)
    version = tvk_version(ac)
    for plural in TVK_PLURALS:
        try:
            items = co.list_namespaced_custom_object(
                TVK_GROUP, version, ns, plural).get("items", [])
        except ApiException as e:
            if e.status in (404, 405):  # CRD not present on this cluster
                continue
            print(f"[cleanup] list {plural} failed ({e.status})")
            continue
        for it in items:
            name = it["metadata"]["name"]
            try:
                co.delete_namespaced_custom_object(TVK_GROUP, version, ns, plural, name)
                print(f"[cleanup] deleted {plural}/{name} in '{ns}'")
            except ApiException as e:
                if e.status != 404:
                    print(f"[cleanup] delete {plural}/{name} failed ({e.status})")
        # second pass: clear finalizers on anything still lingering
        time.sleep(2)
        try:
            leftover = co.list_namespaced_custom_object(
                TVK_GROUP, version, ns, plural).get("items", [])
            for it in leftover:
                clear_finalizers(co, version, ns, plural, it["metadata"]["name"])
        except ApiException:
            pass


def delete_namespace(ac, ns):
    core = client.CoreV1Api(ac)
    try:
        core.delete_namespace(ns)
        print(f"[cleanup] namespace '{ns}' deletion requested")
    except ApiException as e:
        if e.status == 404:
            print(f"[cleanup] namespace '{ns}' not found — nothing to delete")
        else:
            print(f"[cleanup] delete namespace '{ns}' failed ({e.status})")


def main():
    ap = argparse.ArgumentParser(description="Clean up TVK resources and delete a namespace")
    ap.add_argument("namespaces", nargs="+", help="namespace(s) to clean up")
    ap.add_argument("--config", default="config/example-config.yaml",
                    help="YAML config with cluster.console_url/username/password")
    ap.add_argument("--console", help="override console URL")
    ap.add_argument("--user", help="override username")
    ap.add_argument("--password", help="override password")
    ap.add_argument("--keep-namespace", action="store_true",
                    help="only delete TVK resources, keep the namespace")
    args = ap.parse_args()

    console = args.console
    user = args.user
    password = args.password
    if not (console and user and password):
        try:
            with open(args.config) as f:
                cl = (yaml.safe_load(f) or {}).get("cluster", {})
            console = console or cl.get("console_url")
            user = user or cl.get("username")
            password = password or cl.get("password")
        except FileNotFoundError:
            sys.exit(f"Config '{args.config}' not found and --console/--user/--password "
                     "not all provided.")
    if not (console and user and password):
        sys.exit("Missing cluster console_url/username/password.")

    ac = connect(console, user, password)
    for ns in args.namespaces:
        print(f"\n=== Cleaning namespace '{ns}' ===")
        delete_tvk_resources(ac, ns)
        if args.keep_namespace:
            print(f"[cleanup] --keep-namespace set — leaving '{ns}' in place")
        else:
            delete_namespace(ac, ns)
    print("\n[cleanup] done.")


if __name__ == "__main__":
    main()
