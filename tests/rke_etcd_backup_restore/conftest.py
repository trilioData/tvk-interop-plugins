import pytest


def pytest_addoption(parser):
    parser.addoption("--rancher-url", action="store",
                     required=True, help="Rancher server URL")
    parser.addoption("--bearer-token", action="store",
                     required=True, help="Bearer token to access server")
    parser.addoption("--cluster-name", action="store",
                     required=True, help="Cluster name to take backup of")
    parser.addoption("--target-namespace", action="store", required=True,
                     help="Namespace name in which TVk target resides")
    parser.addoption("--target-name", action="store", required=True,
                     help="TVK target name")
    parser.addoption("--target-secretkey", action="store", required=True,
                     help="TVK target secretkey")


@pytest.fixture
def config_param(request):
    param = {}
    param["rancher-url"] = request.config.getoption("--rancher-url")
    param["bearer-token"] = request.config.getoption("--bearer-token")
    param["cluster-name"] = request.config.getoption("--cluster-name")
    param["target-namespace"] = request.config.getoption(
        "--target-namespace")
    param["target-name"] = request.config.getoption("--target-name")
    param["target-secretkey"] = request.config.getoption("--target-secretkey")
    return param


