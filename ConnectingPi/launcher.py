#!/usr/bin/env python3
"""
=============================================================================
AIRWAVE LAUNCHER
=============================================================================
Unified launcher for the AirWave application.
Runs the dashboard locally, and SSH into Pi1/Pi2 to run agents remotely.

Usage:
    python launcher.py              # Run all components
    python launcher.py --setup      # Run onboarding setup only
    python launcher.py --dashboard  # Run dashboard only
    python launcher.py --pi1        # Run pi1_agent only
    python launcher.py --pi2        # Run pi2_agent only
    python launcher.py --local      # Run agents locally (no SSH)

First run will automatically trigger the onboarding process.
=============================================================================
"""

import os
import sys
import subprocess
import signal
import time
import socket
import argparse
import re
import json
from pathlib import Path

# Get the directory where this script lives
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / "config.py"
DASHBOARD_DIR = SCRIPT_DIR / "dashboard"
DASHBOARD_CONFIG = DASHBOARD_DIR / "config.js"
LAUNCHER_CONFIG = SCRIPT_DIR / ".airwave_config.json"

# ANSI colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_banner():
    """Print the AirWave banner."""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║              🌊  A I R W A V E  🌊                        ║
    ║                                                           ║
    ║              Gesture Control System                       ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
{Colors.ENDC}"""
    print(banner)

def print_status(message, status="info"):
    """Print a status message with color."""
    icons = {
        "info": f"{Colors.BLUE}ℹ{Colors.ENDC}",
        "success": f"{Colors.GREEN}✓{Colors.ENDC}",
        "warning": f"{Colors.YELLOW}⚠{Colors.ENDC}",
        "error": f"{Colors.RED}✗{Colors.ENDC}",
        "running": f"{Colors.CYAN}►{Colors.ENDC}",
    }
    icon = icons.get(status, icons["info"])
    print(f"  {icon} {message}")

def check_connection(host, port=22, timeout=3):
    """Check if a host is reachable on a given port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.gaierror:
        return False
    except Exception:
        return False

def check_ssh_connection(host, user, timeout=10):
    """Check if SSH connection works (assumes SSH keys are set up)."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", 
             f"{user}@{host}", "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0
    except Exception:
        return False

# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

def load_config():
    """Load launcher configuration from JSON file."""
    if LAUNCHER_CONFIG.exists():
        try:
            with open(LAUNCHER_CONFIG, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(config):
    """Save launcher configuration to JSON file."""
    try:
        with open(LAUNCHER_CONFIG, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print_status(f"Failed to save config: {e}", "error")
        return False

def get_current_broker():
    """Read the current MQTT broker from config.py."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
        match = re.search(r'MQTT_BROKER_DEFAULT\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def update_config_file(broker_address):
    """Update the MQTT broker in config.py."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
        
        new_content = re.sub(
            r'(MQTT_BROKER_DEFAULT\s*=\s*)["\'][^"\']*["\']',
            f'\\1"{broker_address}"',
            content
        )
        
        with open(CONFIG_FILE, 'w') as f:
            f.write(new_content)
        return True
    except Exception as e:
        print_status(f"Failed to update config.py: {e}", "error")
        return False

def update_dashboard_config(broker_address):
    """Create/update the dashboard config.js file."""
    config_content = f"""// Auto-generated by launcher.py - DO NOT EDIT MANUALLY
// Run 'python launcher.py --setup' to reconfigure

const MQTT_CONFIG = {{
    host: '{broker_address}',
    wsPort: 9001,
    get broker() {{
        return `ws://${{this.host}}:${{this.wsPort}}`;
    }}
}};
"""
    try:
        with open(DASHBOARD_CONFIG, 'w') as f:
            f.write(config_content)
        return True
    except Exception as e:
        print_status(f"Failed to create dashboard config: {e}", "error")
        return False

def update_dashboard_html():
    """Update dashboard HTML to use external config.js if not already done."""
    html_file = DASHBOARD_DIR / "index.html"
    try:
        with open(html_file, 'r') as f:
            content = f.read()
        
        if 'src="config.js"' in content:
            return True
        
        new_content = content.replace(
            '<script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>',
            '<script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>\n    <script src="config.js"></script>'
        )
        
        new_content = re.sub(
            r"const MQTT_HOST = '[^']+';.*?// <-- CHANGE THIS.*?\n",
            "const MQTT_HOST = MQTT_CONFIG.host;  // Loaded from config.js\n",
            new_content
        )
        
        new_content = re.sub(
            r"const MQTT_WS_PORT = \d+;.*?// WebSocket port.*?\n",
            "const MQTT_WS_PORT = MQTT_CONFIG.wsPort;  // Loaded from config.js\n",
            new_content
        )
        
        with open(html_file, 'w') as f:
            f.write(new_content)
        return True
    except Exception as e:
        print_status(f"Failed to update dashboard HTML: {e}", "error")
        return False

def is_first_run():
    """Check if this is the first run."""
    return not LAUNCHER_CONFIG.exists()

# =============================================================================
# ONBOARDING
# =============================================================================

def prompt_with_default(prompt, default=None):
    """Prompt for input with an optional default value."""
    if default:
        user_input = input(f"  {prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        return input(f"  {prompt}: ").strip()

def run_onboarding():
    """Run the full onboarding process."""
    config = load_config()
    
    # ===================
    # MQTT BROKER SETUP
    # ===================
    print(f"\n{Colors.BOLD}━━━ Step 1: MQTT Broker Configuration ━━━{Colors.ENDC}\n")
    
    current_broker = config.get('mqtt_broker') or get_current_broker()
    
    print(f"""  {Colors.YELLOW}Enter your MQTT broker address.{Colors.ENDC}
  This is the computer running Mosquitto (usually your Mac/PC).
  Examples: My-MacBook.local, 192.168.1.100, localhost
""")
    
    while True:
        broker = prompt_with_default("MQTT Broker address", current_broker)
        
        if not broker:
            print_status("Please enter a valid address", "warning")
            continue
        
        print_status(f"Testing MQTT connection to {broker}:1883...", "info")
        
        if check_connection(broker, 1883):
            print_status("MQTT broker is reachable!", "success")
            config['mqtt_broker'] = broker
            break
        else:
            print_status(f"Could not connect to {broker}:1883", "warning")
            proceed = input("  Continue anyway? [y/N]: ").strip().lower()
            if proceed == 'y':
                config['mqtt_broker'] = broker
                break
    
    # ===================
    # PI1 SETUP
    # ===================
    print(f"\n{Colors.BOLD}━━━ Step 2: Raspberry Pi 1 (Gesture Sensor) ━━━{Colors.ENDC}\n")
    
    print(f"""  {Colors.YELLOW}Configure the Pi that runs the IMU/gesture sensor.{Colors.ENDC}
  Leave blank to skip (won't launch Pi1 agent).
""")
    
    pi1_host = prompt_with_default("Pi1 hostname or IP", config.get('pi1_host', ''))
    
    if pi1_host:
        pi1_user = prompt_with_default("Pi1 username", config.get('pi1_user', 'pi'))
        pi1_path = prompt_with_default(
            "Path to pi1_agent.py on Pi1", 
            config.get('pi1_path', '~/AirWave/pi1_agent.py')
        )
        
        print_status(f"Testing SSH connection to {pi1_user}@{pi1_host}...", "info")
        
        if check_ssh_connection(pi1_host, pi1_user):
            print_status("SSH connection successful!", "success")
        else:
            print_status("SSH connection failed", "warning")
            print(f"""
  {Colors.YELLOW}Make sure:{Colors.ENDC}
    1. Pi1 is powered on and connected to the network
    2. SSH is enabled on Pi1
    3. SSH keys are set up (run: ssh-copy-id {pi1_user}@{pi1_host})
""")
        
        config['pi1_host'] = pi1_host
        config['pi1_user'] = pi1_user
        config['pi1_path'] = pi1_path
    else:
        config['pi1_host'] = ''
        print_status("Pi1 skipped - will not launch pi1_agent", "info")
    
    # ===================
    # PI2 SETUP
    # ===================
    print(f"\n{Colors.BOLD}━━━ Step 3: Raspberry Pi 2 (Camera/Display) ━━━{Colors.ENDC}\n")
    
    print(f"""  {Colors.YELLOW}Configure the Pi that runs the camera/face detection.{Colors.ENDC}
  Leave blank to skip (won't launch Pi2 agent).
""")
    
    pi2_host = prompt_with_default("Pi2 hostname or IP", config.get('pi2_host', ''))
    
    if pi2_host:
        pi2_user = prompt_with_default("Pi2 username", config.get('pi2_user', 'pi'))
        pi2_path = prompt_with_default(
            "Path to pi2_agent.py on Pi2", 
            config.get('pi2_path', '~/AirWave/pi2_agent.py')
        )
        
        print_status(f"Testing SSH connection to {pi2_user}@{pi2_host}...", "info")
        
        if check_ssh_connection(pi2_host, pi2_user):
            print_status("SSH connection successful!", "success")
        else:
            print_status("SSH connection failed", "warning")
            print(f"""
  {Colors.YELLOW}Make sure:{Colors.ENDC}
    1. Pi2 is powered on and connected to the network
    2. SSH is enabled on Pi2
    3. SSH keys are set up (run: ssh-copy-id {pi2_user}@{pi2_host})
""")
        
        config['pi2_host'] = pi2_host
        config['pi2_user'] = pi2_user
        config['pi2_path'] = pi2_path
    else:
        config['pi2_host'] = ''
        print_status("Pi2 skipped - will not launch pi2_agent", "info")
    
    # ===================
    # SAVE CONFIGURATION
    # ===================
    print(f"\n{Colors.BOLD}━━━ Saving Configuration ━━━{Colors.ENDC}\n")
    
    # Save launcher config
    save_config(config)
    print_status("Saved .airwave_config.json", "success")
    
    # Update config.py
    if update_config_file(config['mqtt_broker']):
        print_status("Updated config.py", "success")
    
    # Update dashboard config
    if update_dashboard_config(config['mqtt_broker']):
        print_status("Created dashboard/config.js", "success")
    
    if update_dashboard_html():
        print_status("Updated dashboard/index.html", "success")
    
    # Set environment variable
    os.environ['MQTT_BROKER'] = config['mqtt_broker']
    
    # Print summary
    print(f"\n{Colors.BOLD}━━━ Configuration Summary ━━━{Colors.ENDC}\n")
    print(f"  MQTT Broker:  {Colors.CYAN}{config['mqtt_broker']}{Colors.ENDC}")
    if config.get('pi1_host'):
        print(f"  Pi1:          {Colors.GREEN}{config['pi1_user']}@{config['pi1_host']}{Colors.ENDC}")
        print(f"                {config['pi1_path']}")
    else:
        print(f"  Pi1:          {Colors.YELLOW}(not configured){Colors.ENDC}")
    if config.get('pi2_host'):
        print(f"  Pi2:          {Colors.GREEN}{config['pi2_user']}@{config['pi2_host']}{Colors.ENDC}")
        print(f"                {config['pi2_path']}")
    else:
        print(f"  Pi2:          {Colors.YELLOW}(not configured){Colors.ENDC}")
    
    print(f"\n  {Colors.GREEN}✓ Setup complete!{Colors.ENDC}\n")
    
    return config

# =============================================================================
# PROCESS MANAGEMENT
# =============================================================================

class ProcessManager:
    """Manages subprocess lifecycle (local and SSH)."""
    
    def __init__(self):
        self.processes = {}
        self.running = True
        
    def start_local_process(self, name, cmd, cwd=None):
        """Start a local subprocess."""
        try:
            env = os.environ.copy()
            process = subprocess.Popen(
                cmd,
                cwd=cwd or SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            self.processes[name] = {'process': process, 'type': 'local'}
            print_status(f"{name} started locally (PID: {process.pid})", "running")
            return process
        except Exception as e:
            print_status(f"Failed to start {name}: {e}", "error")
            return None
    
    def start_ssh_process(self, name, host, user, remote_cmd, mqtt_broker=None):
        """Start a remote process via SSH."""
        try:
            # Build SSH command with environment variable
            env_prefix = f"MQTT_BROKER={mqtt_broker} " if mqtt_broker else ""
            ssh_cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-tt",  # Force pseudo-terminal for better signal handling
                f"{user}@{host}",
                f"{env_prefix}python3 {remote_cmd}"
            ]
            
            process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.processes[name] = {'process': process, 'type': 'ssh', 'host': host, 'user': user}
            print_status(f"{name} started via SSH on {user}@{host} (PID: {process.pid})", "running")
            return process
        except Exception as e:
            print_status(f"Failed to start {name}: {e}", "error")
            return None
    
    def stop_all(self):
        """Stop all running processes."""
        self.running = False
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.ENDC}")
        
        for name, info in self.processes.items():
            process = info['process']
            if process and process.poll() is None:
                print_status(f"Stopping {name}...", "info")
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        
        print_status("All processes stopped", "success")
    
    def monitor_output(self):
        """Monitor and print output from all processes."""
        while self.running:
            for name, info in list(self.processes.items()):
                process = info['process']
                if process is None:
                    continue
                    
                if process.poll() is not None:
                    exit_status = "error" if process.returncode != 0 else "info"
                    print_status(f"{name} exited with code {process.returncode}", exit_status)
                    del self.processes[name]
                    continue
                
                try:
                    if process.stdout:
                        line = process.stdout.readline()
                        if line:
                            colors = {
                                "Dashboard": Colors.CYAN,
                                "Pi1 Agent": Colors.GREEN,
                                "Pi2 Agent": Colors.YELLOW,
                            }
                            color = colors.get(name, Colors.ENDC)
                            print(f"  {color}[{name}]{Colors.ENDC} {line.rstrip()}")
                except Exception:
                    pass
            
            time.sleep(0.1)
            
            # Exit if all processes have stopped
            if not self.processes:
                print_status("All processes have exited", "info")
                break

# =============================================================================
# MAIN
# =============================================================================

def prompt_mqtt_broker():
    """Quick prompt for MQTT broker address before starting."""
    config = load_config()
    current_broker = config.get('mqtt_broker') or get_current_broker()
    
    print(f"\n{Colors.BOLD}━━━ MQTT Broker ━━━{Colors.ENDC}\n")
    
    if current_broker:
        broker = input(f"  MQTT Broker [{current_broker}]: ").strip()
        if not broker:
            broker = current_broker
    else:
        broker = input(f"  MQTT Broker: ").strip()
        if not broker:
            broker = "localhost"
    
    # Save to all config locations
    config['mqtt_broker'] = broker
    save_config(config)
    update_config_file(broker)
    update_dashboard_config(broker)
    update_dashboard_html()
    os.environ['MQTT_BROKER'] = broker
    
    print_status(f"Using MQTT Broker: {Colors.CYAN}{broker}{Colors.ENDC}", "success")
    
    return broker, config

def main():
    parser = argparse.ArgumentParser(description="AirWave Launcher")
    parser.add_argument('--setup', action='store_true', help='Run onboarding setup only')
    parser.add_argument('--dashboard', action='store_true', help='Run dashboard only')
    parser.add_argument('--pi1', action='store_true', help='Run pi1_agent only')
    parser.add_argument('--pi2', action='store_true', help='Run pi2_agent only')
    parser.add_argument('--local', action='store_true', help='Run agents locally (no SSH)')
    args = parser.parse_args()
    
    print_banner()
    
    # Determine what to run
    run_all = not (args.dashboard or args.pi1 or args.pi2 or args.setup)
    run_dashboard = args.dashboard or run_all
    run_pi1 = args.pi1 or run_all
    run_pi2 = args.pi2 or run_all
    
    # Full setup mode
    if args.setup:
        config = run_onboarding()
        print(f"  Run {Colors.CYAN}python launcher.py{Colors.ENDC} to start the application.\n")
        return
    
    # First run - need full setup
    if is_first_run():
        print(f"  {Colors.YELLOW}First time setup detected!{Colors.ENDC}")
        config = run_onboarding()
    else:
        # Quick MQTT broker prompt before starting
        mqtt_broker, config = prompt_mqtt_broker()
    
    # Ensure dashboard config exists
    if not DASHBOARD_CONFIG.exists():
        broker = config.get('mqtt_broker') or get_current_broker() or "localhost"
        update_dashboard_config(broker)
        update_dashboard_html()
    
    # Set up process manager
    manager = ProcessManager()
    
    # Handle Ctrl+C
    def signal_handler(sig, frame):
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"\n{Colors.BOLD}━━━ Starting Services ━━━{Colors.ENDC}\n")
    
    mqtt_broker = config.get('mqtt_broker', 'localhost')
    
    # Start dashboard server (always local)
    if run_dashboard:
        manager.start_local_process(
            "Dashboard",
            [sys.executable, "-m", "http.server", "8080"],
            cwd=DASHBOARD_DIR
        )
        print_status(f"Dashboard available at: {Colors.CYAN}http://localhost:8080{Colors.ENDC}", "info")
    
    # Start pi1_agent
    if run_pi1:
        if args.local:
            # Run locally
            pi1_script = SCRIPT_DIR / "pi1_agent.py"
            if pi1_script.exists():
                manager.start_local_process(
                    "Pi1 Agent",
                    [sys.executable, str(pi1_script)]
                )
            else:
                print_status("pi1_agent.py not found locally", "warning")
        elif config.get('pi1_host'):
            # Run via SSH
            manager.start_ssh_process(
                "Pi1 Agent",
                config['pi1_host'],
                config['pi1_user'],
                config['pi1_path'],
                mqtt_broker
            )
        else:
            print_status("Pi1 not configured - run 'python launcher.py --setup'", "warning")
    
    # Start pi2_agent
    if run_pi2:
        if args.local:
            # Run locally
            pi2_script = SCRIPT_DIR / "pi2_agent.py"
            if pi2_script.exists():
                manager.start_local_process(
                    "Pi2 Agent",
                    [sys.executable, str(pi2_script)]
                )
            else:
                print_status("pi2_agent.py not found locally", "warning")
        elif config.get('pi2_host'):
            # Run via SSH
            manager.start_ssh_process(
                "Pi2 Agent",
                config['pi2_host'],
                config['pi2_user'],
                config['pi2_path'],
                mqtt_broker
            )
        else:
            print_status("Pi2 not configured - run 'python launcher.py --setup'", "warning")
    
    print(f"\n{Colors.BOLD}━━━ Running ━━━{Colors.ENDC}")
    print(f"  Press {Colors.YELLOW}Ctrl+C{Colors.ENDC} to stop all services\n")
    
    # Monitor process output
    try:
        manager.monitor_output()
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()

if __name__ == "__main__":
    main()
