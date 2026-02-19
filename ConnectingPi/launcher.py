#!/usr/bin/env python3
"""
=============================================================================
AIRWAVE LAUNCHER - Enhanced with Spotify Auto-Setup
=============================================================================
Unified launcher for the AirWave application with automatic Spotify configuration.

Usage:
    python3 launcher.py              # Run all components
    python3 launcher.py --setup      # Run onboarding setup only
    python3 launcher.py --dashboard  # Run dashboard only
    python3 launcher.py --pi1        # Run pi1_agent only
    python3 launcher.py --pi2        # Run pi2_agent only
    python3 launcher.py --local      # Run agents locally (no SSH)

First run will automatically trigger onboarding including Spotify setup.
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
import webbrowser
import http.server
import threading
import urllib.parse
import base64
from pathlib import Path

# Debug mode - set to True to enable verbose logging
DEBUG = os.environ.get('AIRWAVE_DEBUG', '').lower() in ('1', 'true', 'yes')

# Get the directory where this script lives
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / "config.py"
SPOTIFY_CONTROLLER = SCRIPT_DIR / "spotify_controller.py"
DASHBOARD_DIR = SCRIPT_DIR / "dashboard"
DASHBOARD_CONFIG = DASHBOARD_DIR / "config.js"
LAUNCHER_CONFIG = SCRIPT_DIR / ".airwave_config.json"
PI1_SSH_HOST = "pi1.local"
PI2_SSH_HOST = "pi2.local"
PI_SSH_USER = "pi"

# Pi SSH passwords (hardcoded for convenience)
PI1_PASSWORD = "raspberry"  # <-- CHANGE THIS to your Pi 1 password
PI2_PASSWORD = "raspberry"  # <-- CHANGE THIS to your Pi 2 password

# Default paths on the Pis (pre-configured for product handoff)
PI1_SCRIPT_PATH = "~/FinalVersion/Team6/ConnectingPi/pi1_agent.py"
PI2_SCRIPT_PATH = "~/FinalVersion/Team6/ConnectingPi/pi2_agent.py"

# ANSI colors
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
    if DEBUG:
        print(f"{Colors.YELLOW}    [DEBUG MODE ENABLED - Verbose logging active]{Colors.ENDC}\n")

def print_status(message, status="info"):
    icons = {
        "info": f"{Colors.BLUE}ℹ{Colors.ENDC}",
        "success": f"{Colors.GREEN}✓{Colors.ENDC}",
        "warning": f"{Colors.YELLOW}⚠{Colors.ENDC}",
        "error": f"{Colors.RED}✗{Colors.ENDC}",
        "running": f"{Colors.CYAN}►{Colors.ENDC}",
    }
    icon = icons.get(status, icons["info"])
    print(f"  {icon} {message}")

def debug(message, data=None):
    """Print debug message if DEBUG mode is enabled."""
    if DEBUG:
        timestamp = time.strftime("%H:%M:%S")
        print(f"  {Colors.CYAN}[DEBUG {timestamp}]{Colors.ENDC} {message}")
        if data is not None:
            import pprint
            pprint.pprint(data, indent=4, width=80)

# =============================================================================
# SPOTIFY AUTHENTICATION (embedded from spotify_auth.py)
# =============================================================================

def spotify_authenticate(client_id, client_secret):
    """
    Run Spotify OAuth flow and return refresh token.
    Returns: (refresh_token, error_message)
    """
    redirect_uri = "http://127.0.0.1:8888/callback"
    scopes = "user-modify-playback-state user-read-playback-state"
    
    auth_code = None
    server_done = threading.Event()
    
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            
            if "code" in params:
                auth_code = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"""
                    <html><body style='font-family:sans-serif;text-align:center;padding:60px'>
                    <h2>&#10003; Authorization successful!</h2>
                    <p>You can close this tab and return to the terminal.</p>
                    </body></html>
                """)
            else:
                error = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.end_headers()
                msg = f"<html><body>Error: {error}</body></html>"
                self.wfile.write(msg.encode())
            
            server_done.set()
        
        def log_message(self, format, *args):
            pass  # Suppress logs
    
    # Start callback server
    try:
        server = http.server.HTTPServer(("127.0.0.1", 8888), CallbackHandler)
        thread = threading.Thread(target=server.handle_request)
        thread.daemon = True
        thread.start()
    except Exception as e:
        return None, f"Failed to start callback server: {e}"
    
    # Open browser for auth
    auth_url = (
        "https://accounts.spotify.com/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&scope={urllib.parse.quote(scopes)}"
    )
    
    print_status("Opening Spotify login in your browser...", "info")
    print(f"  {Colors.CYAN}If browser doesn't open, visit:{Colors.ENDC}")
    print(f"  {auth_url}\n")
    
    try:
        webbrowser.open(auth_url)
    except:
        pass
    
    print_status("Waiting for authorization...", "info")
    server_done.wait(timeout=120)
    
    if not auth_code:
        return None, "No authorization code received. Did you approve the request?"
    
    # Exchange code for tokens
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    try:
        import requests
    except ImportError:
        return None, "requests library not installed. Run: pip3 install requests"
    
    try:
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri
            },
            timeout=10
        )
        
        if response.status_code != 200:
            return None, f"Token exchange failed: {response.status_code} - {response.text}"
        
        tokens = response.json()
        refresh_token = tokens.get("refresh_token")
        
        if not refresh_token:
            return None, "No refresh token in response"
        
        return refresh_token, None
        
    except Exception as e:
        return None, f"Token exchange error: {e}"


def setup_spotify():
    """Interactive Spotify setup (REQUIRED) - returns (client_id, client_secret, refresh_token) or None."""
    print(f"\n{Colors.BOLD}━━━ Spotify Setup (Required) ━━━{Colors.ENDC}\n")
    print("  AirWave requires Spotify Premium to function.")
    print("  You'll need to create a Spotify Developer App (takes 2 minutes).\n")
    
    print(f"\n{Colors.YELLOW}Step 1: Create Spotify Developer App{Colors.ENDC}")
    print("  1. Go to: https://developer.spotify.com/dashboard")
    print("  2. Click 'Log In' (top right)")
    print(f"     {Colors.RED}⚠️  LOGIN with the Spotify account you'll use to play music{Colors.ENDC}")
    print("  3. Click your profile → Dashboard → 'Create App'")
    print("  4. App Settings:")
    print("     • App Name: AirWave (or anything)")
    print("     • Redirect URI: http://127.0.0.1:8888/callback")
    print("  5. Copy your Client ID and Client Secret\n")
    
    input(f"  Press {Colors.CYAN}Enter{Colors.ENDC} when you have your credentials ready...")
    
    client_id = input(f"\n  Spotify Client ID: ").strip()
    if not client_id:
        print_status("Client ID required. Cannot proceed without Spotify.", "error")
        return None
    
    client_secret = input(f"  Spotify Client Secret: ").strip()
    if not client_secret:
        print_status("Client Secret required. Cannot proceed without Spotify.", "error")
        return None
    
    print(f"\n{Colors.YELLOW}Step 2: Authorize AirWave{Colors.ENDC}")
    print("  A browser window will open for you to authorize AirWave.")
    print("  Make sure you're logged into the Spotify account you want to use!\n")
    
    input(f"  Press {Colors.CYAN}Enter{Colors.ENDC} to continue...")
    
    refresh_token, error = spotify_authenticate(client_id, client_secret)
    
    if error:
        print_status(f"Spotify auth failed: {error}", "error")
        print_status("AirWave cannot function without Spotify. Please try again.", "error")
        return None
    
    print_status("Spotify authorization successful!", "success")
    return (client_id, client_secret, refresh_token)


def update_spotify_config(client_id, client_secret, refresh_token):
    """Update config.py and spotify_controller.py with Spotify credentials."""
    
    # Update config.py
    try:
        config_addition = f'''

# ============================================================
# SPOTIFY API CREDENTIALS (added by launcher)
# ============================================================
SPOTIFY_CLIENT_ID     = "{client_id}"
SPOTIFY_CLIENT_SECRET = "{client_secret}"
SPOTIFY_REFRESH_TOKEN = "{refresh_token}"
'''
        
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
        
        # Remove existing Spotify section if present
        content = re.sub(
            r'\n# ={60,}\n# SPOTIFY API CREDENTIALS.*?\n# ={60,}\n.*?(?=\n# ={60,}|\Z)',
            '',
            content,
            flags=re.DOTALL
        )
        
        with open(CONFIG_FILE, 'a') as f:
            f.write(config_addition)
        
        print_status("Updated config.py with Spotify credentials", "success")
        
    except Exception as e:
        print_status(f"Failed to update config.py: {e}", "error")
        return False
    
    # Update spotify_controller.py
    try:
        with open(SPOTIFY_CONTROLLER, 'r') as f:
            content = f.read()
        
        # Replace credential lines
        content = re.sub(
            r'SPOTIFY_CLIENT_ID\s*=\s*["\'][^"\']*["\']',
            f'SPOTIFY_CLIENT_ID     = "{client_id}"',
            content
        )
        content = re.sub(
            r'SPOTIFY_CLIENT_SECRET\s*=\s*["\'][^"\']*["\']',
            f'SPOTIFY_CLIENT_SECRET = "{client_secret}"',
            content
        )
        content = re.sub(
            r'SPOTIFY_REFRESH_TOKEN\s*=\s*["\'][^"\']*["\']',
            f'SPOTIFY_REFRESH_TOKEN = "{refresh_token}"',
            content
        )
        
        with open(SPOTIFY_CONTROLLER, 'w') as f:
            f.write(content)
        
        print_status("Updated spotify_controller.py with credentials", "success")
        return True
        
    except Exception as e:
        print_status(f"Failed to update spotify_controller.py: {e}", "error")
        return False


# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

def load_config():
    if LAUNCHER_CONFIG.exists():
        try:
            with open(LAUNCHER_CONFIG, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(config):
    try:
        with open(LAUNCHER_CONFIG, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print_status(f"Failed to save config: {e}", "error")
        return False

def get_current_broker():
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
    config_content = f"""// Auto-generated by launcher.py
const MQTT_CONFIG = {{
    host: '{broker_address}',
    wsPort: 9001,
    get broker() {{
        return `ws://${{this.host}}:${{this.wsPort}}`;
    }}
}};
"""
    try:
        DASHBOARD_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with open(DASHBOARD_CONFIG, 'w') as f:
            f.write(config_content)
        return True
    except Exception as e:
        print_status(f"Failed to create dashboard config: {e}", "error")
        return False

def is_first_run():
    return not LAUNCHER_CONFIG.exists()

# =============================================================================
# ONBOARDING
# =============================================================================

def run_onboarding():
    """Run setup - offers web or terminal interface."""
    print(f"\n{Colors.BOLD}━━━ AirWave Setup ━━━{Colors.ENDC}\n")
    
    # Offer web-based or terminal-based setup
    print("  Choose your setup method:")
    print(f"  {Colors.CYAN}1. Web Interface{Colors.ENDC} (recommended)")
    print(f"  {Colors.CYAN}2. Terminal{Colors.ENDC} (for advanced users)\n")
    
    choice = input("  Enter choice (1 or 2) [1]: ").strip()
    
    if choice == "2":
        # Terminal-based setup
        return run_terminal_setup()
    else:
        # Web-based setup (default)
        return run_web_setup_flow()


def run_web_setup_flow():
    """Run web-based setup and return config."""
    print(f"\n{Colors.CYAN}Opening web setup interface...{Colors.ENDC}\n")
    
    # Import and run web setup
    try:
        from web_setup_embedded import run_web_setup
        web_config = run_web_setup()
        
        if not web_config:
            print_status("Setup cancelled", "warning")
            return {}
        
        # Process web config into launcher config
        config = {}
        config['mqtt_broker'] = web_config.get('mqtt_broker', 'localhost')
        
        # Update config.py with MQTT broker
        update_config_file(config['mqtt_broker'])
        update_dashboard_config(config['mqtt_broker'])
        
        # Handle Spotify (always required)
        client_id = web_config.get('spotify_client_id')
        client_secret = web_config.get('spotify_client_secret')
        
        if client_id and client_secret:
            print_status("Authorizing Spotify...", "info")
            refresh_token, error = spotify_authenticate(client_id, client_secret)
            
            if refresh_token:
                update_spotify_config(client_id, client_secret, refresh_token)
                config['spotify_configured'] = True
                print_status("Spotify configured successfully!", "success")
            else:
                print_status(f"Spotify auth failed: {error}", "error")
                config['spotify_configured'] = False
        else:
            config['spotify_configured'] = False
        
        # Save Pi paths
        config['pi1_host'] = PI1_SSH_HOST
        config['pi1_path'] = PI1_SCRIPT_PATH
        config['pi2_host'] = PI2_SSH_HOST
        config['pi2_path'] = PI2_SCRIPT_PATH
        
        save_config(config)
        
        if not config.get('spotify_configured'):
            print(f"\n{Colors.RED}━━━ Setup Incomplete ━━━{Colors.ENDC}\n")
            print_status("Spotify is required for AirWave to function", "error")
            print(f"  Run {Colors.CYAN}python3 launcher.py --setup{Colors.ENDC} to try again.\n")
        else:
            print(f"\n{Colors.GREEN}━━━ Setup Complete! ━━━{Colors.ENDC}\n")
            print_status("Configuration saved", "success")
            
            # Important: Bluetooth pairing instructions
            print(f"\n{Colors.BOLD}📱 IMPORTANT: Pair Your Phone with Pi 2{Colors.ENDC}")
            print(f"  {Colors.CYAN}1.{Colors.ENDC} Open Bluetooth settings on your phone")
            print(f"  {Colors.CYAN}2.{Colors.ENDC} Look for {Colors.YELLOW}\"PiSpeaker\"{Colors.ENDC}")
            print(f"  {Colors.CYAN}3.{Colors.ENDC} Tap to connect")
            print(f"  {Colors.GREEN}→{Colors.ENDC} This is where your music will play!")
            print()
        
        return config
        
    except ImportError:
        print_status("Web setup module not found (web_setup_embedded.py).", "error")
        print_status("Make sure web_setup_embedded.py is in the same directory as launcher.py", "error")
        print_status("Falling back to terminal setup...", "warning")
        return run_terminal_setup()


def run_terminal_setup():
    print(f"\n{Colors.BOLD}━━━ AirWave Setup ━━━{Colors.ENDC}\n")
    
    config = load_config()
    
    # 1. MQTT Broker
    print(f"{Colors.BOLD}1. MQTT Broker Configuration{Colors.ENDC}\n")
    print("  Run this on your Mac to get the hostname:")
    print(f"  {Colors.CYAN}echo \"$(scutil --get LocalHostName).local\"{Colors.ENDC}\n")
    
    current_broker = config.get('mqtt_broker') or get_current_broker()
    if current_broker:
        broker = input(f"  MQTT Broker [{current_broker}]: ").strip()
        if not broker:
            broker = current_broker
    else:
        broker = input(f"  MQTT Broker: ").strip()
        if not broker:
            broker = "localhost"
    
    config['mqtt_broker'] = broker
    update_config_file(broker)
    update_dashboard_config(broker)
    print_status(f"MQTT Broker set to: {broker}", "success")
    
    # 2. Spotify Setup
    spotify_creds = setup_spotify()
    if spotify_creds:
        client_id, client_secret, refresh_token = spotify_creds
        update_spotify_config(client_id, client_secret, refresh_token)
        config['spotify_configured'] = True
    else:
        config['spotify_configured'] = False
    
    # 3. Save Pi paths (hardcoded defaults)
    config['pi1_host'] = PI1_SSH_HOST
    config['pi1_path'] = PI1_SCRIPT_PATH
    config['pi2_host'] = PI2_SSH_HOST
    config['pi2_path'] = PI2_SCRIPT_PATH
    
    # 4. Save config
    save_config(config)
    
    if not config.get('spotify_configured'):
        print(f"\n{Colors.RED}━━━ Setup Incomplete ━━━{Colors.ENDC}\n")
        print_status("Spotify is required for AirWave to function", "error")
        print(f"  Run {Colors.CYAN}python3 launcher.py --setup{Colors.ENDC} to try again.\n")
    else:
        print(f"\n{Colors.GREEN}━━━ Setup Complete! ━━━{Colors.ENDC}\n")
        print_status("Configuration saved", "success")
        print_status(f"Pi1 script: {PI1_SCRIPT_PATH}", "info")
        print_status(f"Pi2 script: {PI2_SCRIPT_PATH}", "info")
        
        # Important: Bluetooth pairing instructions
        print(f"\n{Colors.BOLD}📱 IMPORTANT: Pair Your Phone with Pi 2{Colors.ENDC}")
        print(f"  {Colors.CYAN}1.{Colors.ENDC} Open Bluetooth settings on your phone")
        print(f"  {Colors.CYAN}2.{Colors.ENDC} Look for {Colors.YELLOW}\"PiSpeaker\"{Colors.ENDC}")
        print(f"  {Colors.CYAN}3.{Colors.ENDC} Tap to connect")
        print(f"  {Colors.GREEN}→{Colors.ENDC} This is where your music will play!")
        print()
    
    return config


# =============================================================================
# PROCESS MANAGEMENT (same as before)
# =============================================================================

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.running = True
    
    def start_local_process(self, name, cmd, cwd=None):
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=cwd
            )
            self.processes[name] = {'process': process, 'type': 'local'}
            print_status(f"{name} started (PID: {process.pid})", "running")
            return process
        except Exception as e:
            print_status(f"Failed to start {name}: {e}", "error")
            return None
    
    def start_ssh_process(self, name, host, user, remote_cmd, mqtt_broker=None, password=None):
        try:
            debug(f"Starting SSH process: {name}")
            debug(f"  Host: {host}")
            debug(f"  User: {user}")
            debug(f"  Remote command: {remote_cmd}")
            debug(f"  MQTT broker: {mqtt_broker}")
            debug(f"  Using password: {bool(password)}")
            
            env_prefix = f"MQTT_BROKER={mqtt_broker} " if mqtt_broker else ""
            
            # Build SSH command with password if provided
            if password:
                # Use sshpass for password authentication
                ssh_cmd = [
                    "sshpass", "-p", password,
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "ServerAliveInterval=30",
                    "-tt",
                    f"{user}@{host}",
                    f"{env_prefix}python3 {remote_cmd}"
                ]
                debug(f"  Using password authentication")
            else:
                # Use regular SSH (assumes SSH keys are set up)
                ssh_cmd = [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "ServerAliveInterval=30",
                    "-tt",
                    f"{user}@{host}",
                    f"{env_prefix}python3 {remote_cmd}"
                ]
                debug(f"  Using SSH key authentication")
            
            # Obscure password in debug output
            debug_cmd = [c if c != password else "***" for c in ssh_cmd]
            debug(f"  SSH command: {' '.join(debug_cmd)}")
            
            process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.processes[name] = {'process': process, 'type': 'ssh', 'host': host, 'user': user}
            debug(f"  Process started with PID: {process.pid}")
            print_status(f"{name} started via SSH on {user}@{host} (PID: {process.pid})", "running")
            return process
        except FileNotFoundError as e:
            debug(f"  FileNotFoundError: {e}")
            if "sshpass" in str(e):
                print_status(f"sshpass not found. Install it with: brew install hudochenkov/sshpass/sshpass", "error")
            else:
                print_status(f"Failed to start {name}: {e}", "error")
            return None
        except Exception as e:
            debug(f"  Exception starting SSH process: {e}")
            print_status(f"Failed to start {name}: {e}", "error")
            return None
    
    def stop_all(self):
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
            
            if not self.processes:
                print_status("All processes have exited", "info")
                break

# =============================================================================
# MAIN
# =============================================================================

def prompt_mqtt_broker():
    config = load_config()
    current_broker = config.get('mqtt_broker') or get_current_broker()
    
    print(f"\n{Colors.BOLD}━━━ Quick Start ━━━{Colors.ENDC}\n")
    
    if current_broker:
        print(f"  Current MQTT Broker: {Colors.CYAN}{current_broker}{Colors.ENDC}")
        print(f"\n  Press Enter to continue, or type:")
        print(f"  • {Colors.CYAN}'setup'{Colors.ENDC} for complete re-setup")
        print(f"  • {Colors.CYAN}new hostname{Colors.ENDC} to change MQTT broker\n")
        
        response = input(f"  [{Colors.GREEN}Enter to continue{Colors.ENDC}]: ").strip()
        
        if response.lower() == 'setup':
            return None, run_onboarding()  # Trigger full setup
        elif response:
            broker = response
        else:
            broker = current_broker
    else:
        print(f"  {Colors.GREEN}Run: echo \"$(scutil --get LocalHostName).local\" on your Mac{Colors.ENDC}\n")
        broker = input(f"  MQTT Broker: ").strip()
        if not broker:
            broker = "localhost"
    
    config['mqtt_broker'] = broker
    save_config(config)
    update_config_file(broker)
    update_dashboard_config(broker)
    os.environ['MQTT_BROKER'] = broker
    
    print_status(f"Using MQTT Broker: {Colors.CYAN}{broker}{Colors.ENDC}", "success")
    
    return broker, config

# =============================================================================
# DEPENDENCY CHECKER
# =============================================================================

def check_and_install_dependencies():
    """Check for all required dependencies and install missing ones automatically."""
    
    print(f"\n{Colors.BOLD}━━━ Checking Dependencies ━━━{Colors.ENDC}\n")
    
    all_good = True
    
    # ── Python packages ──────────────────────────────────────────────────────
    python_packages = [
        ("requests",   "requests"),
        ("paho.mqtt",  "paho-mqtt"),
        ("urllib3",    "urllib3"),
        ("pyaudio",    "pyaudio"),
    ]
    
    for import_name, pip_name in python_packages:
        try:
            __import__(import_name)
            print_status(f"{pip_name}", "success")
        except ImportError:
            print_status(f"{pip_name} not found — installing...", "warning")
            # pyaudio requires portaudio to be installed first via brew
            if pip_name == "pyaudio":
                portaudio_ok = subprocess.run(
                    ["brew", "list", "portaudio"], capture_output=True
                ).returncode == 0
                if not portaudio_ok:
                    print_status("Installing portaudio (required for pyaudio)...", "info")
                    brew_result = subprocess.run(
                        ["brew", "install", "portaudio"],
                        capture_output=True, text=True
                    )
                    if brew_result.returncode != 0:
                        print_status("Failed to install portaudio. Run: brew install portaudio", "error")
                        all_good = False
                        continue
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pip_name],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print_status(f"{pip_name} installed successfully", "success")
            else:
                print_status(f"Failed to install {pip_name}. Run: pip3 install {pip_name}", "error")
                all_good = False
    
    # ── Homebrew tools ───────────────────────────────────────────────────────
    
    # Check Homebrew itself first
    brew_available = subprocess.run(
        ["which", "brew"], capture_output=True
    ).returncode == 0
    
    if not brew_available:
        print_status("Homebrew not found — required to install system tools", "error")
        print(f"\n  Install Homebrew first:")
        print(f"  {Colors.CYAN}/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"{Colors.ENDC}\n")
        print(f"  Then re-run: {Colors.CYAN}python3 launcher.py{Colors.ENDC}\n")
        sys.exit(1)
    
    # mosquitto
    mosquitto_ok = (
        subprocess.run(["which", "mosquitto"], capture_output=True).returncode == 0
        or Path("/opt/homebrew/sbin/mosquitto").exists()   # Apple Silicon
        or Path("/usr/local/sbin/mosquitto").exists()      # Intel Mac
    )
    
    if mosquitto_ok:
        print_status("mosquitto", "success")
    else:
        print_status("mosquitto not found — installing...", "warning")
        result = subprocess.run(["brew", "install", "mosquitto"], capture_output=True, text=True)
        if result.returncode == 0:
            print_status("mosquitto installed successfully", "success")
        else:
            print_status("Failed to install mosquitto. Run: brew install mosquitto", "error")
            all_good = False
    
    # sshpass
    sshpass_ok = subprocess.run(
        ["which", "sshpass"], capture_output=True
    ).returncode == 0
    
    if sshpass_ok:
        print_status("sshpass", "success")
    else:
        print_status("sshpass not found — installing...", "warning")
        result = subprocess.run(
            ["brew", "install", "hudochenkov/sshpass/sshpass"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print_status("sshpass installed successfully", "success")
        else:
            print_status("Failed to install sshpass. Run: brew install hudochenkov/sshpass/sshpass", "error")
            all_good = False
    
    # ── Summary ──────────────────────────────────────────────────────────────
    if all_good:
        print(f"\n  {Colors.GREEN}All dependencies satisfied!{Colors.ENDC}\n")
    else:
        print(f"\n  {Colors.RED}Some dependencies could not be installed automatically.{Colors.ENDC}")
        print(f"  Please install them manually and re-run launcher.py\n")
        sys.exit(1)


def sync_files_to_pis():
    """Sync necessary files from Mac to Pis before starting agents."""
    print(f"\n{Colors.BOLD}━━━ Syncing Files to Pis ━━━{Colors.ENDC}\n")
    
    debug("Starting file sync to Pis")
    debug(f"Mac script directory: {SCRIPT_DIR}")
    
    files_to_sync = [
        ("pi1_agent.py", PI1_SSH_HOST, "~/FinalVersion/Team6/ConnectingPi/"),
        ("config.py", PI1_SSH_HOST, "~/FinalVersion/Team6/ConnectingPi/"),
        ("spotify_controller.py", PI1_SSH_HOST, "~/FinalVersion/Team6/ConnectingPi/"),
        ("pi2_agent.py", PI2_SSH_HOST, "~/FinalVersion/Team6/ConnectingPi/"),
        ("config.py", PI2_SSH_HOST, "~/FinalVersion/Team6/ConnectingPi/"),
        ("spotify_controller.py", PI2_SSH_HOST, "~/FinalVersion/Team6/ConnectingPi/"),
    ]
    
    debug(f"Files to sync: {len(files_to_sync)} files")
    
    all_synced = True
    
    for filename, host, remote_path in files_to_sync:
        local_file = SCRIPT_DIR / filename
        
        debug(f"Syncing {filename} to {host}:{remote_path}")
        debug(f"  Local file: {local_file}")
        debug(f"  Exists: {local_file.exists()}")
        
        if not local_file.exists():
            print_status(f"{filename} not found locally — skipping", "warning")
            debug(f"  File not found, skipping")
            continue
        
        # Use scp to copy file
        if PI1_PASSWORD and host == PI1_SSH_HOST:
            cmd = ["sshpass", "-p", PI1_PASSWORD, "scp", str(local_file), f"{PI_SSH_USER}@{host}:{remote_path}"]
            debug(f"  Using Pi1 password authentication")
        elif PI2_PASSWORD and host == PI2_SSH_HOST:
            cmd = ["sshpass", "-p", PI2_PASSWORD, "scp", str(local_file), f"{PI_SSH_USER}@{host}:{remote_path}"]
            debug(f"  Using Pi2 password authentication")
        else:
            cmd = ["scp", str(local_file), f"{PI_SSH_USER}@{host}:{remote_path}"]
            debug(f"  Using SSH key authentication")
        
        # Obscure password in debug output
        debug_cmd = [c if c != PI1_PASSWORD and c != PI2_PASSWORD else "***" for c in cmd]
        debug(f"  Command: {' '.join(debug_cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            debug(f"  Return code: {result.returncode}")
            if result.returncode == 0:
                debug(f"  ✓ Successfully synced {filename} to {host}")
            else:
                debug(f"  ✗ Failed to sync {filename}")
                debug(f"  stdout: {result.stdout}")
                debug(f"  stderr: {result.stderr}")
                print_status(f"Failed to sync {filename} to {host}", "error")
                all_synced = False
        except subprocess.TimeoutExpired:
            debug(f"  ✗ Timeout syncing {filename} to {host}")
            print_status(f"Timeout syncing {filename} to {host}", "error")
            all_synced = False
        except Exception as e:
            debug(f"  ✗ Exception: {e}")
            print_status(f"Error syncing {filename} to {host}: {e}", "error")
            all_synced = False
    
    if all_synced:
        print_status("All files synced to Pis", "success")
        debug("File sync completed successfully")
    else:
        print_status("Some files failed to sync — Pis may have outdated code", "warning")
        debug("File sync completed with errors")
    
    print()




def configure_mosquitto():
    """Ensure mosquitto.conf has the required configuration for AirWave."""
    # Detect config path
    if Path("/opt/homebrew/etc/mosquitto/mosquitto.conf").exists():
        config_path = Path("/opt/homebrew/etc/mosquitto/mosquitto.conf")
    elif Path("/usr/local/etc/mosquitto/mosquitto.conf").exists():
        config_path = Path("/usr/local/etc/mosquitto/mosquitto.conf")
    else:
        return False, "Config file not found"
    
    # Required configuration
    required_config = """listener 1883
protocol mqtt
allow_anonymous true

listener 9001
protocol websockets
allow_anonymous true
"""
    
    try:
        # Read existing config
        existing_config = config_path.read_text()
        
        # Check if required settings are present
        has_1883 = "listener 1883" in existing_config
        has_9001 = "listener 9001" in existing_config
        has_websockets = "protocol websockets" in existing_config
        has_anonymous = "allow_anonymous true" in existing_config
        
        if has_1883 and has_9001 and has_websockets and has_anonymous:
            return True, "Already configured"
        
        # Need to update config
        print_status("Mosquitto config needs updating for WebSocket support", "warning")
        print(f"  Current config at: {config_path}")
        
        # Backup existing config
        backup_path = config_path.with_suffix('.conf.backup')
        if not backup_path.exists():
            config_path.write_text(existing_config)  # Write to backup
            import shutil
            shutil.copy(config_path, backup_path)
            print_status(f"Backed up existing config to {backup_path}", "info")
        
        # Write new config
        config_path.write_text(required_config)
        print_status("Updated mosquitto.conf with WebSocket support", "success")
        return True, "Updated"
        
    except PermissionError:
        return False, "Permission denied - run: sudo chmod 644 " + str(config_path)
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="AirWave Launcher")
    parser.add_argument('--setup', action='store_true', help='Run onboarding setup only')
    parser.add_argument('--dashboard', action='store_true', help='Run dashboard only')
    parser.add_argument('--pi1', action='store_true', help='Run pi1_agent only')
    parser.add_argument('--pi2', action='store_true', help='Run pi2_agent only')
    parser.add_argument('--local', action='store_true', help='Run agents locally (no SSH)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    # Enable debug mode if --debug flag is set
    if args.debug:
        global DEBUG
        DEBUG = True
        debug("Debug mode enabled via --debug flag")
    
    if DEBUG:
        debug("=== AirWave Launcher Starting ===")
        debug(f"Python version: {sys.version}")
        debug(f"Script directory: {SCRIPT_DIR}")
        debug(f"Arguments: {vars(args)}")
        debug(f"Environment variables:")
        for key in ['AIRWAVE_DEBUG', 'MQTT_BROKER', 'HOME', 'USER']:
            debug(f"  {key} = {os.environ.get(key, 'not set')}")
    
    print_banner()
    
    # Check and install dependencies before anything else
    check_and_install_dependencies()
    
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
        debug("First run detected - no config file found")
        print(f"  {Colors.YELLOW}First time setup detected!{Colors.ENDC}")
        config = run_onboarding()
        debug("Onboarding completed", config)
    else:
        debug("Existing installation detected")
        mqtt_broker, config = prompt_mqtt_broker()
        debug(f"MQTT broker prompt result: {mqtt_broker}")
        # If user typed 'setup', config will be from run_onboarding()
        if mqtt_broker is None:
            debug("User requested full setup")
            # Full setup was run, mqtt_broker already set in config
            mqtt_broker = config.get('mqtt_broker', 'localhost')
            debug(f"Using MQTT broker from config: {mqtt_broker}")
    
    debug("Current configuration:", config)
    
    # Ensure dashboard config exists
    if not DASHBOARD_CONFIG.exists():
        broker = config.get('mqtt_broker') or get_current_broker() or "localhost"
        update_dashboard_config(broker)
    
    # Set up process manager
    manager = ProcessManager()
    
    def signal_handler(sig, frame):
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Sync files to Pis before starting (only if running Pi agents)
    if run_pi1 or run_pi2:
        sync_files_to_pis()
    
    print(f"\n{Colors.BOLD}━━━ Starting Services ━━━{Colors.ENDC}\n")
    
    mqtt_broker = config.get('mqtt_broker', 'localhost')
    
    # Configure and start Mosquitto MQTT broker first
    print_status("Configuring Mosquitto MQTT broker...", "info")
    
    # Check/update mosquitto config
    config_ok, config_msg = configure_mosquitto()
    if not config_ok:
        print_status(f"Could not configure mosquitto: {config_msg}", "warning")
        print_status("Dashboard may not connect properly", "warning")
    
    print_status("Starting Mosquitto MQTT broker...", "info")
    try:
        # Check if mosquitto is already running
        check_running = subprocess.run(
            ["pgrep", "-x", "mosquitto"],
            capture_output=True
        )
        
        if check_running.returncode == 0:
            print_status("Mosquitto already running", "success")
        else:
            # Detect correct mosquitto config path for Apple Silicon vs Intel
            if Path("/opt/homebrew/etc/mosquitto/mosquitto.conf").exists():
                config_path = "/opt/homebrew/etc/mosquitto/mosquitto.conf"  # Apple Silicon
            elif Path("/usr/local/etc/mosquitto/mosquitto.conf").exists():
                config_path = "/usr/local/etc/mosquitto/mosquitto.conf"  # Intel Mac
            else:
                # Fallback: try to start without config file
                config_path = None
            
            # Start mosquitto
            if config_path:
                mosquitto_process = subprocess.Popen(
                    ["mosquitto", "-c", config_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                # Start with default config
                mosquitto_process = subprocess.Popen(
                    ["mosquitto"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            time.sleep(1)  # Give it a moment to start
            
            # Verify it started
            verify = subprocess.run(["pgrep", "-x", "mosquitto"], capture_output=True)
            if verify.returncode == 0:
                print_status("Mosquitto started successfully", "success")
                manager.processes["Mosquitto"] = {'process': mosquitto_process, 'type': 'local'}
            else:
                print_status("Mosquitto may not have started correctly", "warning")
    except FileNotFoundError:
        print_status("mosquitto not found. Install with: brew install mosquitto", "error")
        print_status("Or start manually: brew services start mosquitto", "warning")
    except Exception as e:
        print_status(f"Could not start mosquitto: {e}", "warning")
        print_status("Try running manually: brew services start mosquitto", "info")
    
    # Start dashboard
    if run_dashboard:
        manager.start_local_process(
            "Dashboard",
            ["python3", "-m", "http.server", "8080"],
            cwd=DASHBOARD_DIR
        )
        print_status(f"Dashboard: {Colors.CYAN}http://localhost:8080{Colors.ENDC}", "info")
        
        # Open browser automatically after a short delay
        def open_browser():
            time.sleep(2)  # Wait for server to be ready
            try:
                webbrowser.open("http://localhost:8080")
                print_status("Opened dashboard in browser", "success")
            except Exception:
                pass
        
        threading.Thread(target=open_browser, daemon=True).start()
    
    # Start pi1_agent
    if run_pi1:
        if args.local:
            pi1_script = SCRIPT_DIR / "pi1_agent.py"
            if pi1_script.exists():
                manager.start_local_process("Pi1 Agent", ["python3", str(pi1_script)])
            else:
                print_status("pi1_agent.py not found locally", "warning")
        else:
            # Use hardcoded path and password
            manager.start_ssh_process("Pi1 Agent", PI1_SSH_HOST, PI_SSH_USER, PI1_SCRIPT_PATH, mqtt_broker, PI1_PASSWORD)
    
    # Start pi2_agent
    if run_pi2:
        if args.local:
            pi2_script = SCRIPT_DIR / "pi2_agent.py"
            if pi2_script.exists():
                manager.start_local_process("Pi2 Agent", ["python3", str(pi2_script)])
            else:
                print_status("pi2_agent.py not found locally", "warning")
        else:
            # Use hardcoded path and password
            manager.start_ssh_process("Pi2 Agent", PI2_SSH_HOST, PI_SSH_USER, PI2_SCRIPT_PATH, mqtt_broker, PI2_PASSWORD)
    
    print(f"\n{Colors.BOLD}━━━ Running ━━━{Colors.ENDC}")
    print(f"  Press {Colors.YELLOW}Ctrl+C{Colors.ENDC} to stop\n")
    
    try:
        manager.monitor_output()
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()

if __name__ == "__main__":
    main()