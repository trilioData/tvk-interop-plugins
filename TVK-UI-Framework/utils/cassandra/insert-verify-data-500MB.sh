#!/usr/bin/env bash
#
# insert-verify-data-500MB.sh — seed and verify ~500 MB of random Cassandra data.
#
# Usage:
#   ./insert-verify-data-500MB.sh
#   source insert-verify-data-500MB.sh && insert_data && verify_data
#
# Same flow as insert-verify-data-10GB.sh: insert_data / verify_data.
# Default is 256 KiB random payload × 2000 rows ≈ 500 MiB.
#
#   TARGET_SIZE_MB=500 PAYLOAD_SIZE_BYTES=262144 ./insert-verify-data-500MB.sh
#

# -------- CONFIG --------
NAMESPACE="${NAMESPACE:-cass-oper-ns}"
DC_NAME="${DC_NAME:-dc1}"
POD_NAME="${POD_NAME:-}"
KEYSPACE="${KEYSPACE:-testkeyspace}"
TABLE="${TABLE:-randdata}"

TARGET_SIZE_MB="${TARGET_SIZE_MB:-500}"
PAYLOAD_SIZE_BYTES="${PAYLOAD_SIZE_BYTES:-262144}"
PYTHON_CONCURRENCY="${PYTHON_CONCURRENCY:-2}"
PYTHON_CHUNK="${PYTHON_CHUNK:-8}"
# ------------------------

if command -v oc &>/dev/null; then
  KUBE_CMD=(oc)
elif command -v kubectl &>/dev/null; then
  KUBE_CMD=(kubectl)
else
  echo "ERROR: oc or kubectl is required." >&2
  exit 1
fi

_log() { echo "==> $*"; }

_cass_exec() {
  "${KUBE_CMD[@]}" exec -i "${POD_NAME}" -c cassandra -n "${NAMESPACE}" -- "$@"
}

_resolve_cassandra_pod() {
  if [[ -n "${POD_NAME}" ]]; then
    if "${KUBE_CMD[@]}" get pod "${POD_NAME}" -n "${NAMESPACE}" &>/dev/null; then
      return 0
    fi
  fi

  POD_NAME="$("${KUBE_CMD[@]}" get pods -n "${NAMESPACE}" \
    -l "cassandra.datastax.com/datacenter=${DC_NAME}" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

  if [[ -z "${POD_NAME}" ]]; then
    POD_NAME="cassandra-${DC_NAME}-default-sts-0"
  fi

  _log "Using pod: ${POD_NAME}"
}

_target_bytes() {
  echo $((TARGET_SIZE_MB * 1024 * 1024))
}

_min_bytes() {
  echo $(( $(_target_bytes) * 85 / 100 ))
}

_estimated_rows() {
  local estimated_rows
  estimated_rows=$(( $(_target_bytes) / PAYLOAD_SIZE_BYTES ))
  if [[ "${estimated_rows}" -lt 1 ]]; then
    estimated_rows=1
  fi
  echo "${estimated_rows}"
}

_table_live_bytes() {
  local stats live_total
  stats="$(_cass_exec nodetool tablestats "${KEYSPACE}.${TABLE}" 2>/dev/null || true)"
  live_total="$(echo "${stats}" | awk '
    /Space used \(live\):/ {
      gsub(/,/, "", $NF)
      sum += $NF
    }
    END { printf "%.0f", sum }
  ')"
  echo "${live_total:-0}"
}

_has_enough_data() {
  local live_bytes min_bytes
  _cass_exec nodetool flush "${KEYSPACE}" >/dev/null 2>&1 || true
  live_bytes="$(_table_live_bytes)"
  min_bytes="$(_min_bytes)"
  _log "Live space for ${KEYSPACE}.${TABLE}: ${live_bytes} bytes (need >= ${min_bytes})"
  [[ -n "${live_bytes}" ]] && [[ "${live_bytes}" -ge "${min_bytes}" ]]
}

_insert_schema() {
  _log "Creating keyspace ${KEYSPACE} and table ${TABLE} (pk + random payload)"

  _cass_exec cqlsh <<EOF
CREATE KEYSPACE IF NOT EXISTS ${KEYSPACE}
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS ${KEYSPACE}.${TABLE} (
  pk int PRIMARY KEY,
  payload text
) WITH compression = {'enabled': false};
EOF
}

_generate_with_python() {
  local estimated_rows="$1"

  _log "Inserting random data with in-pod Python/cqlsh (${estimated_rows} rows, ${PAYLOAD_SIZE_BYTES} bytes each)"

  _cass_exec python3 - "${KEYSPACE}" "${TABLE}" "${estimated_rows}" \
    "${PAYLOAD_SIZE_BYTES}" "${PYTHON_CONCURRENCY}" "${PYTHON_CHUNK}" <<'PY'
from __future__ import print_function

import glob
import os
import subprocess
import sys
import time

keyspace, table = sys.argv[1], sys.argv[2]
n = int(sys.argv[3])
payload_size = int(sys.argv[4])
concurrency = int(sys.argv[5])
chunk_size = int(sys.argv[6])
progress_every = max(20, n // 20)


def _random_payload():
    # Printable random text so cqlsh and the CQL text column both accept it.
    return os.urandom((payload_size + 1) // 2).hex()[:payload_size]


def _load_driver():
    sys.path[:0] = (
        glob.glob("/opt/cassandra/lib/*.zip")
        + glob.glob("/opt/cassandra/lib/*.whl")
        + [
            "/opt/cassandra/pylib",
            "/opt/cassandra/lib",
            "/usr/share/cassandra/lib",
        ]
    )
    from cassandra.cluster import Cluster
    from cassandra.concurrent import execute_concurrent_with_args
    return Cluster, execute_concurrent_with_args


def _insert_with_driver():
    Cluster, execute_concurrent_with_args = _load_driver()
    cluster = Cluster(["127.0.0.1"])
    session = cluster.connect(keyspace)
    session.default_timeout = 30
    insert = session.prepare(
        "INSERT INTO %s (pk, payload) VALUES (?, ?)" % table
    )
    inserted = 0
    while inserted < n:
        end = min(inserted + chunk_size, n)
        params = [(i, _random_payload()) for i in range(inserted, end)]
        last_err = None
        for attempt in range(8):
            try:
                execute_concurrent_with_args(
                    session,
                    insert,
                    params,
                    concurrency=concurrency,
                    raise_on_first_error=True,
                )
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                sleep_s = min(2 ** attempt, 16)
                print("==> write retry %d after error: %s" % (attempt + 1, exc), flush=True)
                time.sleep(sleep_s)
        if last_err is not None:
            cluster.shutdown()
            raise last_err
        inserted = end
        time.sleep(0.05)
        if inserted % progress_every == 0 or inserted >= n:
            percent = inserted * 100 // n
            print("==> [%d%%] %d/%d rows inserted" % (percent, inserted, n), flush=True)
    cluster.shutdown()
    print("==> Python driver insert completed (%d rows)" % inserted, flush=True)


def _insert_with_cqlsh():
    print("==> cassandra Python driver not found; using cqlsh", flush=True)
    proc = subprocess.Popen(
        ["cqlsh"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
    )

    def send(stmt):
        proc.stdin.write(stmt + "\n")
        proc.stdin.flush()

    send("CONSISTENCY ONE;")
    send("USE %s;" % keyspace)
    inserted = 0
    while inserted < n:
        send(
            "INSERT INTO %s (pk, payload) VALUES (%d, '%s');"
            % (table, inserted, _random_payload())
        )
        inserted += 1
        if inserted % progress_every == 0 or inserted >= n:
            percent = inserted * 100 // n
            print("==> [%d%%] %d/%d rows inserted" % (percent, inserted, n), flush=True)
            time.sleep(0.2)
        elif inserted % 10 == 0:
            time.sleep(0.02)
    send("EXIT;")
    proc.stdin.close()
    out = proc.stdout.read()
    rc = proc.wait()
    if rc != 0:
        sys.stderr.write(out)
        raise SystemExit("cqlsh insert failed with exit code %d" % rc)
    print("==> cqlsh insert completed (%d rows)" % inserted, flush=True)


try:
    _insert_with_driver()
except ImportError:
    _insert_with_cqlsh()
PY
}

insert_data() {
  local estimated_rows
  _resolve_cassandra_pod
  _log "Inserting ~${TARGET_SIZE_MB} MB random data into ${KEYSPACE}.${TABLE}"

  estimated_rows="$(_estimated_rows)"
  _log "=========================================="
  _log "Random data generation"
  _log "Target size     : ${TARGET_SIZE_MB} MB"
  _log "Payload per row : ${PAYLOAD_SIZE_BYTES} bytes"
  _log "Estimated rows  : ${estimated_rows}"
  _log "=========================================="

  _insert_schema || return 1
  _generate_with_python "${estimated_rows}" || return 1
  _cass_exec nodetool flush "${KEYSPACE}"

  _log "Insert completed"
}

verify_data() {
  _resolve_cassandra_pod
  _log "Verifying on-disk size for ${KEYSPACE}.${TABLE}"

  local estimated_rows
  estimated_rows="$(_estimated_rows)"

  if ! _has_enough_data; then
    echo "ERROR: expected about ${TARGET_SIZE_MB} MB on disk" >&2
    _cass_exec nodetool tablestats "${KEYSPACE}.${TABLE}" >&2 || true
    return 1
  fi

  _log "Verification passed (~${TARGET_SIZE_MB} MB random live data, ~${estimated_rows} payload rows)"
}

if [[ "${BASH_SOURCE[0]:-$0}" == "$0" ]]; then
  insert_data || exit 1
  verify_data || exit 1
fi
