#!/bin/bash

set -e

NAMESPACE="${NAMESPACE:-cass-oper-ns}"
OPERATOR_NAMESPACE="${OPERATOR_NAMESPACE:-openshift-operators}"
DC_NAME="${DC_NAME:-dc1}"
STORAGE_CLASS="${STORAGE_CLASS:-}"
PULL_SECRET_NAME="${PULL_SECRET_NAME:-dockerhub-pull}"

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

echo "=================================================="
echo "Verifying Cassandra CRDs"
echo "=================================================="

oc get crd | grep cassandra

echo "=================================================="
echo "Creating Secret and ConfigMap"
echo "=================================================="

oc apply -f secret-cm.yaml -n ${NAMESPACE}

echo "=================================================="
echo "Creating CassandraDatacenter"
echo "=================================================="

_dc_yaml=$(sed "s/^  name: dc1$/  name: ${DC_NAME}/" cassandra-datacenter.yaml)
if [ -n "${STORAGE_CLASS}" ]; then
  echo "Using storageClassName=${STORAGE_CLASS}"
  _dc_yaml=$(printf '%s\n' "${_dc_yaml}" | sed \
    "s|^[[:space:]]*#*storageClassName:.*|      storageClassName: ${STORAGE_CLASS}|")
else
  echo "STORAGE_CLASS unset — using the cluster default StorageClass"
fi
printf '%s\n' "${_dc_yaml}" | oc apply -f - -n "${NAMESPACE}"

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
