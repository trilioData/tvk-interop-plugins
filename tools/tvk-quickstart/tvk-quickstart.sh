#!/usr/bin/env bash

#This program is use to install/configure/test TVK product with few required inputs
masterIngName=k8s-triliovault-master
masterIngName_2_7_0=k8s-triliovault
ingressGateway=k8s-triliovault-ingress-gateway
ingressGateway_2_7_0=k8s-triliovault-ingress-nginx-controller
operatorSA=triliovault-operator
tvkmanagerSA=k8s-triliovault
tvkingressSA=k8s-triliovault-ingress-nginx-admission
tvkingressSALater=k8s-triliovault-ingress-nginx

#This module is used to perform preflight check which checks if all the pre-requisites are satisfied before installing Triliovault for Kubernetes application in a Kubernetes cluster
preflight_checks() {
  ret=$(kubectl krew 2>/dev/null)
  if [[ -z "$ret" ]]; then
    echo "Please install krew plugin and then try.For information on krew installation please visit:"
    echo "https://krew.sigs.k8s.io/docs/user-guide/setup/install/"
    return 1
  fi
  ret=$(kubectl tvk-preflight --help 2>/dev/null)
  # shellcheck disable=SC2236
  if [[ ! -z "$ret" ]]; then
    echo "Skipping/Upgrading plugin tvk-preflight installation as it is already installed"
    ret_val=$(kubectl krew upgrade tvk-preflight 2>&1)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "$ret_val" | grep -q "can't upgrade, the newest version is already installed"
      ret=$?
      if [ "$ret" -ne 0 ]; then
        echo "Failed to uggrade tvk-plugins/tvk-preflight plugin"
        return 1
      else
        echo "tvk-preflight is already the newest version"
      fi
    fi
  else
    plugin_url='https://github.com/trilioData/tvk-plugins.git'
    kubectl krew index add tvk-plugins "$plugin_url" 1>> >(logit) 2>> >(logit)
    kubectl krew install tvk-plugins/tvk-preflight 1>> >(logit) 2>> >(logit)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Failed to install tvk-plugins/tvk-preflight plugin"
      return 1
    fi
  fi
  default_storage_class=$(kubectl get storageclass | grep -w '(default)' | awk 'NR==1{print $1}')
  kubectl get storageclass
  if [[ -z "${input_config}" ]]; then
    read -r -p "Provide storageclass to be used for TVK/Application Installation ($default_storage_class): " storage_class
  fi
  if [[ -z "$storage_class" ]]; then
    if [[ -z "$default_storage_class" ]]; then
      echo "Neither default storage found nor any input is provided"
      return 1
    else
      storage_class=$default_storage_class
    fi
  fi
  if [[ "$default_storage_class" != "$storage_class" ]]; then
    kubectl get storageclass "$storage_class" 1>> >(logit) 2>> >(logit)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "No storageclass $storage_class found"
      return 1
    else
      #check if selected storageclass is annoteted with "default" Label
      kubectl get storageclass "$storage_class" | grep -w '(default)' 2>> >(logit)
      retcode=$?
      if [ "$retcode" -ne 0 ]; then
        echo "The selected storageclass is not annoteted as default, patching it to act as default and used by TVK"
        echo "Removing 'default' annotation from other storageclass"
        kubectl get storageclass | grep -w '(default)' | awk '{print $1}' | xargs -I {} kubectl patch storageclass {} -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}' 2>> >(logit)
        kubectl patch storageclass "$storage_class" -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
      else
        echo "Removing 'default' annotation from other storageclass"
        kubectl get storageclass | grep -w '(default)' | grep -v "$storage_class" | awk '{print $1}' | xargs -I {} kubectl patch storageclass {} -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}' 2>> >(logit)
      fi
    fi
  fi
  # Run pre-flight check
  check=$(kubectl tvk-preflight run --storage-class "$storage_class" | tee /dev/tty)
  ret_code=$?
  if [ "$ret_code" -ne 0 ]; then
    echo "Failed to run 'kubectl tvk-preflight',please check if PATH variable for krew is set properly and then try"
  fi
  check_for_fail=$(echo "$check" | grep 'Some Pre-flight Checks Failed!')
  if [[ -z "$check_for_fail" ]]; then
    echo "All preflight checks are done and you can proceed"
  else
    if [[ -z "${input_config}" ]]; then
      echo "There are some failures"
      read -r -p "Do you want to proceed? y/n: " proceed_even_PREFLIGHT_fail
    fi
    if [[ "$proceed_even_PREFLIGHT_fail" != "Y" ]] && [[ "$proceed_even_PREFLIGHT_fail" != "y" ]]; then
      exit 1
    fi
  fi
}

#This function is used to uninstall TVK and its related resources
#This module is used to perform preflight check which checks if all the pre-requisites are satisfied before installing Triliovault for Kubernetes application in a Kubernetes cluster
tvk_uninstall() {
  ret=$(kubectl krew 2>/dev/null)
  if [[ -z "$ret" ]]; then
    echo "Please install krew plugin and then try.For information on krew installation please visit:"
    echo "https://krew.sigs.k8s.io/docs/user-guide/setup/install/"
    return 1
  fi
  ret=$(kubectl tvk-cleanup --help 2>/dev/null)
  # shellcheck disable=SC2236
  if [[ ! -z "$ret" ]]; then
    echo "Skipping/Upgrading plugin tvk-cleanup installation as it is already installed"
    ret_val=$(kubectl krew upgrade tvk-cleanup 2>&1)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "$ret_val" | grep -q "can't upgrade, the newest version is already installed"
      ret=$?
      if [ "$ret" -ne 0 ]; then
        echo "Failed to uggrade tvk-plugins/tvk-cleanup plugin"
        return 1
      else
        echo "tvk-cleanup is already the newest version"
      fi
    fi
  else
    plugin_url='https://github.com/trilioData/tvk-plugins.git'
    kubectl krew index add tvk-plugins "$plugin_url" 1>> >(logit) 2>> >(logit)
    kubectl krew install tvk-plugins/tvk-cleanup 1>> >(logit) 2>> >(logit)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Failed to install tvk-plugins/tvk-cleanup plugin" 2>> >(logit)
    fi
  fi

  # Run tvk-uninstall check
  check=$(kubectl tvk-cleanup -n -t -c -r | tee /dev/tty)
  ret_code=$?
  if [ "$ret_code" -ne 0 ]; then
    echo "Failed to run 'kubectl tvk-cleanup',please check if PATH variable for krew is set properly and then try"
  fi
}

#This function is use to compare 2 versions
vercomp() {
  if [[ $1 == "$2" ]]; then
    return 1
  fi
  ret2=$(python3 -c "from packaging import version;print(version.parse(\"$1\") < version.parse(\"$2\"))")
  ret1=$(python3 -c "from packaging import version;print(version.parse(\"$1\") == version.parse(\"$2\"))")
  if [[ $ret2 == "True" ]]; then
    return 2
  elif [[ $ret1 == "True" ]]; then
    return 1
  else
    return 3
  fi
  return 0
}

#function to print waiting symbol
wait_install() {
  runtime=$1
  spin='-\|/'
  i=0
  endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
  if [[ -z ${endtime} ]]; then
    echo "There is some issue with date usage, please check the pre-requsites in README page" 1>> >(logit) 2>> >(logit)
    echo "Something went wrong..terminating" 2>> >(logit)
  fi
  val1=$(eval "$2")
  flag=0
  while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && [[ "" == "$val1" ]] || [[ "$val1" == '{}' ]] || [[ "$val1" == 'map[]' ]]; do
    if [[ $flag -eq 0 ]]; then
      flag=1
      searchstring1="-o"
      searchstring2="2>"
      orig_cmd=$2
      cmd=${orig_cmd%$searchstring1*}
      cmd=${cmd%$searchstring2*}
      echo -e "Waiting on resource to be in expected state, running below command to check \n[$cmd]"
    fi
    i=$(((i + 1) % 4))
    printf "\r %s" "${spin:$i:1}"
    sleep .1
    val1=$(eval "$2")
  done
  echo ""
}

#This module is used to install TVK along with its free trial license
install_tvk() {
  # Add helm repo and install triliovault-operator chart
  kubectl get crd openshiftcontrollermanagers.operator.openshift.io 1>> >(logit) 2>> >(logit)
  ret_val=$?
  open_flag=0
  if [ "$ret_code" -eq 0 ]; then
    open_flag=1
  fi
  helm repo add triliovault-operator http://charts.k8strilio.net/trilio-stable/k8s-triliovault-operator 1>> >(logit) 2>> >(logit)
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "There is some error in helm update,please resolve and try again" 1>> >(logit) 2>> >(logit)
    echo "Error ading helm repo"
    return 1
  fi
  helm repo add triliovault http://charts.k8strilio.net/trilio-stable/k8s-triliovault 1>> >(logit) 2>> >(logit)
  helm repo update 1>> >(logit) 2>> >(logit)
  if [[ -z ${input_config} ]]; then
    read -r -p "Please provide the operator version to be installed (default - 2.9.2): " operator_version
    read -r -p "Please provide the triliovault manager version (default - 2.9.2): " triliovault_manager_version
    read -r -p "Namespace name in which TVK should be installed: (default - default): " tvk_ns
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$if_resource_exists_still_proceed" ]]; then
    if_resource_exists_still_proceed='y'
  fi
  if [[ -z "$operator_version" ]]; then
    operator_version='2.9.2'
  fi
  if [[ -z "$triliovault_manager_version" ]]; then
    triliovault_manager_version='2.9.2'
  fi
  if [[ -z "$tvk_ns" ]]; then
    tvk_ns="default"
  fi
  get_ns=$(kubectl get deployments -l "release=triliovault-operator" -A 2>> >(logit) | awk '{print $1}' | sed -n 2p)
  if [ -z "$get_ns" ]; then
    #Create ns for installation, if not there.
    ret=$(kubectl get ns $tvk_ns 2>/dev/null)
    if [[ -z "$ret" ]]; then
      if ! kubectl create ns $tvk_ns 2>> >(logit); then
        echo "$tvk_ns namespace creation failed"
        return 1
      fi
    fi
    # Install triliovault operator
    echo "Installing Triliovault operator..."
    helm install triliovault-operator triliovault-operator/k8s-triliovault-operator --version $operator_version -n $tvk_ns 2>> >(logit)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "There is some error in helm install triliovaul operator,please resolve and try again" 2>> >(logit)
      return 1
    fi
    if [ "$open_flag" -eq 1 ]; then
      cmd="kubectl get sa -n $tvk_ns | grep $operatorSA 2>> >(logit)"
      wait_install 10 "$cmd"
      kubectl get sa -n $tvk_ns | grep -q $operatorSA 2>> >(logit)
      ret_code=$?
      if [[ $ret_code == 0 ]]; then
        kubectl get sa -n "$tvk_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
        kubectl get sa -n "$tvk_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
      else
        echo "Something wrong when assigning privilege to Trilio operator SA"
        exit 1
      fi
    fi
    get_ns=$(kubectl get deployments -l "release=triliovault-operator" -A 2>> >(logit) | awk '{print $1}' | sed -n 2p)
  else
    tvk_ns="$get_ns"
    echo "Triliovault operator is already installed!"
    if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
      exit 1
    fi
    old_operator_version=$(helm list -n "$get_ns" | grep k8s-triliovault-operator | awk '{print $9}' | rev | cut -d- -f1 | rev | sed 's/[a-z-]//g')
    # shellcheck disable=SC2001
    new_operator_version=$(echo $operator_version | sed 's/[a-z-]//g')
    vercomp "$old_operator_version" "$new_operator_version"
    ret_val=$?
    if [[ $ret_val != 2 ]]; then
      echo "Triliovault operator cannot be upgraded, please check version number"
      if [[ $ret_val == 1 ]]; then
        echo "Triliovault operator is already at same version"
        upgrade_tvo=1
      fi
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
    else
      upgrade_tvo=1
      echo "Upgrading Triliovault operator"
      # shellcheck disable=SC2206
      semver=(${old_operator_version//./ })
      major="${semver[0]}"
      minor="${semver[1]}"
      sub_ver=${major}.${minor}
      if [[ $sub_ver == 2.0 ]]; then
        helm plugin install https://github.com/trilioData/tvm-helm-plugins >/dev/null 1>> >(logit) 2>> >(logit)
        rel_name=$(helm list | grep k8s-triliovault-operator | awk '{print $1}')
        helm tvm-upgrade --release="$rel_name" --namespace="$get_ns" 2>> >(logit)
        retcode=$?
        if [ "$retcode" -ne 0 ]; then
          echo "There is some error in helm tvm-upgrade,please resolve and try again" 2>> >(logit)
          return 1
        fi
      fi
      helm upgrade triliovault-operator triliovault-operator/k8s-triliovault-operator --version $operator_version -n "$get_ns" 2>> >(logit)
      retcode=$?
      if [ "$retcode" -ne 0 ]; then
        echo "There is some error in helm upgrade,please resolve and try again" 2>> >(logit)
        return 1
      fi
      sleep 10
    fi
  fi
  cmd="kubectl get pod -l release=triliovault-operator -n $tvk_ns -o 'jsonpath={.items[*].status.conditions[*].status}' | grep -v False"
  wait_install 10 "$cmd"
  if ! kubectl get pods -l release=triliovault-operator -n "$tvk_ns" 2>/dev/null | grep -q Running; then
    if [[ $upgrade_tvo == 1 ]]; then
      echo "Triliovault operator upgrade failed"
    else
      echo "Triliovault operator installation failed"
    fi
    return 1
  fi
  echo "Triliovault operator is running"
  #set value for tvm_name
  tvm_name="triliovault-manager"
  #check if TVK manager is installed
  ret_code=$(kubectl get tvm -A 2>/dev/null)
  if [[ -n "$ret_code" ]]; then
    echo "Triliovault manager is already installed"
    if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
      exit 1
    fi
    tvm_name=$(kubectl get tvm -A | awk '{print $2}' | sed -n 2p)
    tvk_ns="$get_ns"
    #Check if TVM can be upgraded
    old_tvm_version=$(kubectl get TrilioVaultManager -n "$get_ns" -o json | grep trilioVaultAppVersion | grep -v "{}" | awk '{print$2}' | sed 's/[a-z-]//g' | sed -e 's/^"//' -e 's/",$//' -e 's/"$//')
    # shellcheck disable=SC2001
    new_triliovault_manager_version=$(echo $triliovault_manager_version | sed 's/[a-z-]//g')
    vercomp "$old_tvm_version" "2.7.0"
    ret_ingress=$?
    if [[ $ret_ingress == 0 ]]; then
      echo "Error in getting installed TVM, please check if TVM is installed correctly"
      exit 1
    fi
    if [[ $ret_ingress == 1 ]] || [[ $ret_ingress == 3 ]]; then
      ingressGateway="${ingressGateway_2_7_0}"
      masterIngName="${masterIngName_2_7_0}"
    fi
    if [[ -z "$old_tvm_version" ]]; then
      # shellcheck disable=SC2001
      vercomp "$old_tvm_version" "$new_triliovault_manager_version"
      ret_val=$?
      if [[ $ret_val != 2 ]]; then
        echo "TVM cannot be upgraded! Please check version"
        if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
          exit 1
        fi
        install_license "$tvk_ns"
        return
      fi
    fi
    vercomp "$old_tvm_version" "$new_triliovault_manager_version"
    ret_equal=$?
    vercomp "2.6.5" "$new_triliovault_manager_version"
    ret_val1=$?
    if [[ $upgrade_tvo == 1 ]] && [[ $ret_val1 == 2 ]] && [[ $ret_equal != 1 ]]; then
      svc_type=$(kubectl get svc "$ingressGateway" -n "$tvk_ns" -o 'jsonpath={.spec.type}')
      if [[ $svc_type == LoadBalancer ]]; then
        get_host=$(kubectl get ingress "$masterIngName" -n "$tvk_ns" -o 'jsonpath={.spec.rules[0].host}')
        cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  ingressConfig:
    host: "${get_host}"
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: LoadBalancer
  applicationScope: Cluster
EOF
        retcode=$?
      elif [[ $svc_type == NodePort ]]; then
        get_host=$(kubectl get ingress "$masterIngName" -n "$tvk_ns" -o 'jsonpath={.spec.rules[0].host}')
        cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  ingressConfig:
    host: "${get_host}"
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: NodePort
  applicationScope: Cluster
EOF
        retcode=$?
      fi
      if [ "$retcode" -ne 0 ]; then
        echo "There is error upgrading triliovault manager,please resolve and try again" 2>> >(logit)
        return 0
      else
        echo "Upgrading Triliovault manager"
        echo "It will take some time for pods to update, wait for upgrade to complete before trying any operation on TVK."
        echo "To check if TVM is upgraded, run 'kubectl get tvm -n $tvk_ns'"
      fi
      tvm_upgrade=1
    elif [[ $ret_val1 == 2 ]] || [[ $ret_val1 == 1 ]]; then
      if [ "$open_flag" -eq 1 ]; then
        if [[ $ret_ingress == 1 ]] || [[ $ret_ingress == 3 ]]; then
          cmd="kubectl get sa $tvkingressSALater -n $tvk_ns 2>> >(logit)"
          wait_install 2 "$cmd"
          kubectl get sa $tvkingressSALater -n "$tvk_ns" 2>> >(logit) 1>> >(logit)
          retcode=$?
          if [[ $retcode != 0 ]]; then
            cmd="kubectl get sa $tvkingressSA -n $tvk_ns 2>> >(logit)"
            wait_install 10 "$cmd"
            kubectl get sa $tvkingressSA -n "$tvk_ns" 2>> >(logit) 1>> >(logit)
            retcode=$?
            if [[ $retcode != 0 ]]; then
              echo "Not able find service account $tvkingressSA"
              exit 1
            fi
            oc adm policy add-scc-to-user anyuid -z "$tvkingressSA" -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
            oc adm policy add-cluster-role-to-user cluster-admin -z "$tvkingressSA" -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
          fi
          oc adm policy add-scc-to-user anyuid -z "$tvkingressSALater" -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
          oc adm policy add-cluster-role-to-user cluster-admin -z "$tvkingressSALater" -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
        fi
        cmd="kubectl get sa $tvkmanagerSA -n $tvk_ns 2>> >(logit)"
        wait_install 10 "$cmd"
        kubectl get sa "$tvkmanagerSA" -n "$tvk_ns" 2>> >(logit) 1>> >(logit)
        retcode=$?
        if [[ $retcode == 0 ]]; then
          kubectl get sa -n "$get_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n "$get_ns" 1>> >(logit) 2>> >(logit)
          kubectl get sa -n "$get_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n "$get_ns" 1>> >(logit) 2>> >(logit)
        else
          echo "Something went wrong when assigning privilege to Trilio Manager SA"
          echo "or $tvkmanagerSA service account is taking more time to get created"
          echo "Please retry after 5 minutes"
          exit 1
        fi
      fi
      echo "Waiting for Pods to come up.."
      sleep 10
      if [ "$open_flag" -eq 1 ]; then
        kubectl get sa -n "$get_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n "$get_ns" 1>> >(logit) 2>> >(logit)
        kubectl get sa -n "$get_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n "$get_ns" 1>> >(logit) 2>> >(logit)
      fi
      cmd="kubectl get pods -l app=k8s-triliovault-control-plane -n $tvk_ns -ojsonpath='{.items[*].status.conditions[?(@.type == \"ContainersReady\")].status}' 2>/dev/null | grep True"
      wait_install 10 "$cmd"
      cmd="kubectl get pods -l app=k8s-triliovault-admission-webhook -n $tvk_ns -ojsonpath='{.items[*].status.conditions[?(@.type == \"ContainersReady\")].status}' 2>/dev/null | grep True"
      wait_install 10 "$cmd"
      kubectl get pods -l app=k8s-triliovault-control-plane -n "$tvk_ns" -ojsonpath='{.items[*].status.conditions[?(@.type == "ContainersReady")].status}' 2>/dev/null | grep -q True
      ret_val1=$?
      kubectl get pods -l app=k8s-triliovault-admission-webhook -n "$tvk_ns" -ojsonpath='{.items[*].status.conditions[?(@.type == "ContainersReady")].status}' 2>/dev/null | grep -q True
      ret_val=$?
      if [[ $ret_val != 0 ]] || [[ $ret_val1 != 0 ]]; then
        echo "TVM installation failed"
        exit 1
      else
        echo "TVM is up and running!"
      fi
      install_license "$tvk_ns"
      return
    else
      echo "checking if triliovault manager can be upgraded"
      tvm_upgrade=1
      vercomp "2.5" "$new_triliovault_manager_version"
      ret_val=$?
      vercomp "2.6" "$new_triliovault_manager_version"
      ret_val1=$?
      vercomp "$old_tvm_version" "2.5"
      ret_val2=$?
      if [[ $ret_val == 2 ]] || [[ $ret_val == 1 ]] && [[ $ret_val1 == 3 ]] && [[ $ret_val2 == 2 ]] || [[ $ret_val2 == 1 ]]; then
        svc_type=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.spec.type}')
        if [[ $svc_type == LoadBalancer ]]; then
          get_host=$(kubectl get ingress k8s-triliovault-ingress-master -n "$get_ns" -o 'jsonpath={.spec.rules[0].host}')
          cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  componentConfiguration:
    ingress-controller:
      service:
        type: LoadBalancer
      host: "${get_host}"
  helmVersion:
    version: v3
  applicationScope: Cluster
EOF
          retcode=$?
          if [ "$retcode" -ne 0 ]; then
            echo "There is error upgrading triliovault manager,please resolve and try again" 2>> >(logit)
            return 1
          else
            echo "Upgrading Triliovault manager"
            echo "It will take some time for pods to update, wait for upgrade to complete before trying any operation on TVK"
            echo "To check if TVM is upgraded, run 'kubectl get tvm -n $tvk_ns'"
          fi
        fi
      elif [[ $ret_val1 == 2 ]] || [[ $ret_val1 == 1 ]] && [[ $ret_val2 == 2 ]] || [[ $ret_val2 == 1 ]]; then
        svc_type=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.spec.type}')
        if [[ $svc_type == LoadBalancer ]]; then
          get_host=$(kubectl get ingress k8s-triliovault-ingress-master -n "$get_ns" -o 'jsonpath={.spec.rules[0].host}')
          cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  ingressConfig:
    host: "${get_host}"
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: LoadBalancer
  applicationScope: Cluster
EOF
          retcode=$?
          if [ "$retcode" -ne 0 ]; then
            echo "There is error upgrading triliovault manager,please resolve and try again" 2>> >(logit)
            return 0
          else
            echo "Upgrading Triliovault manager"
            echo "It will take some time for pods to update, wait for upgrade to complete before trying any operation on TVK"
            echo "To check if TVM is upgraded, run 'kubectl get tvm -n $tvk_ns'"
          fi
        fi
      elif [[ $ret_val1 == 2 ]] || [[ $ret_val1 == 1 ]]; then
        svc_type=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.spec.type}')
        if [[ $svc_type == LoadBalancer ]]; then
          get_host=$(kubectl get ingress "$masterIngName" -n "$get_ns" -o 'jsonpath={.spec.rules[0].host}')
          cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  ingressConfig:
    host: "${get_host}"
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: LoadBalancer
  applicationScope: Cluster
EOF
        elif [[ $svc_type == NodePort ]]; then
          get_host=$(kubectl get ingress "$masterIngName" -n "$get_ns" -o 'jsonpath={.spec.rules[0].host}')
          cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  ingressConfig:
    host: "${get_host}"
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: NodePort
  applicationScope: Cluster
EOF
        fi

        retcode=$?
        if [ "$retcode" -ne 0 ]; then
          echo "There is error upgrading triliovault manager,please resolve and try again" 2>> >(logit)
          return 1
        else
          echo "Upgrading Triliovault manager"
          echo "It will take some time for pods to update, wait for upgrade to complete before trying any operation on TVK"
          echo "To check if TVM is upgraded, run 'kubectl get tvm -n $tvk_ns'"
        fi
      fi
    fi
  else
    # Create TrilioVaultManager CR
    sleep 10
    vercomp "2.6" "$new_triliovault_manager_version"
    ret_val=$?
    if [[ $ret_val == 2 ]] || [[ $ret_val == 1 ]] && [[ $tvm_upgrade != 1 ]]; then

      cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: k8s
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  applicationScope: Cluster
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    web-backend:
      resources:
        requests:
          memory: "400Mi"
          cpu: "200m"
        limits:
          memory: "2584Mi"
          cpu: "1000m"
    ingress-controller:
      service:
        type: LoadBalancer
      host: "trilio.co.us"
EOF
      retcode=$?
      if [ "$retcode" -ne 0 ]; then
        echo "There is error in installingi/upgrading triliovault manager,please resolve and try again" 2>> >(logit)
        return 1
      fi
    else
      cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: triliovault
  name: ${tvm_name}
  namespace: ${tvk_ns}
spec:
  trilioVaultAppVersion: ${triliovault_manager_version}
  helmVersion:
    version: v3
  applicationScope: Cluster
EOF
      retcode=$?
      if [ "$retcode" -ne 0 ]; then
        echo "There is error in installingi/upgrading triliovault manager,please resolve and try again" 2>> >(logit)
        return 1
      fi
    fi
  fi
  sleep 5
  if [[ $tvm_upgrade == 1 ]]; then
    echo "Waiting for Pods to come up.."
  else
    if [ "$open_flag" -eq 1 ]; then
      if [[ $ret_ingress == 1 ]] || [[ $ret_ingress == 3 ]]; then
        cmd="kubectl get sa $tvkingressSALater -n $tvk_ns 2>> >(logit)"
        wait_install 2 "$cmd"
        kubectl get sa $tvkingressSALater -n "$tvk_ns" 2>> >(logit) 1>> >(logit)
        retcode=$?
        if [[ $retcode != 0 ]]; then
          cmd="kubectl get sa $tvkingressSA -n $tvk_ns 2>> >(logit)"
          wait_install 10 "$cmd"
          kubectl get sa $tvkingressSA -n "$tvk_ns" 2>> >(logit) 1>> >(logit)
          retcode=$?
          if [[ $retcode != 0 ]]; then
            echo "Not able to find service account $tvkingressSA"
          else
            {
              oc adm policy add-scc-to-user anyuid -z "$tvkingressSA" -n "$tvk_ns"
              oc adm policy add-cluster-role-to-user cluster-admin -z "$tvkingressSA" -n "$tvk_ns"
            } 1>> >(logit) 2>> >(logit)
          fi
        fi
        oc adm policy add-scc-to-user anyuid -z "$tvkingressSALater" -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
        oc adm policy add-cluster-role-to-user cluster-admin -z "$tvkingressSALater" -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
      fi
      kubectl get sa "$tvkmanagerSA" -n "$tvk_ns" 2>> >(logit) 1>> >(logit)
      return_val=$?
      if [[ $return_val == 0 ]]; then
        kubectl get sa -n "$tvk_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
        kubectl get sa -n "$tvk_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
      fi
    fi

    echo "Installing Triliovault manager...."
  fi
  cmd="kubectl get pods -l app=k8s-triliovault-control-plane -n $tvk_ns 2>/dev/null | grep Running"
  wait_install 10 "$cmd"
  cmd="kubectl get pods -l app=k8s-triliovault-admission-webhook -n $tvk_ns 2>/dev/null | grep Running"
  wait_install 10 "$cmd"
  if ! kubectl get pods -l app=k8s-triliovault-control-plane -n "$tvk_ns" 2>/dev/null | grep -q Running || ! kubectl get pods -l app=k8s-triliovault-admission-webhook -n "$tvk_ns" 2>/dev/null | grep -q Running; then
    if [[ $tvm_upgrade == 1 ]]; then
      echo "TVM upgrade failed"
    else
      echo "TVM installation failed"
    fi
    return 1
  fi
  if [[ $tvm_upgrade == 1 ]]; then
    echo "TVM is upgraded successfully!"
  else
    echo "TVK Manager is installed"
  fi
  install_license "$tvk_ns"
}

#This module is use to install license
install_license() {
  tvk_ns=$1
  flag=0
  ret=$(kubectl get license -n "$tvk_ns" 2>> >(logit) | awk '{print $1}' | sed -n 2p)
  if [[ -n "$ret" ]]; then
    ret_val=$(kubectl get license "$ret" -n "$get_ns" 2>> >(logit) | grep -q Active)
    ret_code_A=$?
    if [ "$ret_code_A" -eq 0 ]; then
      echo "License is already installed and is in active state"
      return
    fi
    #license is installed but is in inactive state
    echo "License is already installed and is in inactive state"
    flag=1
  fi

  echo "Installing required packages.."
  {
    pip3 install requests
    pip3 install beautifulsoup4
    pip3 install lxml
    pip3 install yaml
    pip3 install pyyaml

  } 1>> >(logit) 2>> >(logit)
  echo "Installing Freetrial license..."
  cat <<EOF | python3
#!/usr/bin/python3
from bs4 import BeautifulSoup
import requests
import sys
import re
import subprocess
import os
ns = "$tvk_ns"
headers = {'Content-type': 'application/x-www-form-urlencoded; charset=utf-8'}
endpoint="https://license.trilio.io/8d92edd6-514d-4acd-90f6-694cb8d83336/0061K00000fwkma"
command = "kubectl get namespace "+ns+" -o=jsonpath='{.metadata.uid}'"
result = subprocess.check_output(command, shell=True)
kubeid = result.decode("utf-8")
data = "kubescope=clusterscoped&kubeuid={0}".format(kubeid)
r = requests.post(endpoint, data=data, headers=headers)
contents=r.content
soup = BeautifulSoup(contents, 'lxml')
apply_command = soup.body.find('div', attrs={'class':'yaml-content'}).text
if($flag == 1):
  s = re.compile("name: trilio-license",re.MULTILINE)
  apply_command = re.sub(s, 'name: $ret', apply_command)
print("creating license for "+ns)
result = subprocess.check_output(apply_command.replace('kubectl', 'kubectl -n '+ns), shell=True)
EOF
  cmd="kubectl get license -n $tvk_ns 2>> >(logit) | awk '{print $2}' | sed -n 2p | grep Active"
  wait_install 5 "$cmd"
  ret=$(kubectl get license -n "$tvk_ns" 2>> >(logit) | grep -q Active)
  ret_code=$?
  if [ "$ret_code" -ne 0 ]; then
    echo "License installation failed"
    exit 1
  else
    echo "License is installed successfully"
  fi
}

#This module is used to check if TVK is installed and up and running
check_tvk_install() {
  #checking for pod status
  #{
  kubectl get svc -A | grep k8s-triliovault-operator 1>> >(logit) 2>> >(logit)
  ret_code=$?
  if [ "$ret_code" -ne 0 ]; then
    echo "Triliovault-operator is not installed..Exiting"
    exit 1
  fi
  tvk_control_name=$(kubectl get pods -l app=k8s-triliovault-control-plane -A -ojsonpath='{.items[0].metadata.name}' 2>> >(logit))
  tvk_control_namespace=$(kubectl get pods -l app=k8s-triliovault-control-plane -A -ojsonpath='{.items[0].metadata.namespace}' 2>> >(logit))
  tvk_webhook_name=$(kubectl get pods -l app=k8s-triliovault-admission-webhook -A -ojsonpath='{.items[0].metadata.name}' 2>> >(logit))
  tvk_webhook_namespace=$(kubectl get pods -l app=k8s-triliovault-admission-webhook -A -ojsonpath='{.items[0].metadata.namespace}' 2>> >(logit))
  webhook_state=$(kubectl get pod "$tvk_webhook_name" -n "$tvk_webhook_namespace" -ojsonpath='{.status.phase}' 2>> >(logit))
  if [[ "$webhook_state" != "Running" ]]; then
    echo "TVK webhook pod is not in Running state"
    return 1
  else
    kubectl get pod "$tvk_webhook_name" -n "$tvk_webhook_namespace" -ojsonpath='{.status.conditions[?(@.type == "ContainersReady")].status}' | grep -q True
    ret_code_web=$?
  fi
  control_plane_state=$(kubectl get pod "$tvk_control_name" -n "$tvk_control_namespace" -ojsonpath='{.status.phase}' 2>> >(logit))
  if [[ "$control_plane_state" != "Running" ]]; then
    echo "TVK control plane pod is not in Running state"
    return 1
  else
    kubectl get pod "$tvk_control_name" -n "$tvk_control_namespace" -ojsonpath='{.status.conditions[?(@.type == "ContainersReady")].status}' | grep -q True
    ret_code_control=$?
  fi
  #}2>> >(logit)
  if [[ $ret_code_web != 0 ]] || [[ $ret_code_control != 0 ]]; then
    return 1
  fi
  return 0

}

#This module is used to configure TVK UI
configure_ui() {
  check_tvk_install
  ret_code=$?
  if [[ $ret_code != 0 ]]; then
    echo "TVK is not in healthy state, UI configuration may fail or UI will not work as expected."
  fi
  if [[ -z ${input_config} ]]; then
    echo -e "TVK UI can be accessed using \n1.LoadBalancer \n2.NodePort \n3.PortForwarding"
    read -r -p "Please enter option: " ui_access_type
  else
    if [[ $ui_access_type == 'Loadbalancer' ]]; then
      ui_access_type=1
    elif [[ $ui_access_type == 'Nodeport' ]]; then
      ui_access_type=2
    elif [[ $ui_access_type == 'PortForwarding' ]]; then
      ui_access_type=3
    else
      echo "Wrong option selected for ui_access_type"
      return 1
    fi
  fi
  if [[ -z "$ui_access_type" ]]; then
    ui_access_type=2
  fi
  kubectl get crd openshiftcontrollermanagers.operator.openshift.io 1>> >(logit) 2>> >(logit)
  ret_val=$?
  open_flag=0
  if [ "$ret_val" -eq 0 ]; then
    oc -n openshift-ingress-operator patch ingresscontroller/default --patch '{"spec":{"routeAdmission":{"namespaceOwnership":"InterNamespaceAllowed"}}}' --type=merge
  fi
  get_node=$(kubectl get nodes | awk 'NR==2{print $1}')
  ret_val=$(kubectl get nodes "$get_node" -ojsonpath='{.spec.providerID}' 2>> >(logit) | grep digitalocean)
  ret_code=$?
  case $ui_access_type in
  3)
    get_ns=$(kubectl get deployments -l "release=triliovault-operator" -A 2>> >(logit) | awk '{print $1}' | sed -n 2p)
    echo "kubectl port-forward --address 0.0.0.0 svc/$ingressGateway -n $get_ns 80:80 &"
    echo "Copy & paste the command above into your terminal session and add a entry - '<localhost_ip> <ingress_host_name>' in /etc/hosts file.TVK management console traffic will be forwarded to your localhost IP via port 80."
    ;;
  2)
    if [[ $ret_code == 0 ]]; then
      configure_nodeport_for_tvkui "True"
    else
      configure_nodeport_for_tvkui "False"
    fi
    return 0
    ;;
  1)
    if [[ $ret_code == 0 ]]; then
      configure_loadbalancer_for_tvkUI "True"
    else
      configure_loadbalancer_for_tvkUI "False"
    fi
    return 0
    ;;
  *)
    echo "Incorrect choice"
    return
    ;;
  esac
  shift
}

#This function is used to configure TVK UI through nodeport
configure_nodeport_for_tvkui() {
  do=$?
  # shellcheck disable=SC2154
  if [[ $do -eq "True" ]]; then
    ret=$(doctl auth list 2>/dev/null)
    if [[ -z $ret ]]; then
      echo "This functionality requires doctl installed"
      echo "Please follow  to install https://docs.digitalocean.com/reference/doctl/how-to/install/ doctl"
      return 1
    fi
  fi
  if [[ -z ${input_config} ]]; then
    read -r -p "Please enter host name for tvk ingress (default - tvk-doks.com): " tvkhost_name
  fi
  if [[ -z ${tvkhost_name} ]]; then
    tvkhost_name="tvk-doks.com"
  fi
  get_ns=$(kubectl get deployments -l "release=triliovault-operator" -A 2>> >(logit) | awk '{print $1}' | sed -n 2p)
  # Getting tvm version and setting the configs accordingly
  tvm_name=$(kubectl get tvm -A | awk '{print $2}' | sed -n 2p)
  tvk_ns=$(kubectl get tvm -A | awk '{print $1}' | sed -n 2p)
  tvm_version=$(kubectl get TrilioVaultManager -n "$get_ns" -o json | grep trilioVaultAppVersion | grep -v "{}" | awk '{print$2}' | sed 's/[a-z-]//g' | sed -e 's/^"//' -e 's/",$//' -e 's/"$//')
  vercomp "$tvm_version" "2.7.0"
  ret_ingress=$?
  if [[ $ret_ingress == 0 ]]; then
    echo "Error in getting installed TVM, please check if TVM is installed correctly"
    exit 1
  fi
  if [[ $ret_ingress == 1 ]] || [[ $ret_ingress == 3 ]]; then
    ingressGateway="${ingressGateway_2_7_0}"
    masterIngName="${masterIngName_2_7_0}"
  fi
  # shellcheck disable=SC1083
  gateway=$(kubectl get pods --no-headers=true -n "$get_ns" 2>/dev/null | awk "/$ingressGateway/"{'print $1}')
  if [[ -z "$gateway" ]]; then
    echo "Not able to find $ingressGateway resource,TVK UI configuration failed"
    return 1
  fi
  node=$(kubectl get pods "$gateway" -n "$get_ns" -o jsonpath='{.spec.nodeName}' 2>> >(logit))
  ip=$(kubectl get node "$node" -n "$get_ns" -o jsonpath='{.status.addresses[?(@.type=="ExternalIP")].address}' 2>> >(logit))
  port=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}' 2>> >(logit))
  vercomp "2.6.0" "$tvm_version"
  ret_val=$?
  if [[ $ret_val == 2 ]] || [[ $ret_val == 1 ]]; then
    retry=5
    while [[ $retry -gt 0 ]]; do
      cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: k8s
  name: $tvm_name
  namespace: $tvk_ns
spec:
  applicationScope: Cluster
  ingressConfig:
    host: ${tvkhost_name}
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: NodePort
EOF
      ret_code=$?
      if [[ "$ret_code" -eq 0 ]]; then
        break
      else
        retry="$((retry - 1))"
      fi
    done
    if [[ "$ret_code" -ne 0 ]]; then
      echo "Error while configuring TVM CRD.."
      return 1
    fi
  else
    if ! kubectl patch ingress k8s-triliovault-ingress-master -n "$get_ns" -p '{"spec":{"rules":[{"host":"'"${tvkhost_name}"'"}]}}'; then
      echo "TVK UI configuration failed, please check ingress"
      return 1
    fi
    if ! kubectl patch svc "$ingressGateway" -n "$get_ns" -p '{"spec": {"type": "NodePort"}}' 1>> >(logit) 2>> >(logit); then
      echo "TVK UI configuration failed, please check ingress"
      return 1
    fi
  fi
  cmd="(kubectl get svc $ingressGateway -n $get_ns -o 'jsonpath={.spec.type}' | grep 'NodePort')"
  wait_install 20 "$cmd"
  kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.spec.type}' | grep -q 'NodePort'
  ret_code=$?
  if [[ "$retCode" -ne 0 ]]; then
    echo "Changing type of service for $ingressGateway taking long time than usual"
    return 1
  fi
  if [[ $do -eq "True" ]]; then
    doctl kubernetes cluster kubeconfig show "${cluster_name}" >config_"${cluster_name}" 2>> >(logit)
    echo "Kubeconfig file is stored at location: $PWD/config_${cluster_name}"
  fi

  if [[ -z ${ip} ]] || [[ $ip == "none" ]]; then
    echo "since the nodes are not public, we need use port forwarding"
    echo "kubectl port-forward --address 0.0.0.0 svc/$ingressGateway -n $get_ns 80:80 &"
    echo "Copy & paste the command above into your terminal session and add a entry - '<localhost_ip> $tvkhost_name' in /etc/hosts file.TVK management console traffic will be forwarded to your localhost IP via port 80."
    echo "After creating an entry,TVK UI can be accessed through http://$tvkhost_name"
  else
    echo "Please add '$ip $tvkhost_name' entry to your /etc/host file before launching the console"
    echo "After creating an entry,TVK UI can be accessed through http://$tvkhost_name:$port/login"
    echo "If there is an issue accesing TVK console please refer https://docs.trilio.io/kubernetes/support/troubleshooting-guide/issues-and-workaround#management-console-not-accessible-using-nodeport"
  fi
  echo "provide config file to login"
  echo "For https access, please refer - https://docs.trilio.io/kubernetes/management-console/user-interface/accessing-the-ui"
}

#This function is used to configure TVK UI through Loadbalancer
#This function is used to configure TVK UI through Loadbalancer
configure_loadbalancer_for_tvkUI() {
  do=$?
  if [[ $do -eq "True" ]]; then
    ret=$(doctl auth list 2>/dev/null)
    if [[ -z $ret ]]; then
      echo "This functionality requires doctl installed"
      echo "Please follow  to install https://docs.digitalocean.com/reference/doctl/how-to/install/ doctl"
      return 1
    fi
    if [[ -z ${input_config} ]]; then
      echo "To use DigitalOcean DNS, you need to register a domain name with a registrar and update your domain’s NS records to point to DigitalOcean’s name servers."
      read -r -p "Please enter domainname for cluster (Domain name you have registered and added in Doks console): " domain
      read -r -p "Please enter host name for tvk ingress (default - tvk-doks): " tvkhost_name
      read -r -p "Please enter auth token for doctl: " doctl_token
    fi
    if [[ -z ${doctl_token} ]]; then
      echo "This functionality requires Digital Ocean authentication token"
      return 1
    fi
    ret=$(doctl auth init -t "$doctl_token")
    ret_code=$?
    if [ "$ret_code" -ne 0 ]; then
      echo "Cannot authenticate with the provided doctl auth token"
      return 1
    fi
    if [[ -z ${tvkhost_name} ]]; then
      tvkhost_name="tvk-doks"
    fi
    tvk_name=$tvkhost_name.$domain
  else
    if [[ -z ${input_config} ]]; then
      read -r -p "Please enter host name for tvk ingress (default - tvk-doks.com): " tvkhost_name
    fi
    if [[ -z ${tvkhost_name} ]]; then
      tvkhost_name="tvk-doks.com"
    fi
    tvk_name=$tvkhost_name
  fi
  get_ns=$(kubectl get deployments -l "release=triliovault-operator" -A 2>> >(logit) | awk '{print $1}' | sed -n 2p)
  if [[ $do -eq "True" ]]; then
    cluster_name=$(kubectl config view --minify -o jsonpath='{.clusters[].name}' | cut -d'-' -f3-)
    if [[ -z ${cluster_name} ]]; then
      echo "Error in getting cluster name from the current-context set in kubeconfig"
      echo "Please check the current-context"
      return 1
    fi
  fi
  # Getting tvm version and setting the configs accordingly
  tvm_name=$(kubectl get tvm -A | awk '{print $2}' | sed -n 2p)
  tvk_ns=$(kubectl get tvm -A | awk '{print $1}' | sed -n 2p)
  tvm_version=$(kubectl get TrilioVaultManager -n "$get_ns" -o json | grep trilioVaultAppVersion | grep -v "{}" | awk '{print$2}' | sed 's/[a-z-]//g' | sed -e 's/^"//' -e 's/",$//' -e 's/"$//')
  vercomp "$tvm_version" "2.7.0"
  ret_ingress=$?
  if [[ $ret_ingress == 0 ]]; then
    echo "Error in getting installed TVM, please check if TVM is installed correctly"
    exit 1
  fi
  if [[ $ret_ingress == 1 ]] || [[ $ret_ingress == 3 ]]; then
    ingressGateway="${ingressGateway_2_7_0}"
    masterIngName="${masterIngName_2_7_0}"
  fi
  vercomp "2.6.0" "$tvm_version"
  ret_val=$?
  if [[ $ret_val == 2 ]] || [[ $ret_val == 1 ]]; then
    retry=5
    while [[ $retry -gt 0 ]]; do
      cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: TrilioVaultManager
metadata:
  labels:
    triliovault: k8s
  name: $tvm_name
  namespace: $tvk_ns
spec:
  applicationScope: Cluster
  ingressConfig:
    host: ${tvk_name}
  # TVK components configuration, currently supports control-plane, web, exporter, web-backend, ingress-controller, admission-webhook.
  # User can configure resources for all componentes and can configure service type and host for the ingress-controller
  componentConfiguration:
    ingress-controller:
      service:
        type: LoadBalancer
EOF
      ret_code=$?
      if [[ "$ret_code" -eq 0 ]]; then
        break
      else
        retry="$((retry - 1))"
      fi
    done
    if [[ "$ret_code" -ne 0 ]]; then
      echo "Error while configuring TVM CRD.."
      return 1
    fi
  else
    if ! kubectl patch svc "$ingressGateway" -n "$get_ns" -p '{"spec": {"type": "LoadBalancer"}}' 1>> >(logit) 2>> >(logit); then
      echo "TVK UI configuration failed, please check ingress"
      return 1
    fi
  fi
  echo "Configuring UI......This may take some time"
  sleep 10
  cmd="kubectl get svc $ingressGateway -n $get_ns -o 'jsonpath={.status.loadBalancer}'"
  wait_install 20 "$cmd"
  val_status=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.status.loadBalancer}')
  if [[ $val_status == '{}' ]] || [[ $val_status == 'map[]' ]]; then
    echo "Loadbalancer taking time to get External IP"
    return 1
  fi
  external_ip=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.status.loadBalancer.ingress[0].ip}' 2>> >(logit))
  if [[ -z "$external_ip" ]]; then
    hostname=$(kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.status.loadBalancer.ingress[0].hostname}' 2>> >(logit))
    if [[ -z "$hostname" ]]; then
      echo "ExternalIP is not set, please check configurations"
      return 1
    fi
    external_ip=$(dig "$hostname" +short | awk 'NR==2 {print $1}' 2>> >(logit))
    # Do what you want
  fi
  if [[ $ret_val != 2 ]] && [[ $ret_val != 1 ]]; then
    kubectl patch ingress k8s-triliovault-ingress-master -n "$get_ns" -p '{"spec":{"rules":[{"host":"'"${tvkhost_name}.${domain}"'"}]}}' 1>> >(logit) 2>> >(logit)
  fi
  cmd="(kubectl get svc $ingressGateway -n $get_ns -o 'jsonpath={.spec.type}' | grep 'LoadBalancer')"
  wait_install 20 "$cmd"
  kubectl get svc "$ingressGateway" -n "$get_ns" -o 'jsonpath={.spec.type}' | grep -q 'LoadBalancer'
  ret_code=$?
  if [[ "$retCode" -ne 0 ]]; then
    echo "Changing type of service for $ingressGateway taking long time than usual"
    return 1
  fi
  if [[ $do -eq "True" ]]; then
    doctl compute domain records create "${domain}" --record-type A --record-name "${tvkhost_name}" --record-data "${external_ip}" 1>> >(logit) 2>> >(logit)
    retCode=$?
    if [[ "$retCode" -ne 0 ]]; then
      echo "Failed to create record, please check domain name"
      return 1
    fi

    doctl kubernetes cluster kubeconfig show "${cluster_name}" >config_"${cluster_name}" 2>> >(logit)
    echo "Config file can be found at location: $PWD/config_${cluster_name}"
    link="http://${tvkhost_name}.${domain}/login"
    echo "You can access TVK UI: $link"
    echo "provide config file to login"
    echo "Info:UI may take 30 min to come up"
  else
    if [[ -z "$external_ip" ]]; then
      echo "Add the /etc/hosts entry: '${hostname} ${tvkhost_name}'"
      echo "Hit the URL in browser: http://${tvkhost_name}"
    else
      echo "Add the /etc/hosts entry: '${external_ip} ${tvkhost_name}'"
      echo "Hit the URL in browser: http://${tvkhost_name}"
    fi
  fi
}

create_secret() {
  secret_name=$1
  access_key=$2
  secret_key=$3
  secret_ns=$4
  cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: v1
kind: Secret
metadata:
  name: ${secret_name}
  namespace: ${secret_ns}
type: Opaque
stringData:
  accessKey: ${access_key}
  secretKey: ${secret_key}
EOF
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Secret for target creation failed..Exiting"
    return 1
  fi
}

check_target_existence() {
  target_name=$1
  target_namespace=$2
  access_key=$3
  secret_key=$4
  url=$5
  bucket_name=$6
  region=$7
  if [[ $(kubectl get target "$target_name" -n "$target_namespace" 2>> >(logit)) ]]; then
    if kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.status.status}' 2>/dev/null | grep -q Unavailable; then
      echo "Target with same name already exists but is in Unavailable state"
      return 1
    else
      secret_name=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.credentialSecret.name}')
      if [[ $secret_name == "" ]]; then
        old_access=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.accessKey}')
        old_secret=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.secretKey}')
      else
        secret_namespace=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.credentialSecret.namespace}')
        old_access=$(kubectl get secret "$secret_name" -n "$secret_namespace" -o 'jsonpath={.data.accessKey}' | base64 -d)
        old_secret=$(kubectl get secret "$secret_name" -n "$secret_namespace" -o 'jsonpath={.data.secretKey}' | base64 -d)
      fi
      old_url=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.url}')
      old_bucket=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.bucketName}')
      old_region=$(kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.spec.objectStoreCredentials.region}')
      flag=0
      new_str="Target with same name already exists"
      [[ "$old_access" != "$access_key" ]] && new_str="$new_str with different access key"
      [[ "$old_secret" != "$secret_key" ]] && new_str="$new_str with different secret key"
      [[ "$old_bucket" != "$bucket_name" ]] && new_str="$new_str with different bucket name"
      [[ "$old_region" != "$region" ]] && new_str="$new_str with different region name"
      [[ "$old_url" != "$url" ]] && new_str="$new_str with different URL name"
      echo "$new_str"
    fi
    if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
      exit 1
    else
      return 1
    fi
  fi
  return 0
}

call_s3cfg_doks() {
  access_key=$1
  secret_key=$2
  host_base=$3
  host_bucket=$4
  gpg_passphrase=$5

  cat >s3cfg_config <<-EOM
[default]
access_key = ${access_key}
access_token =
add_encoding_exts =
add_headers =
bucket_location = US
ca_certs_file =
cache_file =
check_ssl_certificate = True
check_ssl_hostname = True
cloudfront_host = cloudfront.amazonaws.com
default_mime_type = binary/octet-stream
delay_updates = False
delete_after = False
delete_after_fetch = False
delete_removed = False
dry_run = False
enable_multipart = True
encoding = UTF-8
encrypt = False
expiry_date =
expiry_days =
expiry_prefix =
follow_symlinks = False
force = False
get_continue = False
gpg_command = /usr/bin/gpg
gpg_decrypt = %(gpg_command)s -d --verbose --no-use-agent --batch --yes --passphrase-fd %(passphrase_fd)s -o %(output_file)s %(input_file)s
gpg_encrypt = %(gpg_command)s -c --verbose --no-use-agent --batch --yes --passphrase-fd %(passphrase_fd)s -o %(output_file)s %(input_file)s
gpg_passphrase = ${gpg_passphrase}
guess_mime_type = True
host_base = ${host_base}
host_bucket = ${host_bucket}
human_readable_sizes = False
invalidate_default_index_on_cf = False
invalidate_default_index_root_on_cf = True
invalidate_on_cf = False
kms_key =
limit = -1
limitrate = 0
list_md5 = False
log_target_prefix =
long_listing = False
max_delete = -1
mime_type =
multipart_chunk_size_mb = 15
multipart_max_chunks = 10000
preserve_attrs = True
progress_meter = True
proxy_host =
proxy_port = 0
put_continue = False
recursive = False
recv_chunk = 65536
reduced_redundancy = False
requester_pays = False
restore_days = 1
restore_priority = Standard
secret_key = ${secret_key}
send_chunk = 65536
server_side_encryption = False
signature_v2 = False
signurl_use_https = False
simpledb_host = sdb.amazonaws.com
skip_existing = False
socket_timeout = 300
stats = False
stop_on_error = False
storage_class =
urlencoding_mode = normal
use_http_expect = False
use_https = True
use_mime_magic = True
verbosity = WARNING
website_endpoint = http://%(bucket)s.s3-website-%(location)s.amazonaws.com/
website_error =
website_index = index.html
EOM
}

create_doks_s3() {
  if [[ -z ${input_config} ]]; then
    echo "Please go through https://docs.digitalocean.com/products/spaces/resources/s3cmd/ to know about options"
    echo "for creation of bucket, please provide input"
    read -r -p "Access_key: " access_key
    read -r -p "Secret_key: " secret_key
    read -r -p "Host Base (default - nyc3.digitaloceanspaces.com): " host_base
    read -r -p "Host Bucket (default - %(bucket)s.nyc3.digitaloceanspaces.com): " host_bucket
    read -r -p "gpg_passphrase (default - trilio): " gpg_passphrase
    read -r -p "Bucket Name: " bucket_name
    read -r -p "Target Name: " target_name
    read -r -p "Target Namespace (default): " target_namespace
    read -r -p "thresholdCapacity (Units can be[Mi/Gi/Ti]) (default - 1000Gi): " thresholdCapacity
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$gpg_passphrase" ]]; then
    gpg_passphrase="trilio"
  fi
  if [[ -z "$host_base" ]]; then
    host_base="nyc3.digitaloceanspaces.com"
  fi
  if [[ -z "$host_bucket" ]]; then
    host_bucket="%(bucket)s.nyc3.digitaloceanspaces.com"
  fi
  region="$(cut -d '.' -f 1 <<<"$host_base")"
  url="https://$host_base"

  call_s3cfg_doks "$access_key" "$secret_key" "$host_base" "$host_bucket" "$gpg_passphrase"
  region="$(cut -d '.' -f 1 <<<"$host_base")"
  #create bucket
  ret_val=$(s3cmd --config s3cfg_config mb s3://"$bucket_name" 2>> >(logit))
  ret_mgs=$?
  ret_val_error=$(s3cmd --config s3cfg_config mb s3://"$bucket_name" 2>&1)
  if [[ $ret_mgs -ne 0 ]]; then
    ret_code=$(echo "$ret_val" | grep 'Bucket already exists')
    ret_code_err=$(echo "$ret_val_error" | grep 'Bucket already exists')
    if [[ "$ret_code" ]] || [[ $ret_code_err ]]; then
      echo "WARNING: Bucket already exists"
    else
      echo "$ret_mgs"
      echo "Error in creating spaces,please check credentials"
      exit 1
    fi
  fi

  if [[ -z ${input_config} ]]; then
    read -r -p "Target Name: " target_name
    read -r -p "Target Namespace (default): " target_namespace
    read -r -p "thresholdCapacity (Units can be[Mi/Gi/Ti]) (default - 1000Gi): " thresholdCapacity
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$if_resource_exists_still_proceed" ]]; then
    if_resource_exists_still_proceed='y'
  fi
  if [[ -z "$target_name" ]]; then
    echo "Target name is required to proceed"
    exit 1
  fi
  if [[ -z "$target_namespace" ]]; then
    target_namespace="default"
  fi
  res=$(kubectl get ns $target_namespace 2>> >(logit))
  if [[ -z "$res" ]]; then
    kubectl create ns $target_namespace 2>> >(logit)
  fi
  if [[ -z "$thresholdCapacity" ]]; then
    thresholdCapacity='1000Gi'
  fi
  check_target_existence "$target_name" "$target_namespace" "$access_key" "$secret_key" "$url" "$bucket_name" "$region"
  ret_code=$?
  if [[ $ret_code -ne 0 ]]; then
    return 1
  fi
  #create S3 target
  rand_name=$(python3 -c "import random;import string;ran = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4));print (ran)")
  secret_name="$target_name-$rand_name"
  #Create secret from the credentials provided
  create_secret "$secret_name" "$access_key" "$secret_key" "${target_namespace}"
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Exiting..."
    exit 1
  fi
  cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Target
metadata:
  name: ${target_name}
  namespace: ${target_namespace}
spec:
  type: ObjectStore
  vendor: Other
  objectStoreCredentials:
    url: "${url}"
    credentialSecret:
      name: ${secret_name}
      namespace: ${target_namespace}
    bucketName: "$bucket_name"
    region: "$region"
  thresholdCapacity: $thresholdCapacity
EOF
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Target creation failed"
    return 1
  fi
}

call_s3cfg_aws() {
  access_key=$1
  secret_key=$2
  host_base=$3
  host_bucket=$4
  bucket_location=$5
  use_https=$6
  cat >s3cfg_config <<-EOM
[default]
access_key = ${access_key}
access_token =
add_encoding_exts =
add_headers =
bucket_location = ${bucket_location}
cache_file =
cloudfront_host = cloudfront.amazonaws.com
default_mime_type = binary/octet-stream
delay_updates = False
delete_after = False
delete_after_fetch = False
delete_removed = False
dry_run = False
enable_multipart = True
encoding = UTF-8
encrypt = False
expiry_date =
expiry_days =
expiry_prefix =
follow_symlinks = False
force = False
get_continue = False
gpg_command = /usr/bin/gpg
gpg_decrypt = %(gpg_command)s -d --verbose --no-use-agent --batch --yes --passphrase-fd %(passphrase_fd)s -o %(output_file)s %(input_file)s
gpg_encrypt = %(gpg_command)s -c --verbose --no-use-agent --batch --yes --passphrase-fd %(passphrase_fd)s -o %(output_file)s %(input_file)s
gpg_passphrase =
guess_mime_type = True
host_base = ${host_base}
host_bucket = ${host_bucket}
human_readable_sizes = False
ignore_failed_copy = False
invalidate_default_index_on_cf = False
invalidate_default_index_root_on_cf = True
invalidate_on_cf = False
list_md5 = False
log_target_prefix =
max_delete = -1
mime_type =
multipart_chunk_size_mb = 15
preserve_attrs = True
progress_meter = True
proxy_host =
proxy_port = 0
put_continue = False
recursive = False
recv_chunk = 4096
reduced_redundancy = False
restore_days = 1
secret_key = ${secret_key}
send_chunk = 4096
server_side_encryption = False
simpledb_host = sdb.amazonaws.com
skip_existing = False
socket_timeout = 300
urlencoding_mode = normal
use_https = ${use_https}
use_mime_magic = True
verbosity = WARNING
website_endpoint = http://%(bucket)s.s3-website-% (location)s.amazonaws.com/
website_error =
website_index = index.html
EOM
}

#Function to create Aws s3 target
create_aws_s3() {
  if [[ -z ${input_config} ]]; then
    echo "Please go through https://linux.die.net/man/1/s3cmd to know about options"
    echo "for creation of bucket, please provide input"
    read -r -p "Access_key: " access_key
    read -r -p "Secret_key: " secret_key
    read -r -p "Host Base (default - s3.amazonaws.com): " host_base
    read -r -p "Host Bucket (default - %(bucket)s.s3.amazonaws.com): " host_bucket
    read -r -p "Bucket Location Region to create bucket in. As of now the regions are:
                        us-east-1, us-west-1, us-west-2, eu-west-1, eu-
                        central-1, ap-northeast-1, ap-southeast-1, ap-
                        southeast-2, sa-east-1 (default - us-east-1): " bucket_location
    read -r -p "Bucket Name: " bucket_name
  fi
  if [[ -z "$host_base" ]]; then
    host_base="s3.amazonaws.com"
  fi
  if [[ -z "$host_bucket" ]]; then
    host_bucket="%(bucket)s.s3.amazonaws.com"
  fi
  if [[ -z "$bucket_location" ]]; then
    bucket_location="us-east-1"
  fi
  url="https://s3.amazonaws.com"

  call_s3cfg_aws "$access_key" "$secret_key" "$host_base" "$host_bucket" "$bucket_location" "True"
  #create bucket
  ret_val=$(s3cmd --config s3cfg_config mb s3://"$bucket_name" 2>&1)
  ret_mgs=$?

  if [[ "$ret_mgs" -ne 0 ]]; then
    ret_code=$(echo "$ret_val" | grep 'BucketAlreadyOwnedByYou')
    ret_code1=$(echo "$ret_val" | grep 'BucketNameUnavailable')
    if [[ "$ret_code" ]]; then
      echo "WARNING: Bucket already exists"
    elif [[ "$ret_code1" ]]; then
      echo "WARNING: Bucket Name unavailable,please use different name"
      exit 1
    else
      echo "$ret_val"
      echo "Error in creating bucket,please check credentials/name"
      exit 1
    fi
  fi

  if [[ -z ${input_config} ]]; then
    read -r -p "Target Name (default): " target_name
    read -r -p "Target Namespace: " target_namespace
    read -r -p "thresholdCapacity (Units can be[Mi/Gi/Ti]) (default - 1000Gi): " thresholdCapacity
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$if_resource_exists_still_proceed" ]]; then
    if_resource_exists_still_proceed='y'
  fi
  if [[ -z "$target_namespace" ]]; then
    target_namespace="default"
  fi
  res=$(kubectl get ns $target_namespace 2>> >(logit))
  if [[ -z "$res" ]]; then
    kubectl create ns $target_namespace 2>> >(logit)
  fi
  if [[ -z "$target_name" ]]; then
    echo "Target name is required to proceed"
    exit 1
  fi
  if [[ -z "$thresholdCapacity" ]]; then
    thresholdCapacity='1000Gi'
  fi
  check_target_existence "$target_name" "$target_namespace" "$access_key" "$secret_key" "$url" "$bucket_name" "$bucket_location"
  ret_code=$?
  if [[ $ret_code -ne 0 ]]; then
    return 1
  fi
  #create S3 target
  region=$(s3cmd --config s3cfg_config info s3://"$bucket_name"/ | grep Location | cut -d':' -f2- | sed 's/^ *//g')
  rand_name=$(python3 -c "import random;import string;ran = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4));print (ran)")
  secret_name="$target_name-$rand_name"
  #Create secret from the credentials provided
  create_secret "$secret_name" "$access_key" "$secret_key" "${target_namespace}"
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Exiting..."
    exit 1
  fi
  cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Target
metadata:
  name: ${target_name}
  namespace: ${target_namespace}
spec:
  type: ObjectStore
  vendor: AWS
  objectStoreCredentials:
    url: "$url"
    credentialSecret:
      name: ${secret_name}
      namespace: ${target_namespace}
    bucketName: "$bucket_name"
    region: "$region"
  thresholdCapacity: $thresholdCapacity
EOF
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Target creation failed"
    return 1
  fi
}

#create readymade Minio server and create target
create_readymade_minio() {
  echo "Minio requires sufficient memory.So please check memory and then configure"
  if [[ -z ${input_config} ]]; then
    read -r -p "Minio server Namespace (minio): " minio_server_namespace
    read -r -p "Bucket Name: (tvk-target): " bucket_name
    read -r -p "Target Name (tvk-target): " target_name
    read -r -p "Target Namespace (default): " target_namespace
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$minio_server_namespace" ]]; then
    minio_server_namespace="minio"
  fi
  if [[ -z "$if_resource_exists_still_proceed" ]]; then
    if_resource_exists_still_proceed='y'
  fi
  if [[ -z "$target_namespace" ]]; then
    target_namespace="default"
  fi
  if [[ -z "$target_name" ]]; then
    target_name="tvk-target"
  fi
  if [[ -z "$bucket_name" ]]; then
    bucket_name="tvk-target"
  fi
  #check if minio_server_namespace already exists
  res=$(kubectl get ns $minio_server_namespace 2>/dev/null)
  if [[ -z "$res" ]]; then
    kubectl create ns $minio_server_namespace 2>/dev/null
  fi
  helm repo add minio https://helm.min.io/ 1>> >(logit) 2>> >(logit)
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "There is some error in helm update,please resolve and try again" 1>> >(logit) 2>> >(logit)
    echo "Error ading helm repo"
    exit 1
  fi
  #check if minio server already exists
  helm show chart minio/minio -n $minio_server_namespace 1>> >(logit) 2>> >(logit)
  rel_name=$(helm list -n $minio_server_namespace | awk '$9 ~ "^minio" { print $0 }' | sed -n '1p' | awk '{print $1}')
  if [[ "$rel_name" != "" ]]; then
    echo "minio is already installed"
    #rel_name=$(helm list -n $minio_server_namespace | awk '$9 ~ "^minio" { print $0 }' | sed -n '1p'| awk '{print $1}')
    #pod_name=$(kubectl get pod -n $minio_server_namespace | grep "$rel_name" | awk '{print $1}')
    if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
      exit 1
    fi
    if [[ -z ${input_config} ]]; then
      read -r -p "Use existing minio server if available ('Y'): " use_existing_minio
    fi
    if [[ -z "$use_existing_minio" ]]; then
      use_existing_minio="y"
    fi
  fi
  if [[ "$use_existing_minio" != "Y" ]] && [[ "$use_existing_minio" != "y" ]] || [[ "$rel_name" == "" ]]; then
    ret_val=$(helm install --namespace $minio_server_namespace --generate-name minio/minio 2>> >(logit))
    #echo "$ret_val" 1>> >(logit)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "There is some error in installing minio helm chart, please resolve and try again"
      exit 1
    fi
    rel_name=$(awk 'NR==1 {print $2}' <<<"$ret_val")
  else
    if [[ -z ${input_config} ]]; then
      read -r -p "use any available minio server (y/n) ('Y') : " default_minio
    fi
    if [[ -z "$default_minio" ]]; then
      default_minio="y"
    fi
    if [[ "$default_minio" != "Y" ]] && [[ "$default_minio" != "y" ]]; then
      #read -r -p "Enter the service name of the existing minio: " pod_name
      read -r -p "Enter the namespace in which th minio pod resides: " minio_server_namespace
      read -r -p "Enter the secret name for the existing minio server: " rel_name
    else
      i=1
      minio_num=$(helm list -n "$minio_server_namespace" | awk '$9 ~ "^minio" { print $0 }' | wc -l)
      while [ "$minio_num" -ge $i ]; do
        rel_name=$(helm list -n "$minio_server_namespace" | awk '$9 ~ "^minio" { print $0 }' | sed -n $i'p' | awk '{print $1}')
        if ! kubectl get deployment "$rel_name" -n "$minio_server_namespace" -o jsonpath="{.status.conditions[*].status}" | grep -q false; then
          break
        fi
        rel_name=""
        i=$((i + 1))
      done
    fi
    if [[ "$rel_name" == "" ]]; then
      echo "No minio server is in available state"
      exit 1
    fi
  fi
  #Check if minio is deployed correctly
  #rel_name=$(echo $ret_val | awk '{print $2}')
  #pod_name=$(kubectl get pod -n "$minio_server_namespace" | grep $rel_name | awk '{print $1}')
  echo "Waiting for Minio deployment to be in Ready state.."
  cmd="kubectl get deployment $rel_name -n $minio_server_namespace -o 'jsonpath={.status.conditions[*].status}' | grep -v False"
  wait_install 1 "$cmd"
  kubectl get deployment $rel_name -n "$minio_server_namespace" -o jsonpath="{.status.conditions[*].status}" | grep -q False 1>> >(logit) 2>> >(logit)
  ret_code=$?
  if [[ $ret_code -eq 0 ]]; then
    echo "Minio deployment taking more time than usual to be in Ready state, Exiting.."
    exit 1
  fi
  #get credentials and create target crd and apply it.
  ACCESS_KEY=$(kubectl get secret $rel_name -n "$minio_server_namespace" -o jsonpath="{.data.accesskey}" | base64 --decode)
  SECRET_KEY=$(kubectl get secret $rel_name -n "$minio_server_namespace" -o jsonpath="{.data.secretkey}" | base64 --decode)
  URL="http://$rel_name.$minio_server_namespace.svc:9000"
  check_target_existence "$target_name" "$target_namespace" "$ACCESS_KEY" "$SECRET_KEY" "$URL" "$bucket_name" "us-east1"
  ret_code=$?
  if [[ $ret_code -ne 0 ]]; then
    return 1
  fi
  #create pod to run minio clinet command
  rand_name=$(python3 -c "import random;import string;ran = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4));print (ran)")
  mc_pod_nm="minio-$rand_name"
  ret_val=$(kubectl run "$mc_pod_nm" --image=minio/mc -n "$minio_server_namespace" --restart=Never --command -- /bin/sh -c 'while true; do sleep 5s; done' 1>> >(logit) 2>> >(logit))
  ret_code=$?
  if [[ "$ret_code" -ne 0 ]]; then
    echo "not able to run minio cclinet image/container"
    return 1
  fi
  kubectl get crd openshiftcontrollermanagers.operator.openshift.io 1>> >(logit) 2>> >(logit)
  ret_val=$?
  open_flag=0
  if [ "$ret_code" -eq 0 ]; then
    kubectl get sa -n "$tvk_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
    kubectl get sa -n "$tvk_ns" | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n "$tvk_ns" 1>> >(logit) 2>> >(logit)
    open_flag=1
  fi
  set -x
  echo "Waiting for minio client pod to be in Ready state.."
  cmd="kubectl get pod $mc_pod_nm -n $minio_server_namespace -o jsonpath='{.status.phase}' 2>/dev/null | grep -e Running"
  wait_install 10 "$cmd"
  kubectl get pod "$mc_pod_nm" -n "$minio_server_namespace" -o jsonpath="{.status.conditions[*].status}" | grep -q False 1>> >(logit) 2>> >(logit)
  ret_code=$?
  if [[ "$ret_code" -eq 0 ]]; then
    echo "Minio client container taking more time than usual to be in Ready state, Exiting.."
    return 1
  fi
  kubectl -n "$minio_server_namespace" exec -i "$mc_pod_nm" -- mc alias set minio "$URL" "$ACCESS_KEY" "$SECRET_KEY"
  ret_msg=$(kubectl -n "$minio_server_namespace" exec -i "$mc_pod_nm" -- mc mb minio/$bucket_name 2>&1)
  #create bucket
  ret_code=$?
  if [[ "$ret_code" -ne 0 ]]; then
    ret_val=$(echo "$ret_msg" | grep 'you already own it')
    if [[ "$ret_val" ]]; then
      echo "WARNING: Bucket already exists"
    else
      echo "Error in creating bucket,please check credentials"
      exit 1
    fi
  fi
  kubectl delete pod -n "$minio_server_namespace" "$mc_pod_nm" 1>> >(logit) 2>> >(logit)
  #create bucket
  rand_name=$(python3 -c "import random;import string;ran = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4));print (ran)")
  secret_name="$target_name-$rand_name"
  #Create secret from the credentials provided
  create_secret "$secret_name" "$ACCESS_KEY" "$SECRET_KEY" "${target_namespace}"
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Exiting..."
    exit 1
  fi
  cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Target
metadata:
  name: $target_name
  namespace: $target_namespace
spec:
  type: ObjectStore
  vendor: MinIO
  objectStoreCredentials:
    url: "$URL"
    credentialSecret:
      name: ${secret_name}
      namespace: ${target_namespace}
    bucketName: "$bucket_name"
    region: "us-east1"
  thresholdCapacity: 100Gi
EOF
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Target creation failed"
    return 1
  fi
}

create_gcp_s3() {
  if [[ -z ${input_config} ]]; then
    echo "Please go through https://linux.die.net/man/1/s3cmd to know about options"
    echo "for creation of bucket, please provide input"
    read -r -p "Access_key: " access_key
    read -r -p "Secret_key: " secret_key
    read -r -p "Host Base (default - https://storage.googleapis.com): " host_base
    read -r -p "Host Bucket (default - https://storage.googleapis.com): " host_bucket
    read -r -p "Bucket Location Region to create bucket in. As of now the regions are:
                       northamerica-northeast1, northamerica-northeast2, southamerica-east1,
                       southamerica-west1, us-central1, us-east1, us-east4, us-west1, us-west2,
                       us-west3, us-west4, europe-central2, europe-north1
                       europe-west1, europe-west2, europe-west3, europe-west4, europe-west6,
                       asia-east1, asia-east2, asia-northeast1, asia-northeast2
                       asia-northeast3, asia-south1, asia-south2, asia-southeast1,
                       asia-southeast2, australia-southeast1, australia-southeast2
                       (default - us-east-1): " bucket_location
    read -r -p "Bucket Name: " bucket_name
  fi
  if [[ -z "$host_base" ]]; then
    host_base="https://storage.googleapis.com"
  fi
  if [[ -z "$host_bucket" ]]; then
    host_bucket="https://storage.googleapis.com"
  fi
  if [[ -z "$bucket_location" ]]; then
    bucket_location="us-east-1"
  fi

  url="https://storage.googleapis.com"

  call_s3cfg_aws "$access_key" "$secret_key" "$host_base" "$host_bucket" "$bucket_location" "True"
  #create bucket
  ret_val=$(s3cmd --config s3cfg_config mb s3://"$bucket_name" 2>&1)
  ret_mgs=$?
  if [[ "$ret_mgs" -ne 0 ]]; then
    ret_code=$(echo "$ret_val" | grep 'BucketAlreadyOwnedByYou')
    ret_code1=$(echo "$ret_val" | grep 'BucketNameUnavailable')
    if [[ "$ret_code" ]]; then
      echo "WARNING: Bucket already exists"
    elif [[ "$ret_code1" ]]; then
      echo "WARNING: Bucket Name unavailable,please use different name"
      exit 1
    else
      echo "$ret_val"
      echo "Error in creating bucket,please check credentials/name"
      exit 1
    fi
  fi

  if [[ -z ${input_config} ]]; then
    read -r -p "Target Name: " target_name
    read -r -p "Target Namespace (default) : " target_namespace
    read -r -p "thresholdCapacity (Units can be[Mi/Gi/Ti]) (default - 1000Gi): " thresholdCapacity
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$if_resource_exists_still_proceed" ]]; then
    if_resource_exists_still_proceed='y'
  fi
  if [[ -z "$target_namespace" ]]; then
    target_namespace="default"
  fi
  if [[ -z "$thresholdCapacity" ]]; then
    thresholdCapacity='1000Gi'
  fi
  if [[ -z "$target_name" ]]; then
    echo "Target name is required to proceed"
    exit 1
  fi
  res=$(kubectl get ns $target_namespace 2>> >(logit))
  if [[ -z "$res" ]]; then
    kubectl create ns $target_namespace 2>> >(logit)
  fi
  check_target_existence "$target_name" "$target_namespace" "$access_key" "$secret_key" "$url" "$bucket_name" "$bucket_location"
  ret_code=$?
  if [[ $ret_code -ne 0 ]]; then
    return 1
  fi
  #create S3 target
  rand_name=$(python3 -c "import random;import string;ran = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4));print (ran)")
  secret_name="$target_name-$rand_name"
  #Create secret from the credentials provided
  create_secret "$secret_name" "$access_key" "$secret_key" "${target_namespace}"
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Exiting..."
    exit 1
  fi
  cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Target
metadata:
  name: ${target_name}
  namespace: ${target_namespace}
spec:
  type: ObjectStore
  vendor: Other
  objectStoreCredentials:
    url: "$url"
    credentialSecret:
      name: ${secret_name}
      namespace: ${target_namespace}
    bucketName: "$bucket_name"
    region: "$bucket_location"
  thresholdCapacity: $thresholdCapacity
EOF
  retcode=$?
  if [ "$retcode" -ne 0 ]; then
    echo "Target creation failed"
    return 1
  fi
}

#This module is used to create target to be used for TVK backup and restore
create_target() {
  check_tvk_install
  if [[ $ret_code != 0 ]]; then
    echo "TVK is not in healthy state, Target creation may fail or may not work as expected."
  fi
  if [[ -z ${input_config} ]]; then
    echo -e "Target can be created on NFS or s3 compatible storage\n1.NFS (default) \n2.S3"
    read -r -p "select option: " target_type
  else
    if [[ $target_type == 'NFS' ]]; then
      target_type=1
    elif [[ $target_type == 'S3' ]]; then
      target_type=2
    else
      echo "Wrong value provided for target"
    fi
  fi
  if [[ -z "$target_type" ]]; then
    target_type=1
  fi
  case $target_type in
  2)
    ret=$(s3cmd --version 2>/dev/null)
    if [[ -z $ret ]]; then
      echo "This functionality requires s3cmd utility installed"
      echo "Please check README or follow https://s3tools.org/s3cmd"
      return 1
    fi
    if [[ -z ${input_config} ]]; then
      echo -e "Please select vendor\n1.Digital_Ocean\n2.Amazon_AWS\n3.Readymade_Minio\n4.GCP"
      read -r -p "select option: " vendor_type
    else
      if [[ $vendor_type == "Digital_Ocean" ]]; then
        vendor_type=1
      elif [[ $vendor_type == "Amazon_AWS" ]]; then
        vendor_type=2
      elif [[ $vendor_type == "Readymade_Minio" ]]; then
        vendor_type=3
      elif [[ $vendor_type == "GCP" ]]; then
        vendor_type=4
      else
        echo "Wrong value provided for target"
      fi
    fi
    case $vendor_type in
    1)
      create_doks_s3
      ret_code=$?
      if [ "$ret_code" -ne 0 ]; then
        exit 1
      fi
      ;;
    2)
      create_aws_s3
      ret_code=$?
      if [ "$ret_code" -ne 0 ]; then
        exit 1
      fi
      ;;
    3)
      create_readymade_minio
      ret_code=$?
      if [ "$ret_code" -ne 0 ]; then
        exit 1
      fi
      ;;
    4)
      create_gcp_s3
      ret_code=$?
      if [ "$ret_code" -ne 0 ]; then
        exit 1
      fi
      ;;
    *)
      echo "Wrong selection"
      exit 1
      ;;
    esac
    shift
    ;;
  1)
    if [[ -z ${input_config} ]]; then
      # shellcheck disable=SC2140
      echo "NOTE: Verify if 'nfs-common' package is installed on all nodes, else NFS target creation might fail"
      read -r -p "Target Name: " target_name
      read -r -p "namespace (default): " target_namespace
      read -r -p "NFS Path (server_ip:nfs_path): " nfs_path
      read -r -p "NFSoption (default - nfsvers=4): " nfs_options
      read -r -p "thresholdCapacity (Units can be[Mi/Gi/Ti]) (default - 1000Gi): " thresholdCapacity
      read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
    fi
    if [[ -z "$if_resource_exists_still_proceed" ]]; then
      if_resource_exists_still_proceed='y'
    fi
    if [[ -z "$target_namespace" ]]; then
      target_namespace="default"
    fi
    res=$(kubectl get ns $target_namespace 2>> >(logit))
    if [[ -z "$res" ]]; then
      kubectl create ns $target_namespace 2>> >(logit)
    fi
    if [[ $(kubectl get target "$target_name" -n "$target_namespace" 2>/dev/null) ]]; then
      if kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.status.status}' 2>/dev/null | grep -q Unavailable; then
        echo "Target with same name already exists but is in Unavailable state"
        exit 1
      else
        echo "Target with same name already exists"
        return 0
      fi
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      else
        return 0
      fi
    fi
    if [[ -z "$thresholdCapacity" ]]; then
      thresholdCapacity='1000Gi'
    fi
    if [[ -z "$nfs_options" ]]; then
      nfs_options='nfsvers=4'
    fi
    echo "Creating target..."
    cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Target
metadata:
  name: ${target_name}
  namespace: ${target_namespace}
spec:
  type: NFS
  vendor: Other
  nfsCredentials:
    nfsExport: ${nfs_path}
    nfsOptions: ${nfs_options}
  thresholdCapacity: ${thresholdCapacity}
EOF
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Target creation failed"
      return 1
    fi
    ;;
  *)
    echo "Wrong selection"
    return 1
    ;;
  esac
  shift
  echo "Creating Target.."
  cmd="kubectl get target $target_name -n $target_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -e Available -e Unavailable"
  wait_install 20 "$cmd"
  if ! kubectl get target "$target_name" -n "$target_namespace" -o 'jsonpath={.status.status}' 2>/dev/null | grep -q Available; then
    echo "Failed to create target"
    exit 1
  else
    echo "Target is Available to use"
  fi
}

#module to check valid csi and if not there install it
check_csi() {
  num_nodes=$(kubectl get nodes | wc -l 2>> >(logit))
  num_nodes=$((num_nodes - 1))
  csi=$(kubectl get csidriver 2>> >(logit))
  num_csi=$(kubectl get csidriver 2>> >(logit) | wc -l 2>> >(logit))
  num_csi=$((num_csi - 1))
  flag=0
  kubectl get csidriver 2>> >(logit) | grep -q "hostpath.csi.k8s.io"
  ret_code=$?
  if [[ $num_csi -eq 1 ]] && [[ $ret_code -eq 0 ]] && [[ $num_nodes -gt 1 ]]; then
    echo "Hostpath CSI driver found"
    echo "Limitation of host path, only works for a single node, not for multiple nodes"
    flag=1
  fi
  if [[ -z $csi ]] || [[ $flag -eq 1 ]]; then
    echo "For tvk imstallation and running sample programs valid CSI driver is needed"
    #Check if cluster is OCP
    kubectl get crd openshiftcontrollermanagers.operator.openshift.io 1>> >(logit) 2>> >(logit)
    ret_val=$?
    if [ "$ret_code" -eq 0 ]; then
      echo "Longhorn installation using this plugin on OCP is not supported.."
      echo "Please install valid CSI driver and try again"
      exit 1
    fi
    #echo "Note: longhorn CSI Driver may not work as expected on OCP cluster"
    if [[ -z "${input_config}" ]]; then
      read -r -p "Do you want to install longhorn CSI driver(y): " csi_loghorn
    fi
    if [[ -z $csi_loghorn ]]; then
      csi_loghorn="y"
    fi
    if [[ "$csi_loghorn" != "Y" ]] && [[ "$csi_loghorn" != "y" ]]; then
      exit 1
    fi
    echo "Longhorn requires open-iscsi,nfs-common installed and cluster admin to enable role-based access control else the installation will fail"
    echo "Pre-requisites for the Longhorn CSI can be find at https://longhorn.io/docs/1.3.0/deploy/install/#using-the-environment-check-script"
    echo "Longhorn CSI also requires target to store volumesnapshot"

    snap_ver="release-6.0"
    #check if volumesnapshot CRDS are present
    if kubectl get volumesnapshotclasses.snapshot.storage.k8s.io 1>> >(logit) 2>> >(logit) && kubectl get volumesnapshots.snapshot.storage.k8s.io 1>> >(logit) 2>> >(logit) && kubectl get volumesnapshotcontents.snapshot.storage.k8s.io 1>> >(logit) 2>> >(logit); then
      echo "Volumesnapshot CRDS are present.."
      echo "Checking for snapshot controller"
      snap_ver="release-6.0"
      #check if snapshoter is present
      if kubectl get pods --all-namespaces -o=jsonpath='{range .items[*]}{"\n"}{range .spec.containers[*]}{.image}{", "}{end}{end}' | grep snapshot-controller 1>> >(logit) 2>> >(logit); then
        echo "Snapshot controller is installed.."
      else
        kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/deploy/kubernetes/snapshot-controller/rbac-snapshot-controller.yaml
        kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/deploy/kubernetes/snapshot-controller/setup-snapshot-controller.yaml
      fi
    else
      kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/client/config/crd/snapshot.storage.k8s.io_volumesnapshots.yaml
      kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/client/config/crd/snapshot.storage.k8s.io_volumesnapshotclasses.yaml
      kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/client/config/crd/snapshot.storage.k8s.io_volumesnapshotcontents.yaml
      kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/deploy/kubernetes/snapshot-controller/rbac-snapshot-controller.yaml
      kubectl apply -f https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${snap_ver}/deploy/kubernetes/snapshot-controller/setup-snapshot-controller.yaml

    fi
    helm repo add longhorn https://charts.longhorn.io
    helm repo update 1>> >(logit) 2>> >(logit)
    echo "Longhorn requires target to store volume snapshop"
    echo "Using local minio to create target for longhorn"
    #make changes below:
    kubectl create ns longhorn-system
    kubectl create -f https://raw.githubusercontent.com/longhorn/longhorn/master/deploy/backupstores/minio-backupstore.yaml
    runtime=20
    spin='-\|/'
    i=0
    sleep 5
    endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
    while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pods -l app=longhorn-test-minio -n longhorn-system -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
      i=$(((i + 1) % 4))
      printf "\r %s" "${spin:$i:1}"
      sleep .1
    done
    if kubectl get pods -l app=longhorn-test-minio -n longhorn-system -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
      echo "Local minio is taking more to come up which is required as longhorn snapshot store, Exiting.."
      return 1
    fi
    echo "Local minio is Up and Running to use as storage for snapshot created by longhorn CSI!"
    helm install longhorn longhorn/longhorn --namespace longhorn-system --set defaultSettings.backupTarget="s3://backupbucket@us-east-1/" --set defaultSettings.backupTargetCredentialSecret=minio-secret --set defaultSettings.defaultReplicaCount="1"
    cmd="kubectl get csidriver 2>> >(logit) | grep -w driver.longhorn.io"
    wait_install 10 "$cmd"
    kubectl get csidriver 2>> >(logit) | grep -wq driver.longhorn.io 2>> >(logit)
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Error in installing longhorn..."
      echo "Please check pod logs in longhorn-system namespace"
      exit 1
    fi
    cat <<EOF | kubectl apply -f - 2>> >(logit)
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: csi-longhorn-stclass
parameters:
  fsType: ext4
  numberOfReplicas: "1"
  staleReplicaTimeout: "30"
provisioner: driver.longhorn.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true

---
kind: VolumeSnapshotClass
apiVersion: snapshot.storage.k8s.io/v1
metadata:
  name: csi-longhorn-volsnapclass
driver: driver.longhorn.io
deletionPolicy: Delete

EOF

    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Storageclass or volumesnapshot class creation failed, pleasecheck volume CRD"
      return 1
    fi
  fi
  #check if there is storageclass with default label and valid provisioner

  prov=$(kubectl get storageclass | grep default | awk '{printf $3}')
  kubectl get storageclass | grep -q default
  # shellcheck disable=SC2181
  if [[ $? -eq 0 ]]; then
    #check if the storageclass with default label has valid provisioner
    def_store=$(kubectl get storageclass | grep -q default | awk '{printf $3}' 2>> >(logit))
    # shellcheck disable=SC2206
    def_store=($def_store)
    # shellcheck disable=SC2116
    num_of_store=$(echo ${#def_store[@]})
    if [[ $num_of_store -gt 1 ]]; then
      echo "Multiple storageclass are marked with 'default label', please mark only one storageclass as default"
      return 1
    elif [[ $num_of_store -eq 1 ]]; then
      if [[ $prov == "hostpath.csi.k8s.io" ]] && [[ $num_nodes -gt 1 ]]; then
        echo "Hostpath works only for single node..Please select other storage class as default"
        return 1
      fi
      kubectl get csidriver | grep "$prov" 1>> >(logit) 2>> >(logit)
      # shellcheck disable=SC2181
      if [[ $? -ne 0 ]]; then
        echo "Storageclass labeled as 'default' does not have valid provisioner...Exiting"
        exit 1
      fi
    fi
  else
    echo "No storageclass with default label is present, please label 'default' to one of the valid storageclass"
    return 1
  fi

  #check if volumesnapshot class is present
  kubectl get volumesnapshotclass -o jsonpath='{.items[*].driver}' 1>> >(logit) 2>> >(logit)
  # shellcheck disable=SC2181
  if [[ $? -ne 0 ]]; then
    echo "Please create a volumesnapshotclass for $prov"
    return 1
  fi
  kubectl get volumesnapshotclass -o jsonpath='{.items[*].driver}' | grep -q "$prov"
  # shellcheck disable=SC2181
  if [[ $? -ne 0 ]]; then
    echo "Please make sure that volumesnapshotclass created is consistent with default storageclass"
    return 1
  fi

}

#This module is to print wait symbol for mongofb appliction
wait_install_app() {
  backup_namespace=$2
  runtime=$1
  val1=$(eval "$3")
  spin='-\|/'
  i=0
  endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
  ret_val=0
  while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && [[ $ret_val -eq 0 ]]; do
    i=$(((i + 1) % 4))
    printf "\r %s" "${spin:$i:1}"
    sleep .1
    val1=$(eval "$3")
    ret_val=$?
  done
}

#This module is used to test TVK backup and restore for user.
sample_test() {
  #Add stable helm repo
  #check and install valid CSI
  check_csi
  ret_code=$?
  if [ "$ret_code" -ne 0 ]; then
    exit 1
  fi
  helm repo add stable https://charts.helm.sh/stable 1>> >(logit) 2>> >(logit)
  helm repo update 1>> >(logit) 2>> >(logit)
  app=""
  if [[ -z ${input_config} ]]; then
    echo -e "Select an example\n1.Label based(MySQL)\n2.Namespace based(WordPress)\n3.Operator based(MySQL Operator)\n4.Helm based(MongoDB)\n5.Transformation(PostgreSQL)"
    read -r -p "Select option: " backup_way
  else
    if [[ $backup_way == "Label_based" ]]; then
      backup_way=1
    elif [[ $backup_way == "Namespace_based" ]]; then
      backup_way=2
    elif [[ $backup_way == "Operator_based" ]]; then
      backup_way=3
    elif [[ $backup_way == "Helm_based" ]]; then
      backup_way=4
    elif [[ $backup_way == "Transformation" ]]; then
      backup_way=5
    else
      echo "Backup way is wrong/not defined"
      return 1
    fi
  fi
  if [[ -z $backup_way ]]; then
    echo "Please provide valid option..exiting.."
    return 1
  fi
  case $backup_way in
  1)
    app="label-mysql"
    ;;
  2)
    app="namespace-wordpress"
    ;;
  3)
    app="operator-mysql"
    ;;
  4)
    app="helm-mongodb"
    ;;
  5)
    app="transformation-postgresql"
    ;;
  esac
  if [[ -z ${input_config} ]]; then
    echo "Please provide input for test demo"
    read -r -p "Target Name: " target_name
    read -r -p "Target Namespace: " target_namespace
    read -r -p "Backupplan name (default - trilio-$app-testback): " bk_plan_name
    read -r -p "Backup Name (default - trilio-$app-testback): " backup_name
    read -r -p "Backup Namespace Name (default - trilio-$app-testback): " backup_namespace
    read -r -p "Proceed even if resource exists y/n (default - y): " if_resource_exists_still_proceed
  fi
  if [[ -z "$if_resource_exists_still_proceed" ]]; then
    if_resource_exists_still_proceed='y'
  fi
  if [[ -z "$backup_namespace" ]]; then
    backup_namespace="trilio-$app-testback"
  fi
  if [[ -z "$backup_name" ]]; then
    backup_name="trilio-$app-testback"
  fi
  if [[ -z "$bk_plan_name" ]]; then
    bk_plan_name="trilio-$app-testback"
  fi
  res=$(kubectl get ns $backup_namespace 2>/dev/null)
  if [[ -z "$res" ]]; then
    kubectl create ns $backup_namespace 2>> >(logit)
  fi
  storage_class=$(kubectl get storageclass | grep -w '(default)' | awk '{print $1}')
  if [[ -z "$storage_class" ]]; then
    echo "No default storage class found, need one to proceed"
    return 1
  fi
  #Check if cluster is OCP
  kubectl get crd openshiftcontrollermanagers.operator.openshift.io 1>> >(logit) 2>> >(logit)
  ret_val=$?
  open_flag=0
  if [ "$ret_code" -eq 0 ]; then
    open_flag=1
  fi

  #Check if yq is installed
  ret=$(yq -V 2>/dev/null)
  if [[ -z $ret ]]; then
    echo "This functionality requires yq utility installed"
    echo "Please check README or follow https://github.com/mikefarah/yq"
    return 1
  fi
  #Create backupplan template
  cat >backupplan.yaml <<-EOM
apiVersion: triliovault.trilio.io/v1
kind: BackupPlan
metadata:
  name: trilio-test-label
  namespace: trilio-test-backup
spec:
  backupNamespace: trilio-test-backup
  backupConfig:
    target:
      name: 
      namespace: 
    schedulePolicy:
      incrementalCron:
        schedule: "* 0 * * *"
    retentionPolicy:
      name: sample-policy
      namespace: default
EOM
  ret_code=$?
  if [ "$ret_code" -ne 0 ]; then
    echo "Cannot write backupplan.yaml file, please check file system permissions"
    return 1
  fi
  chmod 666 backupplan.yaml
  chown "$(id -u)":"$(id -g)" backupplan.yaml
  case $backup_way in
  1)
    ## Install mysql helm chart
    #check if app is already installed with same name
    if helm list -n "$backup_namespace" | grep -w -q mysql-qa; then
      echo "Application exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      echo "Waiting for application to be in Ready state"
      if [ "$open_flag" -eq 1 ]; then
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      fi
      cmd="kubectl get pods -l app=mysql-qa -n $backup_namespace 2>/dev/null | grep Running"
      wait_install 15 "$cmd"
      if ! kubectl get pods -l app=mysql-qa -n $backup_namespace 2>/dev/null | grep -q Running; then
        echo "Application taking more time than usual to be in Ready state, Exiting.."
        exit 1
      fi
    else
      helm install mysql-qa stable/mysql --set securityContext.enabled=True --set securityContext.runAsUser=0 -n $backup_namespace 1>> >(logit) 2>> >(logit)
      sleep 2
      if [ "$open_flag" -eq 1 ]; then
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      fi
      echo "Installing Application"
      sleep 10
      cmd=$(kubectl get pods -l app=mysql-qa -n $backup_namespace 2>&1)
      if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
        echo "Error in creating pod, please check security context"
        return 1
      fi
      runtime=20
      spin='-\|/'
      i=0
      sleep 5
      endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
      while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pods -l app=mysql-qa -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
        i=$(((i + 1) % 4))
        printf "\r %s" "${spin:$i:1}"
        sleep .1
      done
      if kubectl get pods -l app=mysql-qa -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
        echo "Mysql Application taking more time than usual to be in Ready state, Exiting.."
        return 1
      fi
    fi
    echo "Requested application is Up and Running!"

    yq eval -i 'del(.spec.backupPlanComponents)' backupplan.yaml 1>> >(logit) 2>> >(logit)
    yq eval -i '.spec.backupPlanComponents.custom[0].matchLabels.app="mysql-qa"' backupplan.yaml 1>> >(logit) 2>> >(logit)
    ;;
  2)
    if helm list -n $backup_namespace | grep -w -q my-wordpress 2>> >(logit); then
      echo "Application exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      echo "Waiting for application to be in Ready state"
    else
      #Add bitnami helm repo
      helm repo add bitnami https://charts.bitnami.com/bitnami 1>> >(logit) 2>> >(logit)
      echo "Installing mysql which will be used as underlying db for wordpress.."
      rand_name=$(python3 -c "import random;import string;ran = ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4));print (ran)")
      helm install "mysql-$rand_name" stable/mysql --set mysqlRootPassword=trilio,mysqlUser=trilio,mysqlPassword=trilio,mysqlDatabase=my-database --set securityContext.enabled=True --set securityContext.runAsUser=0 -n $backup_namespace 1>> >(logit) 2>> >(logit)
      if [ "$open_flag" -eq 1 ]; then
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      fi
      # shellcheck disable=SC2086
      cmd=$(kubectl get pods -l app=mysql-$rand_name -n $backup_namespace 2>&1)
      if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
        echo "Error in creating pod, please check security context"
        return 1
      fi
      runtime=20
      spin='-\|/'
      i=0
      sleep 5
      endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
      # shellcheck disable=SC2086
      while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pods -l app=mysql-$rand_name -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
        i=$(((i + 1) % 4))
        printf "\r %s" "${spin:$i:1}"
        sleep .1
      done
      # shellcheck disable=SC2086
      if kubectl get pods -l app=mysql-$rand_name -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
        echo "Wordpress underlying Mysql Application taking more time than usual to be in Ready state, Exiting.."
        return 1
      fi
      cat >initcontainer.yaml <<-EOM
initContainers:
  - name: volume-permissions
    image: bitnami/minideb
    imagePullPolicy: Always
    command: ['sh', '-c', 'chown 1001:1001 /bitnami/wordpress']
    volumeMounts:
    - mountPath: /bitnami/wordpress
      name: wordpress-data
      subPath: wordpress
EOM
      # shellcheck disable=SC2086
      helm install my-wordpress bitnami/wordpress --set mariadb.enabled=false --set externalDatabase.host=mysql-$rand_name.$backup_namespace.svc.cluster.local --set externalDatabase.user=trilio --set externalDatabase.password=trilio --set externalDatabase.database=my-database --set externalDatabase.port=3306 -f initcontainer.yaml -n $backup_namespace 1>> >(logit) 2>> >(logit)

      echo "Installing Application"
    fi
    if [ "$open_flag" -eq 1 ]; then
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
    fi
    runtime=20
    spin='-\|/'
    i=0
    sleep 5
    cmd=$(kubectl get pod -l app.kubernetes.io/instance=my-wordpress -n $backup_namespace 2>&1)
    if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
      echo "Error in creating pod, please check security context"
      return 1
    fi
    endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
    while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pod -l app.kubernetes.io/instance=my-wordpress -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
      i=$(((i + 1) % 4))
      printf "\r %s" "${spin:$i:1}"
      sleep .1
    done
    if kubectl get pod -l app.kubernetes.io/instance=my-wordpress -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
      echo "Wordpress Application taking more time than usual to be in Ready state, Exiting.."
      return 1
    fi
    echo "Requested application is Up and Running!"
    yq eval -i 'del(.spec.backupPlanComponents)' backupplan.yaml 1>> >(logit) 2>> >(logit)
    rm initcontainer.yaml 1>> >(logit) 2>> >(logit)
    ;;
  3)
    if helm list -n $backup_namespace | grep -w -q mysql-operator 2>> >(logit); then
      echo "Application exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      echo "Waiting for application to be in Ready state"
    else
      echo "MySQL operator will require enough resources, else the deployment will fail"
      helm repo add bitpoke https://helm-charts.bitpoke.io 1>> >(logit) 2>> >(logit)
      cat >initcontainer.yaml <<-EOM
initContainers:
       - name: volume-permissions
         image: busybox
         securityContext:
           runAsUser: 0
         command:
           - sh
           - -c
           - chmod 750 /data/mysql; chown 999:999 /data/mysql
         volumeMounts:
           - name: data
             mountPath: /data/mysql
EOM
      errormessage=$(helm install mysql-operator bitpoke/mysql-operator --set orchestrator.persistence.enabled=false -f initcontainer.yaml -n $backup_namespace 2>> >(logit))
      if echo "$errormessage" | grep -Eq 'Error:|error:'; then
        echo "Mysql operator Installation failed with error: $errormessage"
        return 1
      fi
      echo "Installing MySQL Operator..."
    fi
    if [ "$open_flag" -eq 1 ]; then
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
    fi
    runtime=25
    spin='-\|/'
    i=0
    sleep 5
    cmd=$(kubectl get pod -l app.kubernetes.io/name=mysql-operator -n $backup_namespace 2>&1)
    if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
      echo "Error in creating pod, please check security context"
      return 1
    fi
    endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
    while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pod -l app.kubernetes.io/name=mysql-operator -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
      i=$(((i + 1) % 4))
      printf "\r %s" "${spin:$i:1}"
      sleep .1
    done
    if kubectl get pod -l app.kubernetes.io/name=mysql-operator -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
      echo "MySQL operator taking more time than usual to be in Ready state, Exiting.."
      return 1
    fi
    if ! kubectl get pods -l mysql.presslabs.org/cluster=my-cluster -n $backup_namespace --ignore-not-found 1>> >(logit); then
      echo "Mysql cluster already exists.."
      echo "Waiting for application to be in Ready state"
    else
      #Create a MySQL cluster
      kubectl apply -f https://raw.githubusercontent.com/bitpoke/mysql-operator/master/examples/example-cluster-secret.yaml -n $backup_namespace 2>> >(logit)
      kubectl apply -f https://raw.githubusercontent.com/bitpoke/mysql-operator/master/examples/example-cluster.yaml -n $backup_namespace 2>> >(logit)
      echo "Installing MySQL cluster..."
      sleep 10
    fi
    if [ "$open_flag" -eq 1 ]; then
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
    fi
    runtime=25
    spin='-\|/'
    i=0
    sleep 5
    cmd=$(kubectl get pod -l mysql.presslabs.org/cluster=my-cluster -n $backup_namespace 2>&1)
    if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
      echo "Error in creating pod, please check security context"
      return 1
    fi
    endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
    while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pods -l mysql.presslabs.org/cluster=my-cluster -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
      i=$(((i + 1) % 4))
      printf "\r %s" "${spin:$i:1}"
      sleep .1
    done
    sleep 5
    while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pods -l mysql.presslabs.org/cluster=my-cluster -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
      i=$(((i + 1) % 4))
      printf "\r %s" "${spin:$i:1}"
      sleep .1
    done
    if kubectl get pods -l mysql.presslabs.org/cluster=my-cluster -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
      echo "MySQL cluster taking more time than usual to be in Ready state, Exiting.."
      return 1
    fi
    echo "Requested application is Up and Running!"
    #Creating backupplan
    {
      yq eval -i 'del(.spec.backupPlanComponents)' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].operatorId="my-cluster"' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].customResources[0].groupVersionKind.group="mysql.presslabs.org" | .spec.backupPlanComponents.operators[0].customResources[0].groupVersionKind.group style="double"' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].customResources[0].groupVersionKind.version="v1alpha1" | .spec.backupPlanComponents.operators[0].customResources[0].groupVersionKind.version style="double"' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].customResources[0].groupVersionKind.kind="MysqlCluster" | .spec.backupPlanComponents.operators[0].customResources[0].groupVersionKind.kind style="double"' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].customResources[0].objects[0]="my-cluster"' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].operatorResourceSelector[0].matchLabels."app.kubernetes.io/name"="mysql-operator"' backupplan.yaml
      yq eval -i '.spec.backupPlanComponents.operators[0].applicationResourceSelector[0].matchLabels."app.kubernetes.io/name"="mysql"' backupplan.yaml
      rm initcontainer.yaml
    } 1>> >(logit) 2>> >(logit)
    ;;
  4)
    if helm list -n $backup_namespace | grep -q -w mongotest; then
      echo "Application exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      echo "Waiting for application to be in Ready state"
    else
      {
        helm repo add bitnami https://charts.bitnami.com/bitnami
        helm repo update 1>> >(logit)
        helm install mongotest bitnami/mongodb -n $backup_namespace
        # shellcheck disable=SC2155
        export MONGODB_ROOT_PASSWORD=$(kubectl get secret --namespace $backup_namespace mongotest-mongodb -o jsonpath="{.data.mongodb-root-password}" | base64 --decode)
      } 2>> >(logit)
      echo "Installing App..."
    fi
    if [ "$open_flag" -eq 1 ]; then
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
    fi
    sleep 5
    cmd=$(kubectl get pod -l app.kubernetes.io/name=mongodb -n $backup_namespace 2>&1)
    if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
      echo "Error in creating pod, please check security context"
      return 1
    fi
    # shellcheck disable=SC2016
    cmd='kubectl get pod -l app.kubernetes.io/name=mongodb -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False'
    wait_install_app 30 "$backup_namespace" "$cmd"
    if kubectl get pod -l app.kubernetes.io/name=mongodb -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
      echo "Mongodb Application taking more time than usual to be in Ready state, Exiting.."
      echo "Retrying by changing volume permissions"
      helm upgrade mongotest bitnami/mongodb --set volumePermissions.enabled=true --set auth.rootPassword="$MONGODB_ROOT_PASSWORD" -n $backup_namespace
      wait_install_app 15 "$backup_namespace" "$cmd"
      if kubectl get pod -l app.kubernetes.io/name=mongodb -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
        echo "Failed to install Mongodb Application"
        return 1
      fi
    fi
    echo "Requested application is Up and Running!"
    yq eval -i 'del(.spec.backupPlanComponents)' backupplan.yaml 1>> >(logit) 2>> >(logit)
    yq eval -i '.spec.backupPlanComponents.helmReleases[0]="mongotest"' backupplan.yaml 1>> >(logit) 2>> >(logit)
    ;;
  5)
    ## Install postgresql helm chart
    #check if app is already installed with same name
    if helm list -n "$backup_namespace" | grep -w -q postgresql; then
      echo "Application exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      echo "Waiting for application to be in Ready state"
      if [ "$open_flag" -eq 1 ]; then
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      fi
      cmd="kubectl get pods -l app.kubernetes.io/name=postgresql -n $backup_namespace 2>/dev/null | grep Running"
      wait_install 15 "$cmd"
      if ! kubectl get pods -l app.kubernetes.io/name=postgresql -n $backup_namespace 2>/dev/null | grep -q Running; then
        echo "Application taking more time than usual to be in Ready state, Exiting.."
        exit 1
      fi
    else
      echo "There should be only one storageclass with 'default' label, else the installation would fail"
      {
        helm repo add bitnami https://charts.bitnami.com/bitnami
        helm repo update 1>> >(logit)
        helm install postgresql bitnami/postgresql --set securityContext.enabled=True --set securityContext.runAsUser=0 --set volumePermissions.enabled=true -n $backup_namespace 1>> >(logit)
        sleep 2
      } 2>> >(logit)
      if [ "$open_flag" -eq 1 ]; then
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
        kubectl get sa -n $backup_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $backup_namespace 1>> >(logit) 2>> >(logit)
      fi
      echo "Installing Application"
      sleep 10
      cmd=$(kubectl get pods -l app.kubernetes.io/name=postgresql -n $backup_namespace 2>&1)
      if [[ $cmd == "No resources found in $backup_namespace namespace." ]]; then
        echo "Error in creating pod, please check security context"
        return 1
      fi
      runtime=20
      spin='-\|/'
      i=0
      sleep 5
      endtime=$(python3 -c "import time;timeout = int(time.time()) + 60*$runtime;print(\"{0}\".format(timeout))")
      while [[ $(python3 -c "import time;timeout = int(time.time());print(\"{0}\".format(timeout))") -le $endtime ]] && kubectl get pods -l app.kubernetes.io/name=postgresql -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; do
        i=$(((i + 1) % 4))
        printf "\r %s" "${spin:$i:1}"
        sleep .1
      done
      if kubectl get pods -l app.kubernetes.io/name=postgresql -n $backup_namespace -o jsonpath="{.items[*].status.conditions[*].status}" | grep -q False; then
        echo "Postgresql Application taking more time than usual to be in Ready state, Exiting.."
        return 1
      fi
    fi
    echo "Requested application is Up and Running!"

    yq eval -i 'del(.spec.backupPlanComponents)' backupplan.yaml 1>> >(logit) 2>> >(logit)
    yq eval -i '.spec.backupPlanComponents.helmReleases[0]="postgresql"' backupplan.yaml 1>> >(logit) 2>> >(logit)
    ;;
  *)
    echo "Wrong choice"
    ;;
  esac
  #check if backupplan with same name already exists
  if [[ $(kubectl get backupplan $bk_plan_name -n $backup_namespace 2>/dev/null) ]]; then
    echo "Backupplan with same name already exists"
    if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
      exit 1
    fi
    #echo "Waiting for Backupplan to be in Available state"
  else
    #Applying backupplan manifest
    {
      yq eval -i '.metadata.name="'$bk_plan_name'"' backupplan.yaml
      yq eval -i '.metadata.namespace="'$backup_namespace'"' backupplan.yaml
      yq eval -i '.spec.backupNamespace="'$backup_namespace'"' backupplan.yaml
      yq eval -i '.spec.backupConfig.target.name="'"$target_name"'"' backupplan.yaml
      yq eval -i '.spec.backupConfig.target.namespace="'"$target_namespace"'"' backupplan.yaml
    } 1>> >(logit) 2>> >(logit)
    echo "Creating backupplan..."
    cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Policy
metadata:
  name: sample-policy
spec:
  type: Retention
  default: false
  retentionConfig:
    latest: 30
    weekly: 7
    monthly: 30
EOF
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Erro while applying policy"
      return 1
    fi
    if ! kubectl apply -f backupplan.yaml -n $backup_namespace; then
      echo "Backupplan creation failed"
      return 1
    fi
  fi
  echo "Waiting for backupplan to be Available to use.."
  cmd="kubectl get backupplan $bk_plan_name -n $backup_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -e Available -e Unavailable"
  wait_install 10 "$cmd"
  if ! kubectl get backupplan $bk_plan_name -n $backup_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -q Available; then
    echo "Backupplan is in Unavailable state"
    return 1
  else
    echo "Backupplan is in Available state"
  fi
  rm -f backupplan.yaml
  if [[ $(kubectl get backup $backup_name -n $backup_namespace 2>> >(logit)) ]]; then
    echo "Backup with same name already exists"
    if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
      exit 1
    fi
    #echo "Waiting for Backup to be in Available state"
  else
    echo "Creating Backup..."
    #Applying backup manifest
    cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Backup
metadata:
  name: ${backup_name}
  namespace: ${backup_namespace}
spec:
  type: Full
  backupPlan:
    name: ${bk_plan_name}
    namespace: ${backup_namespace}
EOF
    retcode=$?
    if [ "$retcode" -ne 0 ]; then
      echo "Error while creating backup"
      return 1
    fi
  fi
  echo "Waiting for backup to be available.."
  cmd="kubectl get backup $backup_name -n $backup_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -e Available -e Failed"
  wait_install 60 "$cmd"
  if ! kubectl get backup $backup_name -n $backup_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -wq Available; then
    echo "Backup Failed"
    return 1
  else
    echo "Backup is Available Now"
  fi
  if [[ -z ${input_config} ]]; then
    read -r -p "whether restore test should also be done? y/n: " restore
  fi
  if [[ ${restore} == "Y" ]] || [[ ${restore} == "y" ]] || [[ ${restore} == "True" ]]; then
    if [[ -z ${input_config} ]]; then
      read -r -p "Restore Namepsace (default - trilio-$app-restore): " restore_namespace
      read -r -p "Restore name (default - trilio-$app-restore): " restore_name
    fi
    if [[ -z "$restore_namespace" ]]; then
      restore_namespace="trilio-$app-restore"
    fi
    if ! kubectl get ns "$restore_namespace" 1>> >(logit) 2>> >(logit); then
      echo "Namespace with name $restore_namespace already Exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      if ! kubectl create ns "$restore_namespace" 1>> >(logit) 2>> >(logit); then
        echo "Error while creating $restore_namespace namespace"
        return 1
      fi
    fi
    if [[ -z "$restore_name" ]]; then
      restore_name="trilio-$app-restore"
    fi
    if [[ $(kubectl get restore $restore_name -n $restore_namespace 2>/dev/null) ]]; then
      echo "Restore with same name already exists"
      if [[ "$if_resource_exists_still_proceed" != "Y" ]] && [[ "$if_resource_exists_still_proceed" != "y" ]]; then
        exit 1
      fi
      echo "Waiting for Restore to be in Available state"
    else
      echo "Creating restore..."
      #Applying restore manifest
      if [[ "$app" == "transformation-postgresql" ]]; then
        default_storage=$(kubectl get storageclass -o=jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}')
        kubectl get storageclass "$default_storage" -o yaml >storageclass_trans.yaml
        yq eval -i '.metadata.name="trans-storageclass"' storageclass_trans.yaml 1>> >(logit) 2>> >(logit)
        echo "Creating new storageclass 'trans-storageclass' for this example.."
        kubectl apply -f storageclass_trans.yaml
        retcode=$?
        if [ "$retcode" -ne 0 ]; then
          echo "Error while creating clone of default storageclass"
          return 1
        fi
        #echo "Removing 'default' label from $default_storage storageclass"
        #kubectl patch storageclass $default_storage -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}' 2>> >(logit)
        cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Restore
metadata:
  name: ${restore_name}
  namespace: ${restore_namespace}
spec:
  source:
    type: Backup
    backup:
      namespace: ${backup_namespace}
      name: ${backup_name}
    target:
      name: ${target_name}
      namespace: ${target_namespace}
  restoreNamespace: ${restore_namespace}
  transformComponents:
    helm:
      - release: postgresql
        transformName: t1
        set:
         - key: global.storageClass
           value: "trans-storageclass"
  skipIfAlreadyExists: true
EOF

      else
        cat <<EOF | kubectl apply -f - 1>> >(logit)
apiVersion: triliovault.trilio.io/v1
kind: Restore
metadata:
  name: ${restore_name}
  namespace: ${restore_namespace}
spec:
  source:
    type: Backup
    backup:
      namespace: ${backup_namespace}
      name: ${backup_name}
    target:
      name: ${target_name}
      namespace: ${target_namespace}
  restoreNamespace: ${restore_namespace}
  skipIfAlreadyExists: true
EOF
      fi
      retcode=$?
      if [ "$retcode" -ne 0 ]; then
        echo "Error while restoring"
        return 1
      fi
    fi
    echo "Waiting for restore to complete.."
    cmd="kubectl get restore $restore_name -n $restore_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -e Completed -e Failed"
    wait_install 60 "$cmd"
    if ! kubectl get restore $restore_name -n $restore_namespace -o 'jsonpath={.status.status}' 2>/dev/null | grep -wq 'Completed'; then
      echo "Restore Failed"
      echo "It may because of some resource already exits, please check and try again!"
      return 1
    else
      echo "Restore is Completed"
    fi
    if [ "$open_flag" -eq 1 ]; then
      kubectl get sa -n $restore_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-scc-to-user anyuid -z '{}' -n $restore_namespace 1>> >(logit) 2>> >(logit)
      kubectl get sa -n $restore_namespace | sed -n '1!p' | awk '{print $1, $8}' | sed 's/ //g' | xargs -I '{}' oc adm policy add-cluster-role-to-user cluster-admin -z '{}' -n $restore_namespace 1>> >(logit) 2>> >(logit)
    fi
    if [[ $backup_way == "Operator_based" ]]; then
      kubectl apply -f https://raw.githubusercontent.com/bitpoke/mysql-operator/master/examples/example-cluster-secret.yaml -n $restore_namespace
    fi
  fi
}

print_usage() {
  echo "
--------------------------------------------------------------
tvk-quickstart - Installs, Configures UI, Creates sample backup/restore tests
Usage:
kubectl tvk-quickstart [options] [arguments]
Options:
        -h, --help                Shows brief help
        -n, --noninteractive      Runs script in non-interactive mode.for this you need to provide config file
        -i, --install-tvk         Installs TVK and it's free trial license.
        -c, --configure-ui        Configures TVK UI
        -t, --target              Created Target for backup and restore jobs
        -s, --sample-test         Create sample backup and restore jobs
	-p, --preflight           Checks if all the pre-requisites are satisfied
	-v, --verbose             Runs the plugin in verbose mode
	-u, --uninstall-tvk       Uninstalls TVK and related resources.         
-----------------------------------------------------------------------
Example:
kubectl tvk-quickstart -i -c -t -s
kubectl tvk-quickstart -n /tmp/input_config
kubectl tvk-quickstart -u
"
}

main() {
  export input_config=""
  for i in "$@"; do
    #key="$1"
    case $i in
    -h | --help)
      print_usage
      exit 0
      ;;
    -n | --noninteractive)
      export Non_interact=True
      if [[ -z $2 ]]; then
        echo "filename argument required"
        print_usage
        exit 1
      fi
      export input_config=$2
      echo "tvk-quickstart will run in non-inetractive way"
      echo "Other options provided will be ignored"
      echo
      break
      ;;
    -i | --install-tvk)
      export TVK_INSTALL=True
      #echo "Flag set to install TVK product"
      shift
      echo
      ;;
    -c | --configure-ui)
      export CONFIGURE_UI=True
      #echo "flag set to configure ui"
      shift
      echo
      ;;
    -t | --target)
      export TARGET=True
      #echo "flag set to create backup target"
      shift
      echo
      ;;
    -u | --uninstall-tvk)
      export UNINSTALL=True
      shift
      echo
      ;;
    -s | --sample-test)
      export SAMPLE_TEST=True
      shift
      #echo "flag set to test sample  backup and restore of application "
      echo
      ;;
    -p | --preflight)
      shift
      export PREFLIGHT=True
      echo
      ;;
    -v | --verbose)
      set -x
      echo
      ;;
    *)
      echo "Incorrect option, check usage below..."
      echo
      print_usage
      exit 1
      ;;
    esac
    shift
  done
  if [ ${Non_interact} ]; then
    if [ ! -f "$input_config" ]; then
      echo "$input_config file not found!"
      exit 1
    fi
    # shellcheck source=/dev/null
    # shellcheck disable=SC2086
    . $input_config
    export input_config=$input_config
  fi
  if [[ ${PREFLIGHT} == 'True' ]]; then
    preflight_checks
  fi
  if [[ ${TVK_INSTALL} == 'True' ]]; then
    install_tvk
  fi
  if [[ ${CONFIGURE_UI} == 'True' ]]; then
    configure_ui
  fi
  if [[ ${TARGET} == 'True' ]]; then
    create_target
  fi
  if [[ ${SAMPLE_TEST} == 'True' ]]; then
    sample_test
  fi
  if [[ ${UNINSTALL} == 'True' ]]; then
    tvk_uninstall
  fi
}

logit() {
  # shellcheck disable=SC2162
  while read; do
    time=$(python3 -c "import datetime;e = datetime.datetime.now();print(\"%s\" % e)")
    echo "$time $REPLY" >>"${LOG_FILE}"
  done
}

LOG_FILE="/tmp/tvk_quickstart_stderr"

ret=$(python3 --version 2>/dev/null)
if [[ -z $ret ]]; then
  echo "Plugin requires python3 installed"
  echo "Please install and check"
  return 1
fi
ret=$(pip3 --version 2>> >(logit))
ret_code=$?
if [ "$ret_code" -ne 0 ]; then
  echo "This plugin requires pip3 to be installed.Please follow README"
  exit 1
fi
ret=$(pip3 install packaging 1>> >(logit) 2>> >(logit))
ret_code=$?
if [ "$ret_code" -ne 0 ]; then
  echo "pip3 install is failing.Please check the permisson and try again.."
  exit 1
fi
main "$@"
