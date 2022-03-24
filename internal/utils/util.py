import sys
import subprocess


def run(cmd):
    proc = subprocess.Popen(cmd, stderr=sys.stderr, stdout=sys.stdout, shell=True)
    proc.communicate()
    if proc.returncode:
        err_msg = "command :{}, exitcode :{}".format(cmd, proc.returncode)
        return 1
    else:
        return 0

        
