#!/usr/bin/env python3
"""
Drift Simulator - Test your detector
Makes unauthorized changes to simulate drift
"""
import subprocess
import time
from colorama import init, Fore
init(autoreset=True)

def simulate_unauthorized_change():
    """Add unauthorized route to simulate drift"""
    
    print(f"{Fore.YELLOW}⚠️  Simulating unauthorized change...")
    
    # Add a suspicious route (this simulates an attacker adding a route)
    commands = [
        "sudo vtysh -c 'configure terminal' -c 'ip route 172.16.99.0/24 192.168.1.99' -c 'end' -c 'write'",
    ]
    
    for cmd in commands:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"{Fore.RED}✓ Unauthorized route added: 172.16.99.0/24")
        else:
            print(f"{Fore.YELLOW}Command output: {result.stderr}")

def revert_change():
    """Remove the unauthorized change"""
    
    print(f"{Fore.GREEN}Reverting unauthorized change...")
    
    cmd = "sudo vtysh -c 'configure terminal' -c 'no ip route 172.16.99.0/24 192.168.1.99' -c 'end' -c 'write'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"{Fore.GREEN}✓ Change reverted")
    else:
        print(f"Output: {result.stderr}")

if __name__ == "__main__":
    print(f"""
{Fore.CYAN}Drift Simulator
{Fore.CYAN}{'='*40}
1. Simulate unauthorized change
2. Revert change
3. Exit
    """)
    
    choice = input("Choose (1/2/3): ").strip()
    
    if choice == "1":
        simulate_unauthorized_change()
        print(f"\n{Fore.YELLOW}Now run drift_detector.py to see the alert!")
    elif choice == "2":
        revert_change()
    else:
        print("Exiting...")
