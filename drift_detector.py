#!/usr/bin/env python3
"""
Network Configuration Drift Detector
=====================================
Pulls configs from network devices and compares
against known-good Git baseline to detect changes.
"""

import os
import sys
import time
import logging
import hashlib
import difflib
import schedule
import yaml
import paramiko
import git
from datetime import datetime
from pathlib import Path
from colorama import init, Fore, Back, Style

# Initialize colorama for colored terminal output
init(autoreset=True)


# ============================================================
# CONFIGURATION LOADER
# ============================================================

class Config:
    """Load and hold all configuration settings"""
    
    def __init__(self, config_file="config.yaml"):
        self.config_file = config_file
        self.data = self._load_config()
        self.devices = self.data.get('devices', [])
        self.settings = self.data.get('settings', {})
        self.alerts = self.data.get('alerts', {})
    
    def _load_config(self):
        """Load YAML configuration file"""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"{Fore.RED}[ERROR] Config file not found: {self.config_file}")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"{Fore.RED}[ERROR] Invalid YAML config: {e}")
            sys.exit(1)


# ============================================================
# LOGGING SETUP
# ============================================================

def setup_logging(log_file="logs/drift.log"):
    """Setup logging to both file and console"""
    
    Path("logs").mkdir(exist_ok=True)
    
    logger = logging.getLogger('DriftDetector')
    logger.setLevel(logging.DEBUG)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ============================================================
# SSH DEVICE CONNECTOR
# ============================================================

class DeviceConnector:
    """Handles SSH connections to network devices"""
    
    def __init__(self, device_config, logger):
        self.device = device_config
        self.logger = logger
        self.client = None
    
    def connect(self):
        """Establish SSH connection to device"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(
                paramiko.AutoAddPolicy()
            )
            
            self.logger.info(
                f"Connecting to {self.device['name']} "
                f"({self.device['host']}:{self.device['port']})"
            )
            
            self.client.connect(
                hostname=self.device['host'],
                port=self.device['port'],
                username=self.device['username'],
                password=self.device['password'],
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            
            self.logger.info(f"Connected to {self.device['name']}")
            return True
            
        except paramiko.AuthenticationException:
            self.logger.error(
                f"Authentication failed for {self.device['name']}"
            )
            print(f"{Fore.RED}✗ Auth failed for {self.device['name']}")
            return False
        except Exception as e:
            self.logger.error(
                f"Connection failed to {self.device['name']}: {e}"
            )
            print(f"{Fore.RED}✗ Connection failed: {e}")
            return False
    
    def run_command(self, command):
        """Execute command on device and return output"""
        try:
            stdin, stdout, stderr = self.client.exec_command(
                command, 
                timeout=30,
                get_pty=True
            )
            
            output = stdout.read().decode('utf-8', errors='replace')
            errors = stderr.read().decode('utf-8', errors='replace')
            
            if errors and 'WARNING' not in errors and 'sudo' not in errors.lower():
                self.logger.warning(f"Command stderr: {errors[:200]}")
            
            return output.strip()
            
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return None
    
    def pull_configs(self, output_dir):
        """Pull all configured commands from device"""
        configs = {}
        
        if not self.connect():
            return None
        
        try:
            device_dir = Path(output_dir) / self.device['name']
            device_dir.mkdir(parents=True, exist_ok=True)
            
            for cmd_config in self.device.get('commands', []):
                command = cmd_config['command']
                output_file = cmd_config['output_file']
                
                self.logger.info(f"Running: {command[:50]}...")
                
                output = self.run_command(command)
                
                if output is not None:
                    header = (
                        f"# Device: {self.device['name']}\n"
                        f"# Command: {command}\n"
                        f"# Pulled: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"# {'='*50}\n\n"
                    )
                    
                    full_content = header + output
                    
                    file_path = device_dir / output_file
                    with open(file_path, 'w') as f:
                        f.write(full_content)
                    
                    configs[output_file] = full_content
                    self.logger.info(
                        f"Saved: {output_file} ({len(output)} bytes)"
                    )
                else:
                    self.logger.error(
                        f"Failed to get output for: {command}"
                    )
            
            return configs
            
        finally:
            self.disconnect()
    
    def disconnect(self):
        """Close SSH connection"""
        if self.client:
            self.client.close()


# ============================================================
# GIT BASELINE MANAGER
# ============================================================

class GitBaselineManager:
    """Manages Git repository for config baselines"""
    
    def __init__(self, repo_path, logger):
        self.repo_path = Path(repo_path)
        self.logger = logger
        self.repo = self._get_repo()
    
    def _get_repo(self):
        """Get or initialize Git repository"""
        try:
            repo = git.Repo(self.repo_path)
            self.logger.info(f"Using Git repo: {self.repo_path}")
            return repo
        except git.InvalidGitRepositoryError:
            repo = git.Repo.init(self.repo_path)
            self.logger.info(f"Initialized new Git repo: {self.repo_path}")
            return repo
    
    def get_baseline_content(self, device_name, filename):
        """Get the known-good baseline content"""
        baseline_path = (
            self.repo_path / "known_good" / device_name / filename
        )
        
        if not baseline_path.exists():
            self.logger.warning(
                f"No baseline found: {device_name}/{filename}"
            )
            return None
        
        with open(baseline_path, 'r') as f:
            return f.read()
    
    def save_baseline(self, device_name, filename, content):
        """Save configuration as new baseline"""
        baseline_dir = self.repo_path / "known_good" / device_name
        baseline_dir.mkdir(parents=True, exist_ok=True)
        
        baseline_path = baseline_dir / filename
        
        with open(baseline_path, 'w') as f:
            f.write(content)
        
        self.logger.info(f"Saved baseline: {device_name}/{filename}")
        return baseline_path
    
    def commit_baseline(self, message="Update baseline"):
        """Commit current baseline to Git"""
        try:
            self.repo.git.add(A=True)
            
            if self.repo.is_dirty(untracked_files=True):
                commit = self.repo.index.commit(
                    f"{message} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self.logger.info(f"Git commit: {commit.hexsha[:8]}")
                return commit.hexsha
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Git commit failed: {e}")
            return None


# ============================================================
# DRIFT DETECTOR (CORE ENGINE)
# ============================================================

class DriftDetector:
    """Core engine that detects configuration drift"""
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.git_manager = GitBaselineManager('.', logger)
        self.drift_count = 0
        self.check_count = 0
        
        self._setup_directories()
    
    def _setup_directories(self):
        """Create required project directories"""
        dirs = ['configs', 'known_good', 'logs', 'reports']
        for d in dirs:
            Path(d).mkdir(exist_ok=True)
    
    def _calculate_hash(self, content):
        """Calculate MD5 hash of content (ignoring timestamps)"""
        lines = content.split('\n')
        stable_lines = [
            line for line in lines 
            if not line.startswith('# Pulled:')
            and not line.startswith('# =')
        ]
        stable_content = '\n'.join(stable_lines)
        return hashlib.md5(stable_content.encode()).hexdigest()
    
    def _generate_diff(self, baseline, current, filename):
        """Generate diff between baseline and current"""
        baseline_lines = baseline.splitlines(keepends=True)
        current_lines = current.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            baseline_lines,
            current_lines,
            fromfile=f"baseline/{filename}",
            tofile=f"current/{filename}",
            lineterm=''
        ))
        
        return ''.join(diff)
    
    def _analyze_changes(self, diff_text):
        """Analyze diff and categorize severity"""
        added = []
        removed = []
        
        for line in diff_text.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                added.append(line[1:].strip())
            elif line.startswith('-') and not line.startswith('---'):
                removed.append(line[1:].strip())
        
        severity = "LOW"
        change_types = []
        
        high_severity = [
            'password', 'secret', 'crypto', 'no ip', 
            'shutdown', 'access-list', 'permit', 'deny',
            'no service', 'enable', 'username'
        ]
        
        medium_severity = [
            'ip route', 'neighbor', 'network', 'redistribute',
            'interface', 'ip address', 'ospf', 'bgp'
        ]
        
        all_changes = added + removed
        
        for change in all_changes:
            change_lower = change.lower()
            
            for keyword in high_severity:
                if keyword in change_lower:
                    severity = "HIGH"
                    change_types.append(f"Security: {change[:60]}")
                    break
            
            if severity != "HIGH":
                for keyword in medium_severity:
                    if keyword in change_lower:
                        if severity == "LOW":
                            severity = "MEDIUM"
                        change_types.append(f"Routing: {change[:60]}")
                        break
        
        return {
            'severity': severity,
            'lines_added': len(added),
            'lines_removed': len(removed),
            'change_types': list(set(change_types))[:5]
        }
    
    def _generate_alert(self, device_name, filename, analysis, diff_text):
        """Generate and display drift alert"""
        
        self.drift_count += 1
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if analysis['severity'] == 'HIGH':
            color = Fore.RED
            bg_color = Back.RED
        elif analysis['severity'] == 'MEDIUM':
            color = Fore.YELLOW
            bg_color = Back.YELLOW
        else:
            color = Fore.CYAN
            bg_color = Back.CYAN
        
        alert_box = f"""
{color}{'='*60}
{bg_color}{Fore.WHITE}  CONFIGURATION DRIFT DETECTED! {Style.RESET_ALL}
{color}{'='*60}
{Fore.WHITE}Timestamp : {timestamp}
{Fore.WHITE}Device    : {Fore.CYAN}{device_name}
{Fore.WHITE}File      : {Fore.CYAN}{filename}
{Fore.WHITE}Severity  : {color}{analysis['severity']}
{Fore.WHITE}Changes   : {Fore.YELLOW}+{analysis['lines_added']} added, -{analysis['lines_removed']} removed
"""
        
        if analysis['change_types']:
            alert_box += f"{Fore.WHITE}Details   :\n"
            for change in analysis['change_types']:
                alert_box += f"  {Fore.YELLOW}- {change}\n"
        
        alert_box += f"{color}{'='*60}{Style.RESET_ALL}"
        
        print(alert_box)
        
        self.logger.warning(
            f"DRIFT | Device: {device_name} | File: {filename} | "
            f"Severity: {analysis['severity']} | "
            f"+{analysis['lines_added']}/-{analysis['lines_removed']}"
        )
        
        self._save_report(device_name, filename, analysis, diff_text, timestamp)
        
        return analysis['severity']
    
    def _save_report(self, device_name, filename, analysis, diff_text, timestamp):
        """Save detailed drift report"""
        
        safe_time = timestamp.replace(':', '-').replace(' ', '_')
        report_name = f"drift_{device_name}_{filename}_{safe_time}.txt"
        report_path = Path('reports') / report_name
        
        report_content = f"""
NETWORK CONFIGURATION DRIFT REPORT
{'='*60}
Generated    : {timestamp}
Device       : {device_name}
Config File  : {filename}
Severity     : {analysis['severity']}
Lines Added  : {analysis['lines_added']}
Lines Removed: {analysis['lines_removed']}

CHANGE DETAILS:
{'-'*40}
"""
        for change in analysis['change_types']:
            report_content += f"- {change}\n"
        
        report_content += f"""
FULL DIFF:
{'-'*40}
{diff_text}

ACTION REQUIRED:
{'-'*40}
"""
        if analysis['severity'] == 'HIGH':
            report_content += (
                "HIGH SEVERITY - Immediate review required!\n"
                "Check for unauthorized access or security changes.\n"
            )
        elif analysis['severity'] == 'MEDIUM':
            report_content += (
                "MEDIUM SEVERITY - Review required within 24 hours.\n"
                "Verify if routing changes were authorized.\n"
            )
        else:
            report_content += (
                "LOW SEVERITY - Review at next maintenance window.\n"
            )
        
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        print(f"{Fore.GREEN}Report saved: {report_path}")
    
    def check_device(self, device_config):
        """Check a single device for drift"""
        
        device_name = device_config['name']
        
        print(f"\n{Fore.BLUE}{'-'*50}")
        print(f"{Fore.BLUE}Checking: {device_name}")
        print(f"{Fore.BLUE}{'-'*50}")
        
        connector = DeviceConnector(device_config, self.logger)
        current_configs = connector.pull_configs('configs')
        
        if current_configs is None:
            print(f"{Fore.RED}Failed to pull config from {device_name}")
            return
        
        drift_found = False
        
        for filename, current_content in current_configs.items():
            
            baseline_content = self.git_manager.get_baseline_content(
                device_name, filename
            )
            
            if baseline_content is None:
                print(f"{Fore.YELLOW}No baseline for {filename} - creating...")
                self.git_manager.save_baseline(
                    device_name, filename, current_content
                )
                continue
            
            baseline_hash = self._calculate_hash(baseline_content)
            current_hash = self._calculate_hash(current_content)
            
            if baseline_hash == current_hash:
                print(f"{Fore.GREEN}[OK] {filename}: No drift (hash: {current_hash[:8]})")
                self.logger.info(
                    f"CLEAN | {device_name}/{filename} | hash: {current_hash[:8]}"
                )
            else:
                drift_found = True
                
                diff_text = self._generate_diff(
                    baseline_content, current_content, filename
                )
                
                analysis = self._analyze_changes(diff_text)
                
                self._generate_alert(
                    device_name, filename, analysis, diff_text
                )
        
        if not drift_found:
            print(f"{Fore.GREEN}[OK] {device_name}: All configs match baseline!")
        
        self.git_manager.commit_baseline(f"Auto-check: {device_name}")
    
    def run_check(self):
        """Run drift check on all devices"""
        
        self.check_count += 1
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"\n{Fore.MAGENTA}{'='*60}")
        print(f"{Fore.MAGENTA}DRIFT CHECK #{self.check_count} - {timestamp}")
        print(f"{Fore.MAGENTA}{'='*60}")
        
        devices = self.config.devices
        
        if not devices:
            print(f"{Fore.RED}No devices configured!")
            return
        
        print(f"{Fore.WHITE}Checking {len(devices)} device(s)...")
        
        for device in devices:
            self.check_device(device)
        
        print(f"\n{Fore.CYAN}{'-'*50}")
        print(f"{Fore.CYAN}Summary:")
        print(f"{Fore.WHITE}  Total checks run  : {self.check_count}")
        print(f"{Fore.WHITE}  Total drifts found: "
              f"{Fore.RED if self.drift_count > 0 else Fore.GREEN}{self.drift_count}")
        print(f"{Fore.WHITE}  Next check in     : "
              f"{self.config.settings.get('check_interval_minutes', 5)} minutes")
        print(f"{Fore.CYAN}{'-'*50}")


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def print_banner():
    """Print startup banner"""
    banner = f"""
{Fore.CYAN}==========================================================
{Fore.CYAN}   Network Configuration Drift Detector v1.0
{Fore.YELLOW}   Monitoring your network for unauthorized changes
{Fore.CYAN}=========================================================={Style.RESET_ALL}
"""
    print(banner)


def main():
    """Main function"""
    
    print_banner()
    
    config = Config('config.yaml')
    
    logger = setup_logging(
        config.settings.get('log_file', 'logs/drift.log')
    )
    
    logger.info("="*50)
    logger.info("Drift Detector Started")
    logger.info("="*50)
    
    detector = DriftDetector(config, logger)
    
    interval = config.settings.get('check_interval_minutes', 5)
    
    print(f"{Fore.GREEN}[OK] Configuration loaded")
    print(f"{Fore.GREEN}[OK] Monitoring {len(config.devices)} device(s)")
    print(f"{Fore.GREEN}[OK] Check interval: every {interval} minute(s)")
    print(f"{Fore.YELLOW}Running first check now...\n")
    
    # Run immediately on start
    detector.run_check()
    
    # Schedule periodic checks
    schedule.every(interval).minutes.do(detector.run_check)
    
    print(f"\n{Fore.GREEN}Scheduler running - Press Ctrl+C to stop\n")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Drift Detector stopped by user")
        logger.info("Drift Detector stopped by user")
        print(f"\n{Fore.CYAN}Final Stats:")
        print(f"  Checks run   : {detector.check_count}")
        print(f"  Drifts found : {detector.drift_count}")


if __name__ == "__main__":
    main()
