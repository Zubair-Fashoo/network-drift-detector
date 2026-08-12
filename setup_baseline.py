#!/usr/bin/env python3
"""
Setup Initial Baseline
Run this ONCE to create your known-good baseline
"""

import os
import yaml
import paramiko
import git
from pathlib import Path
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)


def setup_baseline():
    """Pull configs and save as initial known-good baseline"""
    
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════╗
{Fore.CYAN}║  {Fore.WHITE}Initial Baseline Setup{Fore.CYAN}               ║
{Fore.CYAN}║  {Fore.YELLOW}Creating known-good configuration{Fore.CYAN}   ║
{Fore.CYAN}╚══════════════════════════════════════╝
    """)
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Setup directories
    for d in ['configs', 'known_good', 'logs', 'reports']:
        Path(d).mkdir(exist_ok=True)
    
    # Get Git repo
    try:
        repo = git.Repo('.')
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init('.')
        print(f"{Fore.GREEN}✓ Git repository initialized")
    
    for device in config['devices']:
        device_name = device['name']
        
        print(f"\n{Fore.BLUE}Setting up baseline for: {device_name}")
        print(f"{Fore.BLUE}{'─'*40}")
        
        try:
            # Connect to device
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=device['host'],
                port=device['port'],
                username=device['username'],
                password=device['password'],
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            
            print(f"{Fore.GREEN}✓ Connected to {device['host']}")
            
            # Create baseline directory
            baseline_dir = Path('known_good') / device_name
            baseline_dir.mkdir(parents=True, exist_ok=True)
            
            # Pull each command output
            for cmd_config in device.get('commands', []):
                command = cmd_config['command']
                output_file = cmd_config['output_file']
                
                print(f"  Pulling: {output_file}...")
                
                stdin, stdout, stderr = client.exec_command(
                    command, timeout=30, get_pty=True
                )
                output = stdout.read().decode('utf-8', errors='replace')
                
                # Save as baseline
                content = (
                    f"# BASELINE - Device: {device_name}\n"
                    f"# Command: {command}\n"
                    f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"# This is the KNOWN GOOD configuration\n"
                    f"# {'='*50}\n\n"
                    f"{output.strip()}"
                )
                
                baseline_path = baseline_dir / output_file
                with open(baseline_path, 'w') as f:
                    f.write(content)
                
                print(
                    f"  {Fore.GREEN}✓ Baseline saved: "
                    f"known_good/{device_name}/{output_file}"
                )
            
            client.close()
            
        except Exception as e:
            print(f"{Fore.RED}✗ Error: {e}")
            continue
    
    # Git commit the baseline
    try:
        repo.git.add(A=True)
        
        if repo.is_dirty(untracked_files=True):
            commit = repo.index.commit(
                f"Initial baseline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            print(
                f"\n{Fore.GREEN}✓ Baseline committed to Git: "
                f"{commit.hexsha[:8]}"
            )
        else:
            print(f"\n{Fore.YELLOW}No changes to commit")
            
    except Exception as e:
        print(f"{Fore.RED}Git commit failed: {e}")
        
        # Configure Git identity if needed
        os.system('git config user.email "driftdetector@local"')
        os.system('git config user.name "Drift Detector"')
        
        repo.git.add(A=True)
        repo.index.commit(
            f"Initial baseline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print(f"{Fore.GREEN}✓ Baseline committed to Git")
    
    print(f"""
{Fore.GREEN}{'='*50}
✅ Baseline Setup Complete!
{'='*50}
{Fore.WHITE}Baseline files saved in: known_good/
Git history: run 'git log --oneline'

{Fore.YELLOW}Next steps:
  1. Verify baseline: cat known_good/{config['devices'][0]['name']}/running_config.txt
  2. Start monitoring: python3 drift_detector.py
{Fore.GREEN}{'='*50}
    """)


if __name__ == "__main__":
    setup_baseline()
