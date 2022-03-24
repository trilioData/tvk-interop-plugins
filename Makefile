BUILD_DIR ?= build
DIST_DIR ?= dist

clean:
	go clean
	rm -rf $(DIST_DIR) $(BUILD_DIR)

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

build-tvk-oneclick:
	./hack/build-tvk-oneclick-artifacts.sh

build: build_test_tvk_oneclick
	goreleaser release --snapshot --skip-publish --rm-dist

test-tvk-oneclick-plugin-locally:
	./hack/generate-test-tvk-oneclick-plugin-manifest.sh
	./hack/test-tvk-oneclick-plugin-locally.sh

test-tvk_oneclick-integration:
	./tests/tvk-oneclick/install-required-utilities.sh
	./tests/tvk-oneclick/tvk_oneclick_test.sh


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

test: test-tvk_oneclick-integration


test-tvk-oneclick: clean build-tvk-oneclick test-tvk_oneclick-integration test-tvk-oneclick-plugin-locally

test-plugins-locally: test-tvk-oneclick-plugin-locally

test-plugins-packages: test-tvk-oneclick

validate-plugin-manifests:
	./hack/validate-plugin-manifests.sh

verify-code-patterns:
	./hack/verify-code-patterns.sh

update-tvk-oneclick-manifests:
	./hack/update-tvk-oneclick-manifests.sh

update-plugin-manifests: update-tvk-oneclick-manifests

ready: fmt vet lint verify-code-patterns

.PHONY: clean fmt vet go-lint shell-lint go-lint-fix yaml-lint go-test test coverage build run-log-collector
