#!/usr/bin/env bash

set -o pipefail

ONECLICK_TESTS_SUCCESS=true
# shellcheck source=/dev/null
. tests/tvk-oneclick/input_config

# shellcheck disable=SC1091
export input_config=tests/tvk-oneclick/input_config

# shellcheck disable=SC1091
. tools/tvk-oneclick/tvk-oneclick.sh --source-only
#install yq
sudo snap install yq
sudo cp /snap/bin/yq /bin/

testinstallTVK() {
  install_tvk
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test install_tvk, Expected 0 got $rc"
  fi
  return $rc
}

testconfigure_ui() {
  rc=0
  configure_ui
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test configure_ui, Expected 0 got $rc"
  fi
  return $rc
}

testcreate_target() {
  # debug message
  # shellcheck disable=SC2154
  #echo "env variable = $nfs_server_ip"
  # shellcheck disable=SC2154
  #sed -i "s/^\(nfs_server\s*=\s*\).*$/\1\'$nfs_server_ip\'/" "$input_config"
  create_target
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test create_target, Expected 0 got $rc"
    kubectl get target tvk-target -n default -o yaml
  fi
  return $rc
}

testsample_test() {
  sed -i "s/^\(backup_way\s*=\s*\).*$/\1\'Label_based\'/" "$input_config"
  sample_test
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test sample_test, Expected 0 got $rc"
  fi
  return $rc
}

testsample_test_helm() {
  sed -i "s/^\(backup_way\s*=\s*\).*$/\1\'Helm_based\'/" "$input_config"
  sample_test
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test sample_test, Expected 0 got $rc"
  fi
  return $rc
}

testsample_test_namespace() {
  sed -i "s/^\(backup_way\s*=\s*\).*$/\1\'Namespace_based\'/" "$input_config"
  sample_test
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test sample_test, Expected 0 got $rc"
  fi
  return $rc
}

testsample_test_operator() {
  sed -i "s/^\(backup_way\s*=\s*\).*$/\1\'Operator_based\'/" "$input_config"
  sample_test
  rc=$?
  # shellcheck disable=SC2181
  if [ $rc != "0" ]; then
    # shellcheck disable=SC2082
    echo "Failed - test sample_test, Expected 0 got $rc"
  fi
  return $rc
}

cleanup() {
  local rc=$?

  # cleanup namespaces and helm release
  # shellcheck disable=SC2154
  INSTALL_NAMESPACE="$tvk_ns"
  if [ "$TVK_install" == "true" ]; then
    #shellcheck disable=SC2143

    helm list --namespace "${INSTALL_NAMESPACE}" | grep "k8s-triliovault" | awk '{print $1}' | xargs -i helm uninstall '{}' -n "${INSTALL_NAMESPACE}"

    kubectl get validatingwebhookconfigurations -A | grep "${INSTALL_NAMESPACE}" | awk '{print $1}' | xargs -r kubectl delete validatingwebhookconfigurations || true
    kubectl get mutatingwebhookconfigurations -A | grep "${INSTALL_NAMESPACE}" | awk '{print $1}' | xargs -r kubectl delete mutatingwebhookconfigurations || true

    # NOTE: need sleep for resources to be garbage collected by api-controller
    sleep 20
    # shellcheck disable=SC2154
    kubectl delete po,rs,deployment,pvc,svc,sts,cm,secret,sa,role,rolebinding,job,target,backup,backupplan,policy,restore,cronjob --all -n "${INSTALL_NAMESPACE}" || true

    # shellcheck disable=SC2154
    kubectl delete po,rs,deployment,pvc,svc,sts,cm,secret,sa,role,rolebinding,job,target,backup,backupplan,policy,restore,cronjob --all -n "${backup_namespace}"

    # shellcheck disable=SC2154
    kubectl delete po,rs,deployment,pvc,svc,sts,cm,secret,sa,role,rolebinding,job,target,backup,backupplan,policy,restore,cronjob --all -n "${restore_namespace}"

    kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations -A | grep -E "${INSTALL_NAMESPACE}" || true

    kubectl get crd | grep trilio | awk '{print $1}' | xargs -i kubectl delete crd '{}'

    kubectl delete ns "${INSTALL_NAMESPACE}" --request-timeout 2m || true
    # shellcheck disable=SC2154
    s3cmd --config s3cfg_config del --recursive s3://"$bucket_name"
    # shellcheck disable=SC2154
    s3cmd s3cmd --config s3cfg_config rb s3://"$bucket_name"
    # shellcheck disable=SC2154
    #helm delete "$build_id" --namespace default
    #Destroying virtual cluster created
    # shellcheck disable=SC2154
    exit ${rc}
  fi
}

trap "cleanup" EXIT

testinstallTVK
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
else
  TVK_install=true
fi

testconfigure_ui
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
fi

testcreate_target
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
fi

testsample_test
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
fi

testsample_test_helm
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
fi

testsample_test_namespace
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
fi

testsample_test_operator
retCode=$?
if [[ $retCode -ne 0 ]]; then
  ONECLICK_TESTS_SUCCESS=false
fi

# Check status of TVK-oneclick test-cases
if [ $ONECLICK_TESTS_SUCCESS == "true" ]; then
  echo -e "All TVK-oneclick tests Passed!"
else
  echo -e "Some TVK-oneclick Checks Failed!"
  exit 1
fi
