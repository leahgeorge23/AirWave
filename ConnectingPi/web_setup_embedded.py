#!/usr/bin/env python3
"""
web_setup_embedded.py - Embedded web setup for AirWave
Place this file in the same directory as launcher.py
"""

import json
import webbrowser
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# HTML for setup page
SETUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌊 AirWave Setup</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #00d9ff 0%, #0099cc 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
            padding: 40px;
        }
        h1 { text-align: center; color: #333; margin-bottom: 10px; font-size: 2.5rem; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 1.1rem; }
        .step {
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 12px;
            border-left: 4px solid #00d9ff;
        }
        .step-number {
            display: inline-block;
            background: #00d9ff;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            text-align: center;
            line-height: 30px;
            font-weight: bold;
            margin-right: 10px;
        }
        .step-title { font-size: 1.2rem; font-weight: 600; color: #333; margin-bottom: 15px; }
        .help-text {
            background: #e3f2fd;
            padding: 12px;
            border-radius: 8px;
            font-size: 0.9rem;
            margin-bottom: 15px;
            color: #1976d2;
            font-family: 'Courier New', monospace;
        }
        label { display: block; font-weight: 500; margin-bottom: 8px; color: #555; }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #00d9ff;
        }
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 15px;
        }
        input[type="checkbox"] { width: 20px; height: 20px; cursor: pointer; }
        .spotify-fields {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 2px dashed #ddd;
        }
        .submit-btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #00d9ff, #0099cc);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.2rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-top: 20px;
        }
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 217, 255, 0.4);
        }
        .submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .success-message {
            display: none;
            background: #4caf50;
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            font-size: 1.1rem;
            margin-top: 20px;
        }
        .error { color: #f44336; font-size: 0.9rem; margin-top: 5px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌊 AirWave</h1>
        <p class="subtitle">Welcome! Let's get you set up in 2 minutes.</p>
        
        <form id="setupForm">
            <div class="step">
                <div class="step-title">
                    <span class="step-number">1</span>
                    MQTT Broker Configuration
                </div>
                <div class="help-text">
                    On your Mac, run: echo "$(scutil --get LocalHostName).local"
                </div>
                <label for="mqttBroker">MQTT Broker Address:</label>
                <input type="text" id="mqttBroker" name="mqttBroker" 
                       placeholder="e.g., Leahs-MacBook-Pro.local" required>
                <div class="error" id="mqttError">Please enter your Mac's hostname</div>
            </div>
            
            <div class="step">
                <div class="step-title">
                    <span class="step-number">2</span>
                    Spotify Configuration (Required)
                </div>
                <div class="help-text">
                    1. Go to: developer.spotify.com/dashboard<br>
                    2. Create app with redirect URI: http://127.0.0.1:8888/callback<br>
                    3. Copy your Client ID and Client Secret below<br>
                    <br>
                    <strong>Note:</strong> Spotify Premium is required for AirWave to work.
                </div>
                <label for="spotifyClientId">Spotify Client ID:</label>
                <input type="text" id="spotifyClientId" name="spotifyClientId" 
                       placeholder="Your Spotify Client ID" required>
                <label for="spotifyClientSecret" style="margin-top: 15px;">Spotify Client Secret:</label>
                <input type="password" id="spotifyClientSecret" name="spotifyClientSecret" 
                       placeholder="Your Spotify Client Secret" required>
                <div class="error" id="spotifyError">
                    Please fill in both Spotify credentials
                </div>
            </div>
            
            <div class="step">
                <div class="step-title">
                    <span class="step-number">3</span>
                    Connect Your Phone to Pi 2
                </div>
                <div class="help-text">
                    📱 <strong>IMPORTANT:</strong> After clicking "Start AirWave" below, pair your phone:<br><br>
                    1. Open Bluetooth settings on your phone<br>
                    2. Look for <strong>"PiSpeaker"</strong><br>
                    3. Tap to connect<br>
                    4. This is where your music will play!
                </div>
            </div>
            
            <button type="submit" class="submit-btn" id="submitBtn">🚀 Start AirWave</button>
            <div class="success-message" id="successMessage">
                ✓ Setup complete! AirWave is starting...<br>
                <small>You can close this window.</small>
            </div>
        </form>
    </div>
    
    <script>
        const setupForm = document.getElementById('setupForm');
        const submitBtn = document.getElementById('submitBtn');
        const successMessage = document.getElementById('successMessage');
        
        // Form submission
        setupForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Clear errors
            document.querySelectorAll('.error').forEach(el => el.style.display = 'none');
            
            // Validate MQTT broker
            const mqttBroker = document.getElementById('mqttBroker').value.trim();
            if (!mqttBroker) {
                document.getElementById('mqttError').style.display = 'block';
                return;
            }
            
            // Validate Spotify (always required)
            const clientId = document.getElementById('spotifyClientId').value.trim();
            const clientSecret = document.getElementById('spotifyClientSecret').value.trim();
            
            if (!clientId || !clientSecret) {
                document.getElementById('spotifyError').style.display = 'block';
                return;
            }
            
            // Disable form and show loading
            submitBtn.disabled = true;
            submitBtn.textContent = 'Setting up...';
            
            // Collect form data
            const formData = {
                mqtt_broker: mqttBroker,
                enable_spotify: true,  // Always enabled
                spotify_client_id: clientId,
                spotify_client_secret: clientSecret
            };
            
            // Send to server
            try {
                const response = await fetch('/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                
                if (response.ok) {
                    successMessage.style.display = 'block';
                    setupForm.style.display = 'none';
                    setTimeout(() => window.close(), 3000);
                } else {
                    alert('Setup failed. Please try again.');
                    submitBtn.disabled = false;
                    submitBtn.textContent = '🚀 Start AirWave';
                }
            } catch (error) {
                alert('Error: ' + error.message);
                submitBtn.disabled = false;
                submitBtn.textContent = '🚀 Start AirWave';
            }
        });
    </script>
</body>
</html>"""

class SetupHandler(BaseHTTPRequestHandler):
    config_data = None
    server_should_stop = False
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(SETUP_HTML.encode())
    
    def do_POST(self):
        if self.path == '/submit':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                SetupHandler.config_data = json.loads(post_data.decode())
                SetupHandler.server_should_stop = True
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())


def run_web_setup():
    """Run web setup and return config dict."""
    print("🌐 Opening web setup interface...")
    
    # Try to find an available port, starting with 8765
    port = 8765
    max_attempts = 10
    server = None
    
    for attempt in range(max_attempts):
        try:
            server = HTTPServer(('localhost', port), SetupHandler)
            break  # Success!
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"   Port {port} in use, trying {port + 1}...")
                port += 1
            else:
                raise
    
    if server is None:
        print("✗ Could not find an available port for setup interface")
        return None
    
    def open_browser():
        time.sleep(1)
        webbrowser.open(f'http://localhost:{port}')
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    print(f"📝 Complete setup in your browser at: http://localhost:{port}")
    print("   (Should open automatically)\n")
    
    try:
        while not SetupHandler.server_should_stop:
            server.handle_request()
    except KeyboardInterrupt:
        print("\n⚠ Setup cancelled by user")
    finally:
        server.server_close()
    
    if SetupHandler.config_data:
        print("✓ Setup data received!")
        return SetupHandler.config_data
    else:
        return None