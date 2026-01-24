#!/usr/bin/env python3
import subprocess
import os
import sys
import getpass
import shutil

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

    user = getpass.getuser()
    if user == "root":
        user = os.getenv("SUDO_USER", "erick")

    home_dir = os.path.expanduser(f"~{user}")
    config_path = os.path.join(home_dir, ".config", "oxidized")
    temp_clone = "/tmp/oxidized_recovery"

    print("--- Starting Oxidized Disaster Recovery ---")

    # 1. Get GitHub URL
    github_url = input("Enter your Private GitHub SSH URL (e.g. git@github.com:EngErick13/backup.devices.apd.universo.git): ").strip()
    if not github_url:
        print("GitHub URL is required for recovery.")
        sys.exit(1)

    # 2. Basic Dependencies for Recovery
    print("Installing basic recovery dependencies (git)...")
    run_command(["apt-get", "update"])
    run_command(["apt-get", "install", "-y", "git"])

    # 3. SSH Key Setup
    ssh_dir = os.path.join(home_dir, ".ssh")
    key_file = os.path.join(ssh_dir, "id_ed25519_github")

    if not os.path.exists(key_file):
        print("SSH key not found. Generating new key for GitHub access...")
        os.makedirs(ssh_dir, exist_ok=True)
        run_command(f"sudo -u {user} ssh-keygen -t ed25519 -f {key_file} -N '' -C 'oxidized@recovery'", shell=True)
        print("\nIMPORTANT: Add this public key to your GitHub repository/settings:")
        with open(key_file + ".pub", "r") as f:
            print(f.read())
        input("Press Enter AFTER you have added the key to GitHub to continue...")

    # Ensure SSH config is present
    ssh_config = os.path.join(ssh_dir, "config")
    ssh_entry = f"\nHost github.com\n  HostName github.com\n  User git\n  IdentityFile {key_file}\n  StrictHostKeyChecking no\n"

    exists = False
    if os.path.exists(ssh_config):
        with open(ssh_config, "r") as f:
            if "IdentityFile " + key_file in f.read():
                exists = True

    if not exists:
        with open(ssh_config, "a") as f:
            f.write(ssh_entry)
        run_command(f"chmod 600 {ssh_config}", shell=True)
        run_command(f"chown {user}:{user} {ssh_config}", shell=True)

    # 3. Clone Repository
    if os.path.exists(temp_clone):
        shutil.rmtree(temp_clone)

    print("Cloning repository...")
    if not run_command(f"sudo -u {user} git clone {github_url} {temp_clone}", shell=True):
        print("Failed to clone repository. Check your SSH key permissions on GitHub.")
        sys.exit(1)

    # Setup files -> Main folders
    os.makedirs(os.path.join(config_path, "configs"), exist_ok=True)
    run_command(f"sudo -u {user} git -C {os.path.join(config_path, 'configs')} init", shell=True)
    os.makedirs(os.path.join(config_path, "model"), exist_ok=True)
    os.makedirs(os.path.join(config_path, "repo_sync"), exist_ok=True)
    run_command(f"chown -R {user}:{user} {config_path}", shell=True)

    # Setup files -> Main folders
    setup_dir = os.path.join(temp_clone, "setup")
    if os.path.exists(setup_dir):
        shutil.copy(os.path.join(setup_dir, "config"), os.path.join(config_path, "config"))
        shutil.copy(os.path.join(setup_dir, "router.db"), os.path.join(config_path, "router.db"))

        model_src = os.path.join(setup_dir, "model")
        if os.path.exists(model_src):
            for model_file in os.listdir(model_src):
                shutil.copy(os.path.join(model_src, model_file), os.path.join(config_path, "model", model_file))

        # Save scripts back to home
        shutil.copy(os.path.join(setup_dir, "install_oxidized.py"), os.path.join(home_dir, "install_oxidized.py"))
        shutil.copy(os.path.join(setup_dir, "restore_oxidized.py"), os.path.join(home_dir, "restore_oxidized.py"))

        # Restore failure log if exists
        fail_log = os.path.join(setup_dir, "last_failures.log")
        if os.path.exists(fail_log):
            shutil.copy(fail_log, os.path.join(config_path, "last_failures.log"))

    # Backups -> configs/
    backup_src = os.path.join(temp_clone, "equipamentos_configuracao")
    if os.path.exists(backup_src):
        for bkp in os.listdir(backup_src):
            shutil.copy(os.path.join(backup_src, bkp), os.path.join(config_path, "configs", bkp))

    # Initialize sync repo correctly
    sync_repo = os.path.join(config_path, "repo_sync")
    if os.path.exists(os.path.join(sync_repo, ".git")):
        shutil.rmtree(os.path.join(sync_repo, ".git"))

    # We move the cloned git repo to be the sync_repo, but we need it to be clean
    # Actually, it's easier to just re-init and set remote in the right place
    run_command(f"sudo -u {user} git -C {sync_repo} init", shell=True)
    run_command(f"sudo -u {user} git -C {sync_repo} remote add origin {github_url}", shell=True)

    # Correct permissions
    run_command(f"chown -R {user}:{user} {config_path}", shell=True)

    # 5. Run Installation Script to finalize dependencies and service
    print("Finalizing environment (Running installation script)...")
    install_script = os.path.join(home_dir, "install_oxidized.py")
    if os.path.exists(install_script):
        # We run it non-interactively by providing the URL as input
        run_command(f"echo '{github_url}' | sudo python3 {install_script}", shell=True)

    print("\n--- RECOVERY COMPLETE ---")
    print("The system has been restored with all configurations and backups.")
    print("Oxidized service should be running. Check with: sudo systemctl status oxidized")

if __name__ == "__main__":
    main()
