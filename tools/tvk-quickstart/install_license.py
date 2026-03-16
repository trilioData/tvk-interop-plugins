import requests
import sys
import subprocess
import re
from bs4 import BeautifulSoup

def run_command(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(result.stdout)

def secret_exists(secret_name: str, namespace: str) -> bool:
    """Check if a Kubernetes secret exists in the given namespace."""
    try:
        subprocess.run(
            f"kubectl get secret {secret_name} -n {namespace}",
            shell=True, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def handle_option1(soup, namespace):
    # Find Option 1 header
    option1_header = soup.find("strong", string=re.compile("Option 1", re.IGNORECASE))
    if not option1_header:
        raise Exception("Option 1 header not found in POST response")

    option1_p = option1_header.find_parent("p")

    commands = []
    for sibling in option1_p.find_next_siblings():
        strong = sibling.find("strong")
        if strong and re.search("Option", strong.get_text(), re.IGNORECASE):
            break
        for block in sibling.find_all(["code", "pre"]):
            text = block.get_text().strip()
            if text.startswith("kubectl"):
                commands.append(text)

    if not commands:
        raise Exception("No kubectl commands found under Option 1")

    # Separate secret creation and apply
    secret_cmds = [c for c in commands if "create secret" in c]
    apply_cmds = [c for c in commands if "apply -f" in c]

    # Handle secret creation
    for cmd in secret_cmds:
        match = re.search(r"create secret \S+ (\S+)", cmd)
        secret_name = match.group(1) if match else None

        if secret_name and secret_exists(secret_name, namespace):
            print(f"Secret '{secret_name}' already exists in namespace '{namespace}'. Using existing secret.")
        else:
            if "-n" in cmd:
                cmd = re.sub(r"-n\s+\S+", f"-n {namespace}", cmd)
            else:
                cmd += f" -n {namespace}"
            run_command(cmd)

    # Handle apply command
    for cmd in apply_cmds:
        match = re.search(r"apply -f\s+(\S+)", cmd)
        if not match:
            continue
        target = match.group(1)

        filename = "license.yaml"

        if target == "-":
            # Inline YAML case
            print("Found inline YAML in Option 1 response")
            yaml_blocks = []
            for block in soup.find_all("pre"):
                text = block.get_text()
                if not text.startswith("kubectl") and "apiVersion" in text:
                    yaml_blocks.append(text.strip())
            if not yaml_blocks:
                raise Exception("No inline YAML found in response")
            with open(filename, "w") as f:
                f.write("\n---\n".join(yaml_blocks))
        else:
            # URL case
            print(f"Downloading license YAML from {target}")
            yaml_resp = requests.get(target)
            yaml_resp.raise_for_status()
            with open(filename, "w") as f:
                f.write(yaml_resp.text)

        # Apply with namespace
        apply_cmd = f"kubectl apply -f {filename} -n {namespace}"
        run_command(apply_cmd)

def handle_option3(soup, namespace):
    option3_header = soup.find("strong", string=re.compile("Option 3", re.IGNORECASE))
    if not option3_header:
        print("Option 3 not found in response")
        return

    option3_p = option3_header.find_parent("p")

    yaml_blocks = []
    # Look through all code/pre blocks after Option 3
    for sibling in option3_p.find_next_siblings():
        strong = sibling.find("strong")
        if strong and re.search("Option", strong.get_text(), re.IGNORECASE):
            break
        for block in sibling.find_all(["pre", "code"]):
            text = block.get_text().strip()
            if "EOF" in text:
                inside = []
                capture = False
                for line in text.splitlines():
                    if "<<EOF" in line or "<< EOF" in line:
                        capture = True
                        continue
                    if line.strip() == "EOF":
                        capture = False
                        break
                    if capture:
                        inside.append(line)
                if inside:
                    yaml_blocks.append("\n".join(inside))

    if not yaml_blocks:
        # Debug dump to see what we actually got
        print("DEBUG: No heredoc YAML found. Dumping blocks:")
        for block in option3_p.find_all(["pre", "code"]):
            print("BLOCK:\n", block.get_text())
        raise Exception("No YAML found under Option 3 (heredoc parsing failed)")

    filename = "license-trilio.yaml"
    with open(filename, "w") as f:
        f.write("\n---\n".join(yaml_blocks))

    print(f"Saved license manifest to {filename}")
    # Show preview
    with open(filename) as f:
        preview = "".join(f.readlines()[:10])

    # Apply with namespace
    apply_cmd = f"kubectl apply -f {filename} -n {namespace}"
    run_command(apply_cmd)


def install_license(namespace: str, license_url: str, format: str, headers=None, data=None):
    """Install license in either 'new' (Option 1) or 'old' (Option 3) format."""
    resp = requests.post(license_url, headers=headers, data=data)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    if format.lower() == "new":
        handle_option1(soup, namespace)
    elif format.lower() == "old":
        handle_option3(soup, namespace)
    else:
        raise ValueError("Invalid format. Use 'new' or 'old'.")

if __name__ == "__main__":
    LICENSE_URL = "https://license.trilio.io/8d92edd6-514d-4acd-90f6-694cb8d83336/0061K00000fwkma"

    HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        # Add cookies/auth headers if required
    }
    DATA = {}  # Add payload if DevTools shows one
    NAMESPACE = sys.argv[1]
    format = sys.argv[2]
    # Choose format: "new" for Option 1, "old" for Option 3
    install_license(NAMESPACE, LICENSE_URL, format, headers=HEADERS, data=DATA)
