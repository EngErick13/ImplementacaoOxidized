#!/usr/bin/env python3
import subprocess
import os
import sys
import getpass

def run_command(command, shell=False):
    print(f"Executing: {command}")
    try:
        subprocess.run(command, check=True, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        sys.exit(1)

def main():
    candidate_user = os.getenv("SUDO_USER")
    if not candidate_user or candidate_user == "root":
        # Try to find the first non-root user with a home directory
        homes = [d for d in os.listdir('/home') if os.path.isdir(os.path.join('/home', d)) and d != 'lost+found']
        if homes:
            user = homes[0]
            print(f"Detected target user from /home: {user}")
        else:
            user = "root"
            print("No non-root user found in /home. Using root.")
    else:
        user = candidate_user
        print(f"Detected target user from SUDO_USER: {user}")

    home_dir = os.path.expanduser(f"~{user}")
    config_path = os.path.join(home_dir, ".config", "oxidized")

    print("--- Starting Decoupled Oxidized Installation ---")

    # 1. Install Dependencies
    run_command(["apt-get", "update"])
    dependencies = [
        "ruby", "ruby-dev", "make", "gcc", "g++", "cmake", "libcurl4-openssl-dev",
        "libssl-dev", "pkg-config", "libicu-dev", "libsqlite3-dev", "libyaml-dev",
        "zlib1g-dev", "git"
    ]
    run_command(["apt-get", "install", "-y"] + dependencies)

    # 2. Install gems
    run_command(["gem", "install", "oxidized", "oxidized-web", "rugged"])

    # 3. Setup directories
    configs_dir = os.path.join(config_path, "configs")
    os.makedirs(configs_dir, exist_ok=True)
    os.makedirs(os.path.join(config_path, "model"), exist_ok=True)

    # Change ownership BEFORE git init
    run_command(f"chown -R {user}:{user} {config_path}", shell=True)

    # Initialize configs as a non-bare repo so hook can see files
    if not os.path.exists(os.path.join(configs_dir, ".git")):
        run_command(f"sudo -u {user} git init {configs_dir}", shell=True)
        run_command(f"sudo -u {user} git -C {configs_dir} config user.name 'Oxidized'", shell=True)
        run_command(f"sudo -u {user} git -C {configs_dir} config user.email 'oxidized@backup.local'", shell=True)

    # 4. GitHub Setup
    github_url = ""
    if len(sys.argv) > 1:
        github_url = sys.argv[1].strip()

    if not github_url:
        try:
            github_url = input("Enter your Private GitHub SSH URL (e.g. git@github.com:user/repo.git) or leave empty: ").strip()
        except EOFError:
            github_url = ""
        if "github.com/" in github_url and "git@" not in github_url:
            repo_path = github_url.split("github.com/")[-1].replace(".git", "")
            github_url = f"git@github.com:{repo_path}.git"
            print(f"Auto-formatted URL to: {github_url}")

        ssh_dir = os.path.join(home_dir, ".ssh")
        key_file = os.path.join(ssh_dir, "id_ed25519_github")

        if not os.path.exists(key_file):
            print("Generating SSH key for GitHub...")
            run_command(f"sudo -u {user} ssh-keygen -t ed25519 -f {key_file} -N '' -C 'oxidized@bkp'", shell=True)
            print("\nIMPORTANT: Add this public key to your GitHub repository/settings:")
            with open(key_file + ".pub", "r") as f:
                print(f.read())
            try:
                input("Press Enter AFTER you have added the key to GitHub...")
            except EOFError:
                print("Non-interactive mode: skipping wait for key confirmation.")

        # SSH Config
        ssh_config = os.path.join(ssh_dir, "config")
        config_entry = f"\nHost github.com\n  HostName github.com\n  User git\n  IdentityFile {key_file}\n  StrictHostKeyChecking no\n"

        exists = False
        if os.path.exists(ssh_config):
            with open(ssh_config, "r") as f:
                if "IdentityFile " + key_file in f.read():
                    exists = True

        if not exists:
            with open(ssh_config, "a") as f:
                f.write(config_entry)
            run_command(f"chmod 600 {ssh_config}", shell=True)
            run_command(f"chown {user}:{user} {ssh_config}", shell=True)

    # 5. Initialize Sync Repo (GitHub only structure)
    sync_repo = os.path.join(config_path, "repo_sync")
    if not os.path.exists(os.path.join(sync_repo, ".git")):
        os.makedirs(sync_repo, exist_ok=True)
        run_command(f"chown -R {user}:{user} {sync_repo}", shell=True)
        run_command(f"sudo -u {user} git -C {sync_repo} init", shell=True)

    if github_url:
        run_command(f"sudo -u {user} git -C {sync_repo} remote add origin {github_url} || sudo -u {user} git -C {sync_repo} remote set-url origin {github_url}", shell=True)

    # 6. Create Oxidized Config with Decoupled Hook
    hook_cmd = (
        f'git -C {config_path}/configs/ checkout master . 2>/dev/null; '
        f'REPO_DIR="{config_path}/repo_sync"; '
        'mkdir -p $REPO_DIR/equipamentos_configuracao $REPO_DIR/setup/model; '
        f'find {config_path}/configs/ -maxdepth 1 -type f -exec cp {{}} $REPO_DIR/equipamentos_configuracao/ \\;; '
        f'cp {config_path}/config $REPO_DIR/setup/config; '
        f'cp {config_path}/router.db $REPO_DIR/setup/router.db; '
        f'cp {config_path}/model/vrp.rb $REPO_DIR/setup/model/vrp.rb; '
        f'cp {home_dir}/install_oxidized.py $REPO_DIR/setup/install_oxidized.py; '
        f'cp {home_dir}/restore_oxidized.py $REPO_DIR/setup/restore_oxidized.py; '
        f'[ -f {config_path}/last_failures.log ] && cp {config_path}/last_failures.log $REPO_DIR/setup/last_failures.log; '
        'git -C $REPO_DIR config user.name "Oxidized"; '
        'git -C $REPO_DIR config user.email "oxidized@backup.local"; '
        'git -C $REPO_DIR add .; '
        'git -C $REPO_DIR commit -m "Auto-sync: Project State and Configs" --allow-empty; '
        'git -C $REPO_DIR push origin master --force'
    )

    oxidized_config = f"""---
resolve_dns: true
interval: 3600
use_max_threads: false
threads: 30
timeout: 20
retries: 3
prompt: !ruby/regexp /^([\\w.@-]+[#>][\\s]?)$/
pid: "{config_path}/pid"
rest: 0.0.0.0:8888
extensions:
  oxidized-web:
    load: true
hooks:
  error_report:
    type: exec
    events: [node_fail]
    cmd: 'echo "$(date "+%Y-%m-%d %H:%M:%S") | Node: ${{OX_NODE_NAME}} | Status: ${{OX_JOB_STATUS}} | Type: ${{OX_ERR_TYPE}} | Reason: ${{OX_ERR_REASON}}" >> {config_path}/last_failures.log'
    async: true
  full_project_sync:
    type: exec
    events: [post_store]
    cmd: '{hook_cmd}'
    async: true
input:
  default: ssh, telnet
  debug: false
  ssh:
    secure: false
output:
  default: git
  git:
    user: Oxidized
    email: oxidized@bkp-01.local
    repo: "{config_path}/configs"
    # repo: "{config_path}/configs/.git"
source:
  default: csv
  csv:
    file: "{config_path}/router.db"
    delimiter: !ruby/regexp /:/
    map:
      name: 0
      ip: 1
      model: 2
      username: 3
      password: 4
    vars_map:
      ssh_port: 5
"""
    with open(os.path.join(config_path, "config"), "w") as f:
        f.write(oxidized_config)

    # 7. Create router.db (6 columns)
    router_db_file = os.path.join(config_path, "router.db")
    if not os.path.exists(router_db_file):
        with open(router_db_file, "w") as f:
            f.write("# name:ip:model:username:password:ssh_port\n")
            f.write("DUMMY_NODE:127.0.0.1:routeros:admin:admin:22\n")
            f.write("# PA-QBCS-ISR-01:1.1.1.1:routeros:admin:p@ss:22\n")

    # 8. Create custom VRP model
    vrp_custom_model = """class VRP < Oxidized::Model
  using Refinements
  prompt /^.*(<[\\w.-]+>)$/
  comment '# '
  expect /Change now\\? \\[Y\\/N\\]:/ do |data, re|
    send "n\\n"
    data.sub re, ''
  end
  cmd :secret do |cfg|
    cfg.gsub! /(pin verify (?:auto|)).*/, '\\\\1 <PIN hidden>'
    cfg.gsub! /(%\\^%#.*%\\^%#)/, '<secret hidden>'
    cfg
  end
  cmd :all do |cfg|
    cfg.cut_both
  end
  cfg :telnet do
    username /^Username:$/
    password /^Password:$/
  end
  cfg :telnet, :ssh do
    post_login 'screen-length 0 temporary'
    pre_logout 'quit'
  end
  cmd 'display version' do |cfg|
    cfg = cfg.each_line.reject do |l|
      l.match /uptime|^\\d\\d\\d\\d-\\d\\d-\\d\\d \\d\\d:\\d\\d:\\d\\d(\\.\\d\\d\\d)? ?(\\+\\d\\d:\\d\\d)?$/
    end.join
    comment cfg
  end
  cmd 'display device' do |cfg|
    cfg = cfg.each_line.reject { |l| l.match /^\\d\\d\\d\\d-\\d\\d-\\d\\d \\d\\d:\\d\\d:\\d\\d(\\.\\d\\d\\d)? ?(\\+\\d\\d:\\d\\d)?$/ }.join
    comment cfg
  end
  cmd 'display current-configuration all' do |cfg|
    cfg = cfg.each_line.reject { |l| l.match /^\\d\\d\\d\\d-\\d\\d-\\d\\d \\d\\d:\\d\\d:\\d\\d(\\.\\d\\d\\d)? ?(\\+\\d\\d:\\d\\d)?$/ }.join
    cfg
  end
end
"""
    with open(os.path.join(config_path, "model", "vrp.rb"), "w") as f:
        f.write(vrp_custom_model)

    run_command(f"chown -R {user}:{user} {config_path}", shell=True)

    # 9. Setup systemd service
    service_content = f"""[Unit]
Description=Oxidized - Network Configuration Backup
After=network.target

[Service]
User={user}
Environment="OXIDIZED_HOME={config_path}"
ExecStart=/usr/local/bin/oxidized
Restart=on-failure
RestartSec=30s

[Install]
WantedBy=multi-user.target
"""
    print(f"Writing systemd service for user {user}...")
    with open("/etc/systemd/system/oxidized.service", "w") as f:
        f.write(service_content)

    os.chmod("/etc/systemd/system/oxidized.service", 0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    run_command(["systemctl", "daemon-reload"])
    run_command(["systemctl", "enable", "oxidized"])

    # Cleanup possible root configuration that causes confusion
    if os.path.exists("/root/.config/oxidized"):
        print("Cleaning up erroneous root configuration...")
        run_command(["rm", "-rf", "/root/.config/oxidized"])

    run_command(["systemctl", "restart", "oxidized"])

    print("--- Installation and Decoupled Synchronization Configured ---")
    print(f"Web UI: http://<machine-ip>:8888")
    if github_url:
        print(f"GitHub: Organized repository with 'equipamentos_configuracao' and 'setup' folders.")

if __name__ == "__main__":
    main()
