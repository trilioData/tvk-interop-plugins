#!/bin/bash

set -e

NAMESPACE="${NAMESPACE:-cass-oper-ns}"
OPERATOR_NAMESPACE="${OPERATOR_NAMESPACE:-openshift-operators}"
DC_NAME="${DC_NAME:-dc1}"
CLUSTER_NAME="${CLUSTER_NAME:-cassandra}"
STORAGE_CLASS="${STORAGE_CLASS:-}"
PULL_SECRET_NAME="${PULL_SECRET_NAME:-dockerhub-pull}"
IF_EXISTS_PROCEED="${IF_EXISTS_PROCEED:-true}"
SKIP_DATACENTER="${SKIP_DATACENTER:-false}"

_if_exists_proceed() {
  case "${IF_EXISTS_PROCEED}" in
    true|TRUE|True|1|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

echo "=================================================="
echo "Creating namespace if it doesn't exist"
echo "=================================================="

oc get ns ${NAMESPACE} >/dev/null 2>&1 || oc new-project ${NAMESPACE}

echo "=================================================="
echo "Granting anyuid SCC"
echo "=================================================="

oc adm policy add-scc-to-user anyuid -z default -n ${NAMESPACE}

echo "=================================================="
echo "Configuring image pull credentials"
echo "=================================================="

if [ -n "${DOCKERHUB_USERNAME}" ] && [ -n "${DOCKERHUB_PASSWORD}" ]; then
  oc create secret docker-registry ${PULL_SECRET_NAME} \
    --docker-server=https://index.docker.io/v1/ \
    --docker-username="${DOCKERHUB_USERNAME}" \
    --docker-password="${DOCKERHUB_PASSWORD}" \
    --docker-email="${DOCKERHUB_EMAIL:-unused@example.com}" \
    -n ${NAMESPACE} \
    --dry-run=client -o yaml | oc apply -f -

  oc secrets link default ${PULL_SECRET_NAME} --for=pull -n ${NAMESPACE} || true
  echo "Linked ${PULL_SECRET_NAME} to default service account"
else
  echo "DOCKERHUB_USERNAME/PASSWORD not set."
  echo "cass-config-builder is pulled from Docker Hub and will fail if the"
  echo "anonymous rate limit is already exhausted on this cluster."
fi

echo "=================================================="
echo "Installing Cassandra Operator"
echo "=================================================="

_csv_ok=false
CSV=$(oc get csv -n ${OPERATOR_NAMESPACE} --no-headers 2>/dev/null | grep cass-operator | awk '{print $1}' || true)
PHASE=""
if [ -n "$CSV" ]; then
  PHASE=$(oc get csv ${CSV} -n ${OPERATOR_NAMESPACE} -o jsonpath='{.status.phase}' 2>/dev/null || true)
fi
if [ "${PHASE}" == "Succeeded" ]; then
  if _if_exists_proceed; then
    echo "cass-operator already Succeeded — skipping install (IF_EXISTS_PROCEED=${IF_EXISTS_PROCEED})"
    _csv_ok=true
  else
    echo "ERROR: cass-operator already installed and IF_EXISTS_PROCEED=false" >&2
    exit 1
  fi
fi

if [ "${_csv_ok}" != "true" ]; then
  oc apply -f subscription.yaml

  echo "=================================================="
  echo "Waiting for Operator CSV"
  echo "=================================================="

  CSV=""
  for i in {1..60}; do
    CSV=$(oc get csv -n ${OPERATOR_NAMESPACE} --no-headers 2>/dev/null | grep cass-operator | awk '{print $1}' || true)

    if [ ! -z "$CSV" ]; then
      PHASE=$(oc get csv ${CSV} -n ${OPERATOR_NAMESPACE} -o jsonpath='{.status.phase}')
      echo "CSV=${CSV} PHASE=${PHASE}"

      if [ "${PHASE}" == "Succeeded" ]; then
        echo "Operator installation completed"
        break
      fi
    fi

    sleep 10
  done

  if [ -z "${CSV}" ] || [ "${PHASE}" != "Succeeded" ]; then
    echo "ERROR: cass-operator CSV did not reach Succeeded" >&2
    oc get csv -n ${OPERATOR_NAMESPACE} || true
    exit 1
  fi
fi

echo "=================================================="
echo "Verifying Cassandra CRDs"
echo "=================================================="

oc get crd | grep cassandra

if [ "${SKIP_DATACENTER}" = "true" ] || [ "${SKIP_DATACENTER}" = "1" ]; then
  echo "SKIP_DATACENTER=${SKIP_DATACENTER} — operator only, not creating DC/secret"
  echo "=================================================="
  echo "SUCCESS (operator only)"
  echo "=================================================="
  exit 0
fi

echo "=================================================="
echo "Creating Secret and ConfigMap"
echo "=================================================="

oc apply -f secret-cm.yaml -n ${NAMESPACE}

echo "=================================================="
echo "Creating CassandraDatacenter"
echo "=================================================="

if oc get cassandradatacenter "${DC_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  if _if_exists_proceed; then
    echo "CassandraDatacenter ${DC_NAME} already exists — skipping apply (IF_EXISTS_PROCEED=${IF_EXISTS_PROCEED})"
  else
    echo "ERROR: CassandraDatacenter ${DC_NAME} already exists and IF_EXISTS_PROCEED=false" >&2
    exit 1
  fi
else
  _dc_yaml=$(sed -e "s/^  name: dc1$/  name: ${DC_NAME}/" \
                 -e "s/^  clusterName: cassandra$/  clusterName: ${CLUSTER_NAME}/" \
                 cassandra-datacenter.yaml)
  if [ -n "${STORAGE_CLASS}" ]; then
    echo "Using storageClassName=${STORAGE_CLASS}"
    _dc_yaml=$(printf '%s\n' "${_dc_yaml}" | sed \
      "s|^[[:space:]]*#*storageClassName:.*|      storageClassName: ${STORAGE_CLASS}|")
  else
    echo "STORAGE_CLASS unset — using the cluster default StorageClass"
  fi
  printf '%s\n' "${_dc_yaml}" | oc apply -f - -n "${NAMESPACE}"
fi

echo "=================================================="
echo "Waiting for Cassandra Pod"
echo "=================================================="

READY="false"
for i in {1..60}; do

  POD=$(oc get pods -n ${NAMESPACE} --no-headers 2>/dev/null | \
    grep "cassandra-${DC_NAME}" | awk '{print $1}' | head -1 || true)

  if [ ! -z "$POD" ]; then

    READY=$(oc get pod ${POD} -n ${NAMESPACE} \
      -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || true)

    WAITING_REASON=$(oc get pod ${POD} -n ${NAMESPACE} \
      -o jsonpath='{.status.initContainerStatuses[0].state.waiting.reason}' 2>/dev/null || true)

    echo "Pod=${POD} Ready=${READY} InitWaiting=${WAITING_REASON}"

    if [ "${WAITING_REASON}" == "ImagePullBackOff" ] || [ "${WAITING_REASON}" == "ErrImagePull" ]; then
      echo "ERROR: Cassandra pod cannot pull its image." >&2
      oc describe pod ${POD} -n ${NAMESPACE} | tail -n 40 >&2
      echo >&2
      echo "The init container uses docker.io/datastax/cass-config-builder:1.0-ubi8." >&2
      echo "Unauthenticated Docker Hub pulls are rate-limited." >&2
      echo "Re-run with Docker Hub credentials:" >&2
      echo "  export DOCKERHUB_USERNAME=<user>" >&2
      echo "  export DOCKERHUB_PASSWORD=<token-or-password>" >&2
      echo "  ./install-operator.sh" >&2
      exit 1
    fi

    if [ "${READY}" == "true" ]; then
      break
    fi
  fi

  sleep 15
done

if [ "${READY}" != "true" ]; then
  echo "ERROR: Cassandra pod did not become Ready" >&2
  oc get pods -n ${NAMESPACE} || true
  oc get cassandradatacenter -n ${NAMESPACE} || true
  exit 1
fi

echo "=================================================="
echo "Verifying Secret Mount"
echo "=================================================="

oc get secret cassandra-app-secret -n ${NAMESPACE}

echo "=================================================="
echo "Verifying ConfigMap Mount"
echo "=================================================="

oc get configmap cassandra-config -n ${NAMESPACE}

echo "=================================================="
echo "SUCCESS"
echo "=================================================="

echo ""
echo "Datacenter:"
oc get cassandradatacenter -n ${NAMESPACE}

echo ""
echo "Pods:"
oc get pods -n ${NAMESPACE}
