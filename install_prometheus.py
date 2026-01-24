#!/usr/bin/env python3
import subprocess
import os
import sys
import tarfile
import shutil

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

    version = "3.0.1"
    arch = "linux-amd64"
    prom_dir = f"prometheus-{version}.{arch}"
    tar_file = f"{prom_dir}.tar.gz"
    url = f"https://github.com/prometheus/prometheus/releases/download/v{version}/{tar_file}"

    print(f"--- Installing Prometheus v{version} ---")

    # 1. Create User and Directories
    run_command("id -u prometheus >/dev/null 2>&1 || useradd --no-create-home --shell /bin/false prometheus", shell=True)
    os.makedirs("/etc/prometheus", exist_ok=True)
    os.makedirs("/var/lib/prometheus", exist_ok=True)

    # 2. Download and Extract
    if not os.path.exists(tar_file):
        print(f"Downloading Prometheus v{version}...")
        run_command(["wget", url])
    
    with tarfile.open(tar_file, "r:gz") as tar:
        tar.extractall()

    # 3. Copy Binaries and Assets
    shutil.copy2(f"{prom_dir}/prometheus", "/usr/local/bin/")
    shutil.copy2(f"{prom_dir}/promtool", "/usr/local/bin/")
    
    if os.path.exists(f"{prom_dir}/consoles"):
        shutil.copytree(f"{prom_dir}/consoles", "/etc/prometheus/consoles", dirs_exist_ok=True)
    if os.path.exists(f"{prom_dir}/console_libraries"):
        shutil.copytree(f"{prom_dir}/console_libraries", "/etc/prometheus/console_libraries", dirs_exist_ok=True)

    # 4. Create Initial Config
    config_content = """global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
"""
    config_path = "/etc/prometheus/prometheus.yml"
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            f.write(config_content)

    # 5. Set Permissions
    run_command("chown -R prometheus:prometheus /etc/prometheus", shell=True)
    run_command("chown -R prometheus:prometheus /var/lib/prometheus", shell=True)
    run_command("chown prometheus:prometheus /usr/local/bin/prometheus", shell=True)
    run_command("chown prometheus:prometheus /usr/local/bin/promtool", shell=True)

    # 6. Create systemd service
    service_content = """[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \\
    --config.file /etc/prometheus/prometheus.yml \\
    --storage.tsdb.path /var/lib/prometheus/ \\
    --web.console.templates=/etc/prometheus/consoles \\
    --web.console.libraries=/etc/prometheus/console_libraries

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/prometheus.service", "w") as f:
        f.write(service_content)

    # 7. Start Service
    run_command(["systemctl", "daemon-reload"])
    run_command(["systemctl", "enable", "prometheus"])
    run_command(["systemctl", "start", "prometheus"])

    # Cleanup
    if os.path.exists(prom_dir):
        shutil.rmtree(prom_dir)
    if os.path.exists(tar_file):
        os.remove(tar_file)

    print("\n--- Prometheus Installation Complete ---")
    print("Web UI: http://<machine-ip>:9090")

if __name__ == "__main__":
    main()
