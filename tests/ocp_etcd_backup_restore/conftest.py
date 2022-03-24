import pytest


def pytest_addoption(parser):
    parser.addoption("--server", action="store",
                     required=True, help="server URL")
    parser.addoption("--user", action="store",
                     required=True, help="User name to access cluster")
    parser.addoption("--passwd", action="store",
                     required=True, help="Passwd to access cluster")
    parser.addoption('--target-namespace', action="store",
                            help="Namespace name where the target resides.")
    parser.addoption('--target-name',
            action="store",
            help="The name of a single datastore on which etcd backup needs "
            "to be shared")
    parser.addoption('--p', action='store_true',
                       help="If users want to run only post restore tasks")
    parser.addoption('--log-location',
            action="store",
            help="Log file name along with path where the logs should be save"
            " default - /tmp/etcd-ocp-backup.log")


@pytest.fixture
def config_param(request):
    param = {}
    param["server"] = request.config.getoption("--server")
    param["user"] = request.config.getoption("--user")
    param["passwd"] = request.config.getoption("--passwd")
    param["target-name"] = request.config.getoption("--target-name")
    param["target-namespace"] = request.config.getoption("--target-namespace")
    param["post-restore"] = request.config.getoption("--p")
    return param


