#!/usr/bin/env bash

set -o pipefail

TVK_QUICKSTART_SUCCESS=true
# shellcheck source=/dev/null
. tests/tvk-quickstart/input_config

# shellcheck disable=SC1091
export input_config=tests/tvk-quickstart/input_config

# shellcheck disable=SC1091
. tools/tvk-quickstart/tvk-quickstart.sh --source-only
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
  sed -i "s/^\(bk_plan_name\s*=\s*\).*$/\1\'trilio-test-label\'/" "$input_config"
  sed -i "s/^\(backup_name\s*=\s*\).*$/\1\'trilio-test-label\'/" "$input_config"
  sed -i "s/^\(restore_name\s*=\s*\).*$/\1\'trilio-test-label\'/" "$input_config"
  # shellcheck disable=SC1091
  . tests/tvk-quickstart/input_config
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
  sed -i "s/^\(bk_plan_name\s*=\s*\).*$/\1\'trilio-test-helm\'/" "$input_config"
  sed -i "s/^\(backup_name\s*=\s*\).*$/\1\'trilio-test-helm\'/" "$input_config"
  sed -i "s/^\(restore_name\s*=\s*\).*$/\1\'trilio-test-helm\'/" "$input_config"
  # shellcheck disable=SC1091
  . tests/tvk-quickstart/input_config
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
  sed -i "s/^\(bk_plan_name\s*=\s*\).*$/\1\'trilio-test-namespace\'/" "$input_config"
  sed -i "s/^\(backup_name\s*=\s*\).*$/\1\'trilio-test-namespace\'/" "$input_config"
  sed -i "s/^\(restore_name\s*=\s*\).*$/\1\'trilio-test-namespace\'/" "$input_config"
  # shellcheck disable=SC1091
  . tests/tvk-quickstart/input_config
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
  sed -i "s/^\(bk_plan_name\s*=\s*\).*$/\1\'trilio-test-operator\'/" "$input_config"
  sed -i "s/^\(backup_name\s*=\s*\).*$/\1\'trilio-test-operator\'/" "$input_config"
  sed -i "s/^\(restore_name\s*=\s*\).*$/\1\'trilio-test-operator\'/" "$input_config"
  # shellcheck disable=SC1091
  . tests/tvk-quickstart/input_config
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

    # shellcheck disable=SC2154
    kubectl delete po,rs,deployment,pvc,svc,sts,cm,sa,role,job,backup,backupplan,target,policy,restore,cronjob --all -n "${backup_namespace}"

    # shellcheck disable=SC2154
    kubectl delete po,rs,deployment,pvc,svc,sts,cm,sa,job,backup,backupplan,target,policy,restore,cronjob --all -n "${restore_namespace}"

    # NOTE: need sleep for resources to be garbage collected by api-controller
    sleep 20

    kubectl get tvm triliovault-manager -n "${INSTALL_NAMESPACE}" -o json | jq '.metadata.finalizers=[]' | kubectl replace -f -
    kubectl delete tvm triliovault-manager -n "${INSTALL_NAMESPACE}"

    kubectl get crd | grep trilio | awk '{print $1}' | xargs -i kubectl delete crd '{}'

    kubectl get validatingwebhookconfigurations -A | grep "${INSTALL_NAMESPACE}" | awk '{print $1}' | xargs -r kubectl delete validatingwebhookconfigurations || true
    kubectl get mutatingwebhookconfigurations -A | grep "${INSTALL_NAMESPACE}" | awk '{print $1}' | xargs -r kubectl delete mutatingwebhookconfigurations || true

    #shellcheck disable=SC2143
    helm list --namespace "${INSTALL_NAMESPACE}" | grep "k8s-triliovault" | awk '{print $1}' | xargs -i helm uninstall '{}' -n "${INSTALL_NAMESPACE}"

    # shellcheck disable=SC2154
    kubectl delete po,rs,deployment,pvc,svc,sts,cm,sa,job,backup,backupplan,target,policy,restore,cronjob --all -n "${INSTALL_NAMESPACE}"

    kubectl delete ns "${INSTALL_NAMESPACE}" --request-timeout 2m || true

    kubectl get mysqlcluster.mysql.presslabs.org/my-cluster -n tvk-restore -o json | jq '.metadata.finalizers=[]' | kubectl replace -f -
    kubectl get mysqlcluster.mysql.presslabs.org/my-cluster -n trilio-test-backup -o json | jq '.metadata.finalizers=[]' | kubectl replace -f -

    kubectl delete ns tvk-restore --request-timeout 2m || true
    kubectl delete ns trilio-test-backup --request-timeout 2m || true
    shellcheck disable=SC2154
    #s3cmd --config s3cfg_config del --recursive s3://"$bucket_name"
    # shellcheck disable=SC2154
    #s3cmd s3cmd --config s3cfg_config rb s3://"$bucket_name"
    # shellcheck disable=SC2154
    # shellcheck disable=SC2154
    exit ${rc}
  fi
}

trap "cleanup" EXIT

testinstallTVK
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
else
  TVK_install=true
fi

testconfigure_ui
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
fi

testcreate_target
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
fi

testsample_test_namespace
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
fi

testsample_test
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
fi

testsample_test_helm
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
fi

testsample_test_operator
retCode=$?
if [[ $retCode -ne 0 ]]; then
  TVK_QUICKSTART_SUCCESS=false
fi

# Check status of TVK-quickstart test-cases
if [ $TVK_QUICKSTART_SUCCESS == "true" ]; then
  echo -e "All TVK-quickstart tests Passed!"
else
  echo -e "Some TVK-quickstart Checks Failed!"
  exit 1
fi
