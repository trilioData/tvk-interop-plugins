# Contribution Guidelines

This guide intends to make contribution to this repo easier and consistent.

## Directory Structure:

```text
tvk-plugins
 ├── .github/
 |    └── workflows : github actions workflow files
 |        ├── plugin-manifests.yml : CI workflow for plugin manifest validation
 |        └── plugin-packages.yml : CI workflow for plugin packages(build, test, release)
 ├── .krew : template yamls of plugin manifests(used for update of actual krew manifest and local testing)
 ├── docs : docs of tvk-plugins, contribution and release guidelines
 ├── hack : dir contains helper files for github actions CI workflows
 ├── internal : dir contains funcs to initialize kube-env clients and other helper funcs
 ├── LICENSE.md : License for tvk-plugins
 ├── Makefile : make targets
 ├── plugins : Krew plugin manifests
 │   └── tvk-oneclick.yaml
 ├── tests : Integration Test
 │   └── tvk-oneclick : oneclick test suite
 ├── tools : business logic of plugins
 │   ├── tvk-oneclick: business logic of tvk-oneclick
 ├── .goreleaser.yml : goreleaser conf file(to build & release plugin packages)   
```

## Setup Local Environment

### Pre-requisites:

Ensure following utilities are installed on the local machine:
1. goreleaser 
2. krew
3. kubectl
4. yamllint
5. golangci-lint
6. curl

If these are not installed then, install using `make install` or choose any other installation method to get the latest version. 

### Code Convention:

Run following commands before git push to remote:

```
make ready
```

### Build and Test:

#### Plugin Packages

2. **Tvk-oneclick**:
     
     Build: 
     ```
     make business logic of
     ```

     Test:
     ```
     make test-tvk_oneclick-integration
     ```   
    
     Build and Test together:
     ```
     make test-tvk-oneclick
     ```


3. **All Plugins  together**:

    Build:
    ```
    make build
    ```

    Test: 
    ```
    make test-plugins-locally
    ``` 

    Build and Test together:
    ```
    make test-plugins-packages
    ```
    

#### Plugin Manifests


1. **Update**:
    
    Update plugin manifests kept under [`plugins`](plugins) directory using template yamls from [`.krew`](.krew) directory.
    Need to set Versions to update plugin manifests.
    
    Set Versions:
    ```
    export TVK_ONECLICK_VERSION=<tvk-oneclick-release-tag>
    ```
   
    Tvk-oneclick:
    ```
    make update-tvk-oneclick-manifests
    ```
   
    All Preflight, Log-collector and Target-Browser together:
    ```
    make update-plugin-manifests
    ```

2. **Validate**:

    Validate updated plugin manifests kept under [`plugins`](plugins) directory.
    
    ```
    make validate-plugin-manifests
    ```

#### Run Integration Tests:
   
   ```
   make test
   ```

```
NOTE: Follow all mentioned code conventions and build & test plugins locally before git push.
```
