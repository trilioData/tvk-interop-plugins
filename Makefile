BUILD_DIR ?= build
DIST_DIR ?= dist

clean:
	rm -rf $(DIST_DIR) $(BUILD_DIR)

clean-build:
	rm -rf $(BUILD_DIR)

fmt:
	go fmt ./...

vet:
	go vet ./...

yaml-lint:
	yamllint -c .yamllint ./

shell-lint:
	./hack/run-shell-lint.sh

lint: yaml-lint shell-lint 

install-required-utilities:
	./hack/install-required-utilities.sh

install: install-required-utilities
	sudo apt-get install curl yamllint
	curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $(go env GOPATH)/bin v1.30.0
	curl -sfL https://install.goreleaser.com/github.com/goreleaser/goreleaser.sh | sh

build-tvk-quickstart:
	./hack/build-tvk-quickstart-artifacts.sh

build: build_test_tvk_quickstart
	goreleaser release --snapshot --skip-publish --rm-dist

test-tvk-quickstart-plugin-locally:
	./hack/generate-test-tvk-quickstart-plugin-manifest.sh
	./hack/test-tvk-quickstart-plugin-locally.sh

test-tvk_quickstart-integration:
	./tests/tvk-quickstart/install-required-utilities.sh
	./tests/tvk-quickstart/tvk_quickstart_test.sh


build-rke_etcd_backup_restore:
	./hack/build-rke-etcd-backup-restore-artifacts.sh

test-rke-etcd-backup-restore-locally:
	./hack/generate-rke-etcd-backup-restore-manifest.sh
	./hack/test-rke-etcd-backup-restore-plugin-locally.sh

build-ocp_etcd_backup_restore:
	./hack/build-ocp-etcd-backup-restore-artifacts.sh

test-ocp-etcd-backup-restore-locally:
	./hack/generate-ocp-etcd-backup-restore-manifest.sh
	./hack/test-ocp-etcd-backup-restore-plugin-locally.sh

build-checksum-rke_etcd_backup_restore:
	./hack/build-checksum-rke-etcd-backup-restore-artifacts.sh  

build-checksum-ocp_etcd_backup_restore:
	./hack/build-checksum-ocp-etcd-backup-restore-artifacts.sh

test: test-tvk_quickstart-integration


test-tvk-quickstart: clean build-tvk-quickstart test-tvk_quickstart-integration test-tvk-quickstart-plugin-locally

test-plugins-locally: test-tvk-quickstart-plugin-locally

test-plugins-packages: test-tvk-quickstart

validate-plugin-manifests:
	./hack/validate-plugin-manifests.sh

verify-code-patterns:
	./hack/verify-code-patterns.sh

update-tvk-quickstart-manifests:
	./hack/update-tvk-quickstart-manifests.sh

update-plugin-manifests: update-tvk-quickstart-manifests

ready: fmt vet lint verify-code-patterns

.PHONY: clean fmt vet go-lint shell-lint go-lint-fix yaml-lint go-test test coverage build run-log-collector
