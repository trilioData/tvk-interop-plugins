# TVK Quickstart — Action Items

## Open Items

### 1. Validate on Vanilla Kubernetes with Helm 3.x

**Priority:** High  
**Context:** All OCP fixes have been validated on `ocp-dc11.demo.presales.trilio.io`. The script's non-OCP code paths (vanilla Kubernetes) have not been retested after the OCP work. Additionally, T4K only supports helm v3. The local helm client was upgraded to 4.1.4 during OCP testing — this is fine for OCP (TVK installs via OLM there) but vanilla k8s installs TVK via `helm install`, which may not be compatible with helm 4.

**What to test:**
- Run `kubectl tvk-quickstart -n input_config` against a vanilla Kubernetes cluster
- Use helm 3.x (>= 3.8, e.g. 3.17.x) — downgrade from 4.1.4 before testing
- Verify all backup_way modes pass (Namespace_based, Label_based, Helm_based, Transformation, Operator_based)
- Confirm the OCP-specific fixes do not interfere with vanilla k8s paths (all gated behind `open_flag`)

**How to downgrade helm temporarily:**
```bash
brew unlink helm
brew install helm@3
brew link --overwrite helm@3
helm version --short  # should show v3.17.x
```

---

### 2. Operator_based Test (OCP)

**Priority:** High  
**Context:** Not yet tested on OCP. Deploys Datagrid via OLM. Likely to hit OCP-specific issues similar to others fixed in this session.

**What to test:**
- Set `backup_way='Operator_based'` in `input_config` and run
- Document and fix any new issues found

---

### 3. Open PR to trilioData/tvk-interop-plugins

**Priority:** Medium  
**Context:** All fixes are on the `main` branch locally. A PR needs to be pushed to `https://github.com/trilioData/tvk-interop-plugins`.

**What to do:**
- Create a new branch (e.g. `fix/ocp-compatibility`)
- Push and open PR via `gh pr create`
- Reference all 16 fixes documented in `OCP_FIXES.md`

---

## Completed

- [x] Namespace_based (WordPress + MySQL) — ✅ OCP passing
- [x] VM_TEST (KubeVirt Fedora) — ✅ OCP passing
- [x] Transformation (PostgreSQL) — ✅ OCP passing (probe fallback to cephfs)
- [x] Label_based (MySQL) — ✅ OCP passing
- [x] Helm_based (Prometheus) — 🔄 In progress (fixes #15 + #16 applied)
