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
    temp_clone = "/tmp/oxidized_recovery"

    print("--- Starting Oxidized Disaster Recovery ---")

    # 1. Get GitHub URL
    github_url = ""
    if len(sys.argv) > 1:
        github_url = sys.argv[1].strip()

    if not github_url:
        try:
            github_url = input("Enter your Private GitHub SSH URL (e.g. git@github.com:user/repo.git): ").strip()
        except EOFError:
            print("Error: GitHub URL is required for recovery.")
            sys.exit(1)

    if not github_url:
        print("GitHub URL is required for recovery.")
        sys.exit(1)

    # Auto-format URL if it's missing the SSH prefix
    if "github.com/" in github_url and "git@" not in github_url:
        repo_path = github_url.split("github.com/")[-1].replace(".git", "")
        github_url = f"git@github.com:{repo_path}.git"
        print(f"Auto-formatted URL to: {github_url}")

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

    # 5. Run Installation Script to finalized system dependencies and service
    print("Finalizing environment (Running installation script)...")
    install_script = os.path.join(home_dir, "install_oxidized.py")
    if os.path.exists(install_script):
        # Pass URL as argument to avoid EOFError
        run_command(f"sudo python3 {install_script} '{github_url}'", shell=True)

    # 6. --- RESTORE GIT DATA AFTER INSTALLATION ---
    # This ensures that our restored data is not overwritten by the installation script's defaults

    # Setup files -> Main folders
    print("Applying Git configurations over installation defaults...")
    setup_dir = os.path.join(temp_clone, "setup")
    if os.path.exists(setup_dir):
        # Ensure directory exists before copy
        os.makedirs(config_path, exist_ok=True)
        shutil.copy2(os.path.join(setup_dir, "config"), os.path.join(config_path, "config"))
        shutil.copy2(os.path.join(setup_dir, "router.db"), os.path.join(config_path, "router.db"))

        model_src = os.path.join(setup_dir, "model")
        if os.path.exists(model_src):
            os.makedirs(os.path.join(config_path, "model"), exist_ok=True)
            for model_file in os.listdir(model_src):
                shutil.copy2(os.path.join(model_src, model_file), os.path.join(config_path, "model", model_file))

        # Protect our own scripts
        shutil.copy2(os.path.join(setup_dir, "install_oxidized.py"), os.path.join(home_dir, "install_oxidized.py"))
        shutil.copy2(os.path.join(setup_dir, "restore_oxidized.py"), os.path.join(home_dir, "restore_oxidized.py"))

    # Backups -> configs/
    print("Restoring hardware backup history...")
    backup_src = os.path.join(temp_clone, "equipamentos_configuracao")
    configs_dir = os.path.join(config_path, "configs")
    if os.path.exists(backup_src):
        os.makedirs(configs_dir, exist_ok=True)
        # Re-initialize git if needed
        if not os.path.exists(os.path.join(configs_dir, ".git")):
            run_command(f"sudo -u {user} git -C {configs_dir} init", shell=True)
            run_command(f"sudo -u {user} git -C {configs_dir} config user.name 'Oxidized'", shell=True)
            run_command(f"sudo -u {user} git -C {configs_dir} config user.email 'oxidized@backup.local'", shell=True)

        for bkp in os.listdir(backup_src):
            shutil.copy2(os.path.join(backup_src, bkp), os.path.join(configs_dir, bkp))

        # Commit to ensure version tab is populated
        run_command(f"sudo -u {user} git -C {configs_dir} add .", shell=True)
        try:
            run_command(f"sudo -u {user} git -C {configs_dir} commit -m 'Restored from Git' --allow-empty", shell=True)
        except: pass

    # Correct permissions and restart service
    print("Finalizing permissions and restarting service...")
    run_command(f"chown -R {user}:{user} {config_path}", shell=True)
    run_command("sudo systemctl restart oxidized", shell=True)

    print("\n--- RECOVERY COMPLETE ---")
    print("The system has been restored with all configurations and backups.")
    print("Oxidized service should be running. Check with: sudo systemctl status oxidized")

if __name__ == "__main__":
    main()
