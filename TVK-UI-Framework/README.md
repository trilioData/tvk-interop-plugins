# trilio-test-framework

Automated test suites for **TrilioVault for Kubernetes (TVK)** backup and
restore, covering both the web console and the Kubernetes API. Runs against
OpenShift and non-OpenShift clusters (AKS/EKS/GKE) from a single codebase.

Three independent suites share the same configuration and cluster helpers:

| Suite | Driver | What it proves |
|---|---|---|
| **UI end-to-end** (`tests/test_e2e_trilio.py`) | Playwright, real browser | The console can drive a full protect/recover lifecycle |
| **Feature integration** (`tests/test_feature_integration.py`) | Custom Resources | Backup types, policies, scheduling and retention behave correctly without a browser |
| **Stress** (`stress_tvk.py`) | Custom Resources | Repeated backup/restore cycles across three application shapes hold up under sustained load |

---

## Prerequisites

- Python 3.12+
- The **OpenShift client (`oc`)** — see below
- `helm` (for suites that install Helm applications)
- A TVK installation on the target cluster, with a valid licence
- An S3 bucket for the backup target

### 1. OpenShift client (`oc`)

**Not included in this repository.** The binary is ~103 MB, which exceeds
GitHub's 100 MB per-file limit, so it must be downloaded once per machine. `oc`
is a superset of `kubectl` and works against any Kubernetes cluster, including
AKS/EKS/GKE — so a separate `kubectl` is not required.

Download the client for your platform from the Red Hat mirror:

<https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/>

- Linux: `openshift-client-linux.tar.gz`
- macOS: `openshift-client-mac.tar.gz`
- Windows: `openshift-client-windows.zip`

You can also get it from the OpenShift web console: **? (help) → Command line
tools → Download oc**.

Then either put `oc` on your `PATH`:

```bash
# Linux / macOS
tar -xzf openshift-client-linux.tar.gz oc && sudo mv oc /usr/local/bin/
oc version --client
```

or unpack it into an `oc/` directory at the repository root, which is the
layout the helper scripts expect and is git-ignored:

```
trilio-test-framework/
  oc/
    oc.exe        # Windows
    oc            # Linux / macOS
```

```powershell
# Windows: verify it is reachable
.\oc\oc.exe version --client
```

### 2. Python environment

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
```

### 3. Node.js (only for the standalone `*.spec.js` / `*.spec.ts` files)

The pytest suites do not need Node. The standalone Playwright recordings do:

```bash
# Node 18+ from https://nodejs.org, then in the repository root:
npm init -y
npm install -D @playwright/test
npx playwright install chromium
```

### 4. Helm

Needed only by the suites that install Helm applications. Install from
<https://helm.sh/docs/intro/install/>, or on Windows with
`winget install Helm.Helm`. If it is not on `PATH`, point the stress suite at
it with `TVK_HELM_BIN`.

## Configuration

Copy the template and fill in your cluster:

```bash
cp config/example-config.yaml config/my-cluster-config.yaml
```

Real config files (`config/*-config.yaml`) are **git-ignored** — they hold
cluster passwords and S3 keys. Only the sanitised template is tracked.

Credentials may also come from the environment, which is preferred for CI:

| Variable | Purpose |
|---|---|
| `TVK_S3_ACCESS_KEY` / `TVK_S3_SECRET_KEY` | S3 target credentials |
| `TVK_KUBECONFIG` | kubeconfig for the stress suite |
| `TVK_HELM_BIN` | path to the `helm` binary |

### Leftover resources

`cleanup_enabled` (default `false`) controls whether a run deletes what it
created. Left `false`, every target, policy, backup plan, backup, restore and
namespace stays on the cluster so results can be inspected — useful when
triaging, but it accumulates. Set it `true` for routine runs, or remove the
namespaces afterwards.

### Cluster types

`cluster.cluster_type` selects how the console is authenticated:

| Value | Login method |
|---|---|
| `ocp` | "Sign in via OpenShift" → OAuth (kube:admin) |
| `aks` / `eks` / `gke` | kubeconfig file upload |

Non-OpenShift clusters have no OAuth provider, so the console takes a
kubeconfig directly. That kubeconfig **must carry embedded credentials** — one
that relies on an `exec` plugin (for example `kubelogin`) cannot be used,
because the console has no way to run a local binary.

### Reaching the TVK console

`cluster.trilio_url` must point at the console's login page.

**OpenShift** exposes it as a Route, so read the host directly:

```bash
oc get route -n trilio-system
# trilio_url: https://<route-host>/#/login
```

**AKS / EKS / GKE / upstream Kubernetes** have no Route. Port-forward the
ingress service instead:

```bash
kubectl port-forward svc/k8s-triliovault-ingress-nginx-controller     -n trilio-system 8080:80
# trilio_url: http://localhost:8080/#/login
```

Forward to **localhost**, not to a remote address. The transformation flows
paste YAML through `navigator.clipboard`, which browsers expose only in a
secure context — `localhost` counts as one, `http://<remote-ip>` does not, and
the editor paste silently fails there. (On older builds the service may be
named `k8s-triliovault-ingress-gateway`; check with
`kubectl get svc -n trilio-system`.)

---

## Running the suites

### First: confirm the configuration works

Before committing to a full run, check that login alone succeeds — it exercises
the URL, credentials and cluster type in about 20 seconds:

```bash
.venv\Scripts\python -m pytest tests/test_e2e_trilio.py -k test_login --headed --tvk-config config/my-cluster-config.yaml -v
```

### Selecting stages with markers

Every stage carries a marker, so any subset can be run with `-m`. Stages are
ordered and share session state, so a marker that depends on earlier stages
must be run together with them.

| Group | Markers |
|---|---|
| UI lifecycle | `login` `app` `helm_app` `target` `policy` `backupplan` `backup` `backup_status` `snapshot` `restore` `restore_status` `cleanup` |
| UI standalone | `target_browsing` `helm_transform` `custom_transform` |
| Feature integration | `feat_apps` `feat_policy` `feat_backupplan` `feat_schedule` `feat_backup` `feat_restore` `feat_transform` `feat_scheduled` `feat_retention` `feat_policy_lifecycle` `feat_cleanup` |

```bash
# one contiguous slice of the feature suite
.venv\Scripts\python -m pytest tests/test_feature_integration.py -m "feat_apps or feat_policy or feat_backupplan" --tvk-config <cfg>
```

The three UI standalone markers are excluded from a default run and must be
asked for explicitly.

### UI end-to-end

```bash
.venv\Scripts\python -m pytest tests/test_e2e_trilio.py --headed --tvk-config config/my-cluster-config.yaml -v
```

`--headed` shows the browser; omit it to run headless. The ordered chain covers
login → install application → create target → create policy → create backup
plan → backup → verify status → snapshot stage → restore → verify status.

Three further flows are self-contained and must be selected explicitly:

```bash
# target created with browsing enabled
.venv\Scripts\python -m pytest tests/test_e2e_trilio.py -m target_browsing --tvk-config <cfg>

# Helm backup + restore applying a values transformation
.venv\Scripts\python -m pytest tests/test_e2e_trilio.py -m helm_transform --tvk-config <cfg>

# namespace backup + restore rewriting /spec/storageClassName
.venv\Scripts\python -m pytest tests/test_e2e_trilio.py -m custom_transform --tvk-config <cfg>
```

Both transformation flows assert the change actually landed on the restored
workload, not merely that the restore reported `Completed`.

### Feature integration (no browser)

```bash
.venv\Scripts\python -m pytest tests/test_feature_integration.py --tvk-config <cfg> -v
```

Covers Helm, label and namespace backup types, schedule policies, scheduled
triggering, retention and shared policy lifecycle — all through Custom
Resources. Stages are ordered and share state, so a failure names the stage
rather than collapsing a long run into one red line.

### Stress

```bash
export TVK_S3_ACCESS_KEY=... TVK_S3_SECRET_KEY=...
.venv\Scripts\python stress_tvk.py 3          # 3 rounds
.venv\Scripts\python stress_tvk.py --teardown # remove everything it created
```

Deploys three application shapes — a **Helm release** (MySQL), an
**operator-managed app** (Data Grid / Infinispan) and a **KubeVirt VM**
(Fedora) — then runs N rounds of backup and restore against all three and
prints a pass/fail matrix.

It is written to fail only for real reasons, not for want of resources:

- **Preflight gate** computes schedulable memory per worker and aborts before
  touching the cluster if headroom is insufficient. Sizing is against pod
  *requests*, not usage — pods are rejected on requests, which is how an
  apparently idle cluster still fails to schedule.
- **Restore namespaces are deleted after each round.** A restore doubles an
  application's footprint while it exists, so without this the footprint grows
  every round; steady state now stays flat regardless of round count.
- **Backups and restores are staggered**, so the three applications' datamover
  pods never start simultaneously.

Requires the Data Grid operator and OpenShift Virtualization (CNV) on the
cluster for the operator and VM workloads respectively.

---

## Standalone Playwright specs (`*.spec.js` / `*.spec.ts`)

The repository root also holds a set of standalone Playwright recordings —
`target.spec.js`, `policy.spec.js`, `restore.spec.js`, `helm_trans.spec.js`,
`custom-trans-click-test.spec.ts` and others. Each drives one console screen
directly and is useful for reproducing a single interaction or checking a
selector against a live build, without running a whole pytest suite.

**Credentials in these files are blank and must be filled in before they will
run.** They are committed empty on purpose so no secret is stored in git.

Open the spec you want and supply the values for your cluster:

```js
await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
await page.getByRole('textbox', { name: 'Username' }).fill('kubeadmin');
await page.getByRole('textbox', { name: 'Password' }).fill('');      // <-- your cluster password
await page.getByRole('textbox', { name: 'Access Key' }).fill('');    // <-- S3 access key
await page.getByRole('textbox', { name: 'Secret Key' }).fill('');    // <-- S3 secret key
```

Three things to change per spec:

1. the cluster URL in `page.goto(...)`
2. the cluster password
3. the S3 access key / secret key, in specs that create a target

Then run with the Playwright CLI:

```bash
npx playwright test target.spec.js --headed
```

Do not commit a spec after filling it in — `git diff` before staging, or keep
your edits local with `git update-index --skip-worktree <file>`.

For repeatable work prefer the pytest suites instead: they read credentials
from configuration or the environment, so nothing has to be edited in place.

---

## Retrying a restore without rebuilding everything

The transformation flows are monolithic: application install → target → backup
plan → backup → restore. When only the restore needs re-testing, these drive
just that step against a backup that already exists:

```bash
.venv\Scripts\python restore_helm_only.py   <plan> <source-ns> [restore-name]
.venv\Scripts\python restore_custom_only.py [plan] [source-ns] [restore-name]
```

`restore_custom_only.py` discovers the newest matching backup plan when given
no arguments. This turns a ~20-minute retry into ~3 minutes.

---

## Layout

```
tests/          pytest suites (UI end-to-end, feature integration)
pages/          Playwright page objects, one per console screen
utils/          cluster client, CR builders, Helm and storage-class helpers
config/         configuration templates (real configs are git-ignored)
stress_tvk.py   stress suite
explore_*.py    diagnostic scripts that dump live DOM/CR state
```

### Adding a cluster flavour

Subclass `BaseLoginPage` in `pages/login_page.py` and register it in
`LOGIN_STRATEGIES`. Nothing else changes — the target, policy, backup plan and
restore page objects are not OpenShift-specific.

---

## Notes for this environment

**Colliding CRD names.** More than one operator can define `Backup` and
`Restore`. On a cluster that also runs Data Grid or CNPG, `kubectl get backup`
may silently resolve to the wrong CRD and appear to show nothing. Always
qualify:

```bash
kubectl get backups.triliovault.trilio.io -A
```

**Restore flags are nested.** `skipIfAlreadyExists` belongs under
`spec.restoreFlags`, not at the top of `spec`, where it is silently ignored. A
namespace-scoped restore needs it, because such a backup captures OpenShift's
auto-created RBAC — including the cluster-scoped `ClusterRole system:deployer`
— which already exists at restore time. Helm-scoped plans capture only the
release's own resources and so never hit this.

**Transformation editor needs a secure context.** The console pastes
transformation YAML through `navigator.clipboard`, which browsers expose only
in a secure context. Reach the console over HTTPS or via a `localhost`-origin
port-forward; plain HTTP to a remote IP leaves the clipboard API undefined.

**Test output is not tracked.** Screenshots, logs and generated reports are
git-ignored, as is the vendored `oc` client (over GitHub's file-size limit).
