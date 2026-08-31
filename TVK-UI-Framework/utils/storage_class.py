"""Create the 'trans-storageclass' StorageClass used by the custom-transform
restore test (the restore rewrites each PVC's /spec/storageClassName to this).

Python port of create_storage_class.txt — kept SEPARATE so existing code is
untouched. Strategy (mirrors the shell script):
  1. Find the default StorageClass (is-default-class annotation).
  2. Prefer cloning a NON-ODF SC (provisioner not ceph/noobaa/openshift-storage)
     into 'trans-storageclass' with volumeBindingMode=Immediate.
  3. If there is no non-ODF SC to clone, use an existing non-default SC name
     directly (no creation needed).
  4. Last resort: use the default SC name.

Returns the StorageClass NAME the restore should target.
"""
from kubernetes import client
from kubernetes.client.rest import ApiException

TRANS_SC_NAME = "trans-storageclass"
_ODF_PROVISIONER_RE = ("ceph", "noobaa", "openshift-storage")


def _is_default(sc) -> bool:
    ann = (sc.metadata.annotations or {})
    return ann.get("storageclass.kubernetes.io/is-default-class") == "true"


def _storage_api(kube) -> "client.StorageV1Api":
    return client.StorageV1Api(kube.api_client)


def ensure_trans_storageclass(kube, name: str = TRANS_SC_NAME) -> str:
    """Ensure a StorageClass suitable for the transform exists; return its name."""
    sc_api = _storage_api(kube)
    classes = sc_api.list_storage_class().items
    by_name = {c.metadata.name: c for c in classes}

    # already there from a previous run
    if name in by_name:
        print(f"[storage_class] '{name}' already exists — reusing")
        return name

    default_sc = next((c.metadata.name for c in classes if _is_default(c)), None)
    print(f"[storage_class] default StorageClass = {default_sc}")

    # 1. prefer a non-ODF SC to clone
    non_odf = next(
        (c for c in classes
         if not any(p in (c.provisioner or "").lower() for p in _ODF_PROVISIONER_RE)),
        None)

    if non_odf is not None:
        src = non_odf
        print(f"[storage_class] cloning non-ODF SC '{src.metadata.name}' "
              f"(provisioner={src.provisioner}) -> '{name}'")
        clone = client.V1StorageClass(
            metadata=client.V1ObjectMeta(name=name),
            provisioner=src.provisioner,
            parameters=src.parameters,
            reclaim_policy=src.reclaim_policy,
            mount_options=src.mount_options,
            allow_volume_expansion=src.allow_volume_expansion,
            # Immediate binding so PVCs provision without waiting for a pod
            volume_binding_mode="Immediate",
        )
        try:
            sc_api.create_storage_class(clone)
            print(f"[storage_class] created '{name}'")
            return name
        except ApiException as e:
            if e.status == 409:
                print(f"[storage_class] '{name}' already exists — reusing")
                return name
            print(f"[storage_class] clone create failed ({e.status}) — "
                  "falling back to an existing SC")

    # 2. no non-ODF SC (or clone failed): use an existing non-default SC directly
    alt = next((c.metadata.name for c in classes
                if c.metadata.name != default_sc), None)
    if alt:
        print(f"[storage_class] no clonable SC — using existing non-default "
              f"SC '{alt}' as the transform target")
        return alt

    # 3. last resort
    if default_sc:
        print(f"[storage_class] using default SC '{default_sc}' as transform target")
        return default_sc

    raise RuntimeError("No StorageClass found on the cluster for the transform test")


def verify_pvc_storageclass(kube, namespace: str, expected_sc: str,
                            timeout_s: int = 600):
    """Verify the custom transform took effect: at least one PVC in the restore
    namespace uses `expected_sc` as its storageClassName. Separate/additive."""
    import time
    deadline = time.time() + timeout_s
    seen = {}
    while time.time() < deadline:
        pvcs = kube.core.list_namespaced_persistent_volume_claim(namespace).items
        seen = {pv.metadata.name: pv.spec.storage_class_name for pv in pvcs}
        if expected_sc in seen.values():
            match = [n for n, sc in seen.items() if sc == expected_sc]
            print(f"[storage_class] transform verified: PVC(s) {match} in "
                  f"'{namespace}' use storageClassName='{expected_sc}' [OK]")
            return True
        print(f"[storage_class] waiting for a restored PVC with "
              f"storageClassName='{expected_sc}' in '{namespace}' (have {seen})")
        time.sleep(10)
    raise AssertionError(
        f"Custom transform NOT applied: no PVC in '{namespace}' uses "
        f"storageClassName='{expected_sc}'. Found: {seen}")
