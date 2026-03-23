#!/bin/bash
set -e

NAMESPACE=$1
VM_NAME=$2
VM_USER=$3
VM_PASSWORD=$4
DEPLOY=$5

KEY_PATH="$HOME/.ssh/${VM_NAME}_${NAMESPACE}"
LOGFILE=/tmp/vm_quickstart_logs

# Save original stdout to FD 3
exec 3>&1

# Redirect stdout and stderr to logfile
exec >"$LOGFILE" 2>&1

if [[ $DEPLOY == "True" ]]; then
  if [ -e "$KEY_PATH" ]; then
    echo "key $KEY_PATH already exists. Please remove it and then try.Exiting script." 
    exit 1
  fi

  echo "Generating SSH key pair..."
  ssh-keygen -t rsa -b 4096 -f "$KEY_PATH" -N ""
  # shellcheck disable=SC2155
  export PUB_KEY="$(cat "$KEY_PATH".pub)"


  echo "=========================================="
  echo "Deploying Fedora VM"
  echo "=========================================="

  cat <<EOF > vm.yaml
#cat <<YAML | oc apply -f -
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: ${VM_NAME}
  namespace: ${NAMESPACE}
  labels:
    os: fedora
spec:
  dataVolumeTemplates:
    - apiVersion: cdi.kubevirt.io/v1beta1
      kind: DataVolume
      metadata:
        creationTimestamp: null
        name: ${VM_NAME}
      spec:
        sourceRef:
          kind: DataSource
          name: fedora
          namespace: openshift-virtualization-os-images
        storage:
          resources:
            requests:
              storage: 30Gi
  runStrategy: RerunOnFailure
  template:
    metadata:
      annotations:
        vm.kubevirt.io/flavor: small
        vm.kubevirt.io/os: fedora
        vm.kubevirt.io/workload: server

      labels:
        kubevirt.io/domain: ${VM_NAME}
        kubevirt.io/size: small
        network.kubevirt.io/headlessService: headless
    spec:
      architecture: amd64
      domain:
        cpu:
          cores: 1
          sockets: 1
          threads: 1
        devices:
          disks:
            - disk:
                bus: virtio
              name: rootdisk
            - disk:
                bus: virtio
              name: cloudinitdisk
          interfaces:
            - masquerade: {}
              model: virtio
              name: default
          rng: {}
        features:
          acpi: {}
          smm:
            enabled: true
        firmware:
          bootloader:
            efi: {}
        machine:
          type: pc-q35-rhel9.4.0
        memory:
          guest: 2Gi
        resources: {}
      networks:
        - name: default
          pod: {}
      terminationGracePeriodSeconds: 180
      volumes:
        - dataVolume:
            name: ${VM_NAME}
          name: rootdisk
        - name: cloudinitdisk
          cloudInitNoCloud:
            userData: |
              #cloud-config
              hostname: ${VM_NAME}
              users:
                - name: ${VM_USER}
                  passwd: ${VM_PASSWORD}
                  lock_passwd: false
                  ssh-authorized-keys:
                    - ${PUB_KEY}
              chpasswd: { expire: False }
              ssh_pwauth: True
              packages: [qemu-guest-agent]
              runcmd:
                - [systemctl, enable, qemu-guest-agent]
                - [systemctl, start, qemu-guest-agent]

#YAML
EOF
  kubectl apply -f vm.yaml

  echo "✓ VM created"
  echo ""
  echo "Waiting for VM to be ready (2-3 minutes)..."


  # Duration in seconds (2 minutes = 120 seconds)
  DURATION=120

  # Spinner characters
  spin='-\|/'
  i=0

  end=$((SECONDS+DURATION))
  while [ $SECONDS -lt $end ]; do
    i=$(( (i+1) %4 ))
    # shellcheck disable=SC2059
    printf "\rWaiting...for VM pod to get created ${spin:$i:1}"
    sleep 1
  done

  # Simple: just wait 15 seconds for VMI to be created
  #echo "wait 8-10 min for VM to get created"
  #sleep 600

  # Now wait for it to be ready

  # Run oc wait in the background
  oc wait --for=condition=Ready vmi/"${VM_NAME}" -n "${NAMESPACE}" --timeout=600s &
  pid=$!

  # Spinner while waiting
  spin='-\|/'
  i=0
  while kill -0 $pid 2>/dev/null; do
    i=$(( (i+1) %4 ))
    # shellcheck disable=SC2059
    printf "\rWaiting for VM to be Ready... ${spin:$i:1}"
    sleep 1
  done

  wait $pid
  ret_val=$?
  if [[ $ret_val -ne 0 ]]; then
    echo "Vm creation Failed, please check logs at /tmp/vm_quickstart_logs" 
    exit 1
  fi
  echo ""
  echo "=========================================="
  echo "✓ Fedora VM Ready!"
  echo "=========================================="
  echo "VM Name:  ${VM_NAME}"
  echo "Username: ${VM_USER}"
  echo "Password: ${VM_PASSWORD}"
  echo ""
  echo "Access VM:"
  echo "  virtctl ssh -n ${NAMESPACE} ${VM_USER}@${VM_NAME}"
  echo ""


  # Create a 20MB random file on the VM
  DURATION=40

  # Spinner characters
  spin='-\|/'
  i=0

  end=$((SECONDS+DURATION))
  while [ $SECONDS -lt $end ]; do
    i=$(( (i+1) %4 ))
    # shellcheck disable=SC2059
    printf "\rWaiting...for VM pod to come up ${spin:$i:1}"
    sleep 1
  done
fi


echo "echo $VM_PASSWORD" > /tmp/askpass.sh
chmod +x /tmp/askpass.sh
# Set environment variables so ssh uses it
export SSH_ASKPASS=/tmp/askpass.sh
export DISPLAY=:0   # fake display to trigger askpass
export SSH_ASKPASS_REQUIRE=force


FILE_PATH="/home/${VM_USER}/file_test"
# shellcheck disable=SC2034
REMOTE_CMD="dd if=/dev/urandom of=${FILE_PATH} bs=1M count=20 && sha256sum ${FILE_PATH}"

file_exist=$(virtctl -n "${NAMESPACE}" ssh "${VM_USER}"@"${VM_NAME}" --local-ssh=true --local-ssh-opts="-o StrictHostKeyChecking=no" --local-ssh-opts="-o UserKnownHostsFile=/dev/null" --local-ssh-opts="-o LogLevel=ERROR" --identity-file="${KEY_PATH}" -c "[ -e ${FILE_PATH} ] && echo 0 || echo 1")

if [[ $file_exist -eq 1 ]]; then
  CHECKSUM=$(virtctl -n "${NAMESPACE}" ssh "${VM_USER}"@"${VM_NAME}" --local-ssh=true --local-ssh-opts="-o StrictHostKeyChecking=no" --local-ssh-opts="-o UserKnownHostsFile=/dev/null" --local-ssh-opts="-o LogLevel=ERROR" --identity-file="${KEY_PATH}" -c "dd if=/dev/urandom of=${FILE_PATH} bs=1M count=20 > /dev/null 2>&1 && sha256sum ${FILE_PATH}"  | awk '{print $1}')
else
  CHECKSUM=$(virtctl -n "${NAMESPACE}" ssh "${VM_USER}"@"${VM_NAME}" --local-ssh=true --local-ssh-opts="-o StrictHostKeyChecking=no" --local-ssh-opts="-o UserKnownHostsFile=/dev/null" --local-ssh-opts="-o LogLevel=ERROR" --identity-file="${KEY_PATH}" -c "sha256sum ${FILE_PATH}"  | awk '{print $1}')
fi
#CHECKSUM=$(virtctl ssh -i ${KEY_PATH} ${VM_USER}@${VM_NAME} -n ${NAMESPACE} "${REMOTE_CMD}" | awk '{print $1}')
#CHECKSUM=$(virtctl ssh -i ${KEY_PATH} -l ${VM_USER} ${VM_NAME}.${NAMESPACE} -c "dd if=/dev/urandom of=${FILE_PATH} bs=1M count=20 && sha256sum ${FILE_PATH}")

#echo "SHA256 checksum of ${FILE_PATH} on VM ${VM_NAME}: ${CHECKSUM}"
echo "$CHECKSUM" >&3
