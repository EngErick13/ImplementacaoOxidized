#!/usr/bin/env python3
import subprocess
import os
import sys

def run_command(command, shell=False):
    print(f"Executing: {command}")
    try:
        subprocess.run(command, check=True, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        sys.exit(1)

def main():
    if os.getuid() != 0:
        print("This script must be run with sudo.")
        sys.exit(1)

    print("--- Installing Grafana Enterprise ---")

    # 1. Install prerequisites
    run_command(["apt-get", "update"])
    run_command(["apt-get", "install", "-y", "apt-transport-https", "software-properties-common", "wget"])

    # 2. Add GPG Key
    run_command("mkdir -p /etc/apt/keyrings", shell=True)
    run_command("wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | tee /etc/apt/keyrings/grafana.gpg > /dev/null", shell=True)

    # 3. Add APT Repository
    repo_line = 'echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list'
    run_command(repo_line, shell=True)

    # 4. Install Grafana
    run_command(["apt-get", "update"])
    run_command(["apt-get", "install", "-y", "grafana-enterprise"])

    # 5. Enable and Start Service
    run_command(["systemctl", "daemon-reload"])
    run_command(["systemctl", "enable", "grafana-server"])
    run_command(["systemctl", "start", "grafana-server"])

    print("\n--- Grafana Installation Complete ---")
    print("Web UI: http://<machine-ip>:3000")
    print("Default Login: admin / admin")

if __name__ == "__main__":
    main()
