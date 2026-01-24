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
        return False
    return True

def main():
    if os.getuid() != 0:
        print("This script must be run with sudo.")
        sys.exit(1)

    version = "1.0.3"
    deb_file = f"oxidized-exporter_{version}_linux_amd64.deb"
    url = f"https://github.com/akquinet/oxidized-exporter/releases/download/v{version}/{deb_file}"

    print(f"--- Installing Oxidized Exporter v{version} ---")

    # 1. Download .deb
    if not os.path.exists(deb_file):
        print(f"Downloading Exporter v{version}...")
        run_command(["wget", url])

    # 2. Install package
    run_command(f"apt-get install -y ./{deb_file}", shell=True)

    # 3. Configure/Verify Service
    # The deb package usually creates a service, but let's ensure it knows where Oxidized is.
    # We will create/override the systemd service to ensure the correct flags.
    service_content = f"""[Unit]
Description=Oxidized Exporter for Prometheus
After=network.target oxidized.service

[Service]
Type=simple
ExecStart=/usr/bin/oxidized-exporter --url="http://127.0.0.1:8888"
Restart=always

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/oxidized-exporter.service", "w") as f:
        f.write(service_content)

    run_command(["systemctl", "daemon-reload"])
    run_command(["systemctl", "enable", "oxidized-exporter"])
    run_command(["systemctl", "start", "oxidized-exporter"])

    # 4. Integrate with Prometheus if available
    prom_config = "/etc/prometheus/prometheus.yml"
    if os.path.exists(prom_config):
        print("Integrating with local Prometheus...")
        with open(prom_config, "r") as f:
            content = f.read()
        
        if "job_name: 'oxidized'" not in content:
            scrape_job = """
  - job_name: 'oxidized'
    static_configs:
      - targets: ['localhost:8080']
"""
            with open(prom_config, "a") as f:
                f.write(scrape_job)
            run_command(["systemctl", "restart", "prometheus"])
            print("Prometheus configuration updated and service restarted.")
        else:
            print("Oxidized job already exists in Prometheus config.")

    # Cleanup
    if os.path.exists(deb_file):
        os.remove(deb_file)

    print("\n--- Oxidized Exporter Installation Complete ---")
    print("Metrics Endpoint: http://localhost:8080/metrics")

if __name__ == "__main__":
    main()
