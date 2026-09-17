"""Strict CR-status waits for the helm-transform flow — kept separate from
kube_client's wait_for_backup/wait_for_restore so the existing flows are
untouched.

Unlike the shared helpers, these match the EXACT resource name and never fall
back to 'latest' (which caused false positives by matching unrelated
backups/restores from other runs).
"""
import time

from kubernetes.client.rest import ApiException

TVK_GROUP = "triliovault.trilio.io"
_DONE = {"completed", "available", "succeeded"}
_FAILED = {"failed", "error"}


def _status(obj: dict) -> str:
    st = obj.get("status") or {}
    return str(st.get("status") or st.get("phase") or "").strip()


def _wait_named(kube, plural: str, name: str, namespace: str | None,
                timeout_s: int, poll_s: int = 20) -> dict:
    version = kube._tvk_version()
    deadline = time.time() + timeout_s
    print(f"[helm_verify] waiting for {plural}/{name} (exact match, "
          f"timeout {timeout_s}s)...")
    while time.time() < deadline:
        items = []
        try:
            if namespace:
                items = kube.custom.list_namespaced_custom_object(
                    TVK_GROUP, version, namespace, plural).get("items", [])
            if not items:
                items = kube.custom.list_cluster_custom_object(
                    TVK_GROUP, version, plural).get("items", [])
        except ApiException as e:
            print(f"[helm_verify] list {plural} failed ({e.status}) — retrying")

        target = next((i for i in items
                       if i.get("metadata", {}).get("name") == name), None)
        if target is not None:
            status = _status(target)
            remaining = int(deadline - time.time())
            print(f"[helm_verify] {plural}/{name} status={status or '<none>'} "
                  f"({remaining}s left)")
            if status.lower() in _DONE:
                return target
            if status.lower() in _FAILED:
                raise AssertionError(f"{plural}/{name} failed with status '{status}'")
        else:
            print(f"[helm_verify] {plural}/{name} not created yet — waiting")
        time.sleep(poll_s)
    raise TimeoutError(
        f"{plural}/{name} did not complete within {timeout_s}s "
        "(exact-name match — not created or never completed)")


def wait_for_helm_backup(kube, name: str, namespace: str, timeout_s: int = 2700):
    return _wait_named(kube, "backups", name, namespace, timeout_s)


def wait_for_helm_restore(kube, name: str, namespace: str, timeout_s: int = 2700):
    return _wait_named(kube, "restores", name, namespace, timeout_s)


# ---------- transformation verification (separate, additive) ----------

def _app_pods(kube, namespace: str):
    """Running app pods in a namespace (skip helm hook/test/job pods)."""
    pods = kube.core.list_namespaced_pod(namespace).items
    out = []
    for p in pods:
        name = p.metadata.name
        phase = p.status.phase
        # skip obvious helm hooks / one-off jobs
        if any(s in name for s in ("-test", "-hook", "-upgrade", "-install")):
            continue
        out.append(p)
    return out


def _images(pod) -> set:
    return {c.image for c in (pod.spec.containers or [])}


def _cpu_requests(pod):
    """Return [(container_name, requests.cpu)] from
    pod.spec.containers[].resources.requests.cpu — ONLY requests.cpu (not
    limits.cpu, not other cpu fields). There may be several containers; we
    check this specific path on each.
    """
    out = []
    for c in pod.spec.containers or []:
        req = (c.resources.requests if c.resources else None) or {}
        if "cpu" in req:
            out.append((c.name, req["cpu"]))
    return out


def helm_restore_verify(kube, source_ns: str, restore_ns: str,
                        expected_cpu: str = None, timeout_s: int = 600):
    """Verify a helm transform restore:
      1) the source app is present in the restore namespace and Running — the
         pod NAME may differ but the container IMAGE(s) must match a source pod.
      2) (if expected_cpu given) the restored pod's resources.requests.cpu was
         transformed to expected_cpu.

    Separate from the existing flows — does not touch other code.
    """
    import time

    # source images (what we expect to see restored)
    src_pods = _app_pods(kube, source_ns)
    src_images = set()
    for p in src_pods:
        src_images |= _images(p)
    print(f"[helm_verify] source '{source_ns}' images: {sorted(src_images)}")
    if not src_images:
        raise AssertionError(f"No app pods/images found in source ns '{source_ns}'")

    # wait for a Running pod in the restore ns whose image matches the source
    deadline = time.time() + timeout_s
    matched_pod = None
    while time.time() < deadline:
        for p in _app_pods(kube, restore_ns):
            running = p.status.phase == "Running"
            imgs = _images(p)
            if running and (imgs & src_images):
                matched_pod = p
                break
        if matched_pod:
            break
        print(f"[helm_verify] waiting for restored app pod in '{restore_ns}'...")
        time.sleep(10)

    if not matched_pod:
        raise AssertionError(
            f"No Running pod in restore ns '{restore_ns}' with an image matching "
            f"the source app {sorted(src_images)}")
    print(f"[helm_verify] restored pod '{matched_pod.metadata.name}' Running with "
          f"image(s) {sorted(_images(matched_pod))} (matches source) [OK]")

    # verify the transformed cpu — strictly from
    # spec.containers[].resources.requests.cpu (there may be several cpu
    # values across containers/limits; only requests.cpu on this flow counts).
    if expected_cpu:
        per_container = _cpu_requests(matched_pod)   # [(container, requests.cpu)]
        cpus = [v for _, v in per_container]
        print(f"[helm_verify] restored pod '{matched_pod.metadata.name}' "
              f"spec.containers[].resources.requests.cpu = {per_container} "
              f"(expected {expected_cpu})")
        assert expected_cpu in cpus, (
            f"Transform not applied: expected requests.cpu='{expected_cpu}' on a "
            f"container of restored pod '{matched_pod.metadata.name}', found "
            f"{per_container}")
        print(f"[helm_verify] transform verified: requests.cpu = {expected_cpu} [OK]")
    return matched_pod
