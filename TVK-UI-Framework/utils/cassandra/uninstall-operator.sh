#!/bin/bash
#
# Remove the Cassandra install created by install-operator.sh.
# Keeps the namespace (TVK target / backup plans / backups live there).
#
#   DC -> cassandra PVCs -> secret/configmap/pull secret -> cass-operator
#

set -e

NAMESPACE="${NAMESPACE:-cass-oper-ns}"
OPERATOR_NAMESPACE="${OPERATOR_NAMESPACE:-openshift-operators}"
DC_NAME="${DC_NAME:-dc1}"
PULL_SECRET_NAME="${PULL_SECRET_NAME:-dockerhub-pull}"
KEEP_CONFIGMAP="${KEEP_CONFIGMAP:-false}"

_oc() { oc "$@"; }

_delete() {
  # oc delete ... --ignore-not-found (ok if already gone)
  _oc delete "$@" --ignore-not-found=true
}

echo "=================================================="
echo "Deleting CassandraDatacenter ${DC_NAME}"
echo "=================================================="

_delete cassandradatacenter "${DC_NAME}" -n "${NAMESPACE}" --wait=false

READY_GONE=false
for i in {1..60}; do
  if ! _oc get cassandradatacenter "${DC_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    echo "CassandraDatacenter ${DC_NAME} is gone"
    READY_GONE=true
    break
  fi
  echo "Waiting for CassandraDatacenter ${DC_NAME} to delete (${i}/60)"
  sleep 10
done

if [ "${READY_GONE}" != "true" ]; then
  echo "Clearing finalizers on CassandraDatacenter ${DC_NAME}"
  _oc patch cassandradatacenter "${DC_NAME}" -n "${NAMESPACE}" \
    --type merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
  _delete cassandradatacenter "${DC_NAME}" -n "${NAMESPACE}" --wait=false
  sleep 5
fi

echo "=================================================="
echo "Deleting Cassandra pods / PVCs"
echo "=================================================="

_oc get pvc -n "${NAMESPACE}" --no-headers 2>/dev/null \
  | awk '{print $1}' \
  | grep -iE "cassandra|${DC_NAME}" \
  | while read -r pvc; do
      echo "Deleting pvc/${pvc}"
      _delete pvc "${pvc}" -n "${NAMESPACE}" --wait=false
    done || true

_oc get pods -n "${NAMESPACE}" --no-headers 2>/dev/null \
  | awk '{print $1}' \
  | grep -iE "cassandra|${DC_NAME}" \
  | while read -r pod; do
      echo "Deleting pod/${pod}"
      _delete pod "${pod}" -n "${NAMESPACE}" --wait=false --force --grace-period=0
    done || true

for i in {1..40}; do
  LEFT=$(_oc get pods -n "${NAMESPACE}" --no-headers 2>/dev/null \
    | awk '{print $1}' | grep -iE "cassandra|${DC_NAME}" || true)
  if [ -z "${LEFT}" ]; then
    echo "Cassandra pods are gone"
    break
  fi
  echo "Waiting for Cassandra pods to terminate (${i}/40)"
  sleep 5
done

echo "=================================================="
echo "Deleting Secret (and ConfigMap unless KEEP_CONFIGMAP)"
echo "=================================================="

_delete secret cassandra-app-secret -n "${NAMESPACE}"
_delete secret "${PULL_SECRET_NAME}" -n "${NAMESPACE}"
if [ "${KEEP_CONFIGMAP}" = "true" ] || [ "${KEEP_CONFIGMAP}" = "1" ]; then
  echo "KEEP_CONFIGMAP=${KEEP_CONFIGMAP} — leaving configmap/cassandra-config"
else
  _delete configmap cassandra-config -n "${NAMESPACE}"
fi

echo "=================================================="
echo "Deleting cass-operator (subscription + CSV)"
echo "=================================================="

_delete subscription cass-operator -n "${OPERATOR_NAMESPACE}"

CSV=$(_oc get csv -n "${OPERATOR_NAMESPACE}" --no-headers 2>/dev/null \
  | awk '/cass-operator/ {print $1}' | head -1 || true)
if [ -n "${CSV}" ]; then
  echo "Deleting csv/${CSV}"
  _delete csv "${CSV}" -n "${OPERATOR_NAMESPACE}"
fi

echo "=================================================="
echo "UNINSTALL SUCCESS (namespace ${NAMESPACE} kept)"
echo "=================================================="
