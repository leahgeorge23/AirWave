#!/usr/bin/env python

import time
import pantilthat
import threading
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

try:
    import cv2
except ImportError:
    print("OpenCV not found. Install with: sudo apt install python3-opencv")
    exit(1)

current_frame = None
frame_lock = threading.Lock()

INVERT_PAN = False
INVERT_TILT = False


class PID:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0
        self.integral = 0
    
    def update(self, error, dt):
        self.integral += error * dt
        self.integral = max(-30, min(30, self.integral))
        derivative = (error - self.prev_error) / dt if dt > 0 else 0
        self.prev_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative


class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
                <html>
                <head><title>Wallet Tracking</title></head>
                <body style="margin:0; background:#000; display:flex; justify-content:center; align-items:center; height:100vh;">
                    <img src="/stream" style="max-width:100%; max-height:100%;">
                </body>
                </html>
            ''')
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            while True:
                try:
                    with frame_lock:
                        if current_frame is not None:
                            ret, jpeg = cv2.imencode('.jpg', current_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                            if ret:
                                self.wfile.write(b'--frame\r\n')
                                self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                                self.wfile.write(jpeg.tobytes())
                                self.wfile.write(b'\r\n')
                    time.sleep(0.03)
                except:
                    break
    
    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def start_server(port=8080):
    server = ThreadedHTTPServer(('0.0.0.0', port), StreamHandler)
    server.serve_forever()


class BlackObjectTracker:
    def __init__(self, frame_width, frame_height):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.smooth_x = frame_width // 2
        self.smooth_y = frame_height // 2
        self.alpha = 0.15  # Lower = smoother
        self.last_bbox = None
    
    def track(self, frame):
        # Convert to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Black color range (low value, any hue/saturation)
        lower_black = np.array([0, 0, 0], dtype=np.uint8)
        upper_black = np.array([180, 255, 50], dtype=np.uint8)
        
        mask = cv2.inRange(hsv, lower_black, upper_black)
        
        # Clean up mask
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=3)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        
        # Find contours
        result = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(result) == 3:
            _, contours, _ = result
        else:
            contours, _ = result
        
        if not contours:
            return None
        
        # Filter by size and shape (wallet-like aspect ratio)
        valid_contours = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 800 or area > 50000:
                continue
            
            x, y, w, h = cv2.boundingRect(c)
            aspect = float(w) / h if h > 0 else 0
            
            # Wallet is roughly rectangular, wider than tall or square-ish
            if 0.3 < aspect < 3.0:
                valid_contours.append((c, area))
        
        if not valid_contours:
            return None
        
        # Get largest valid contour
        largest = max(valid_contours, key=lambda x: x[1])[0]
        x, y, w, h = cv2.boundingRect(largest)
        cx = x + w // 2
        cy = y + h // 2
        
        # Extra smooth position with exponential moving average
        self.smooth_x = self.alpha * cx + (1 - self.alpha) * self.smooth_x
        self.smooth_y = self.alpha * cy + (1 - self.alpha) * self.smooth_y
        
        self.last_bbox = (x, y, w, h)
        
        return {
            'bbox': (x, y, w, h),
            'center': (int(self.smooth_x), int(self.smooth_y))
        }


def main():
    global current_frame
    
    pan_angle = 0
    tilt_angle = 0
    pantilthat.pan(pan_angle)
    pantilthat.tilt(tilt_angle)
    
    # Very smooth PID values
    pan_pid = PID(kp=0.04, ki=0.002, kd=0.015)
    tilt_pid = PID(kp=0.04, ki=0.002, kd=0.015)
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    if not cap.isOpened():
        print("Error: Could not open camera")
        return
    
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    center_x = frame_width // 2
    center_y = frame_height // 2
    
    dead_zone = 8
    
    server_thread = threading.Thread(target=start_server, args=(8080,))
    server_thread.daemon = True
    server_thread.start()
    
    tracker = BlackObjectTracker(frame_width, frame_height)
    
    print(f"Camera resolution: {frame_width}x{frame_height}")
    print("="*50)
    print("BLACK WALLET TRACKING")
    print("View at: http://raspberrypi.local:8080")
    print("="*50)
    print("Press Ctrl+C to quit.")
    
    last_time = time.time()
    
    # For extra smoothing on servo output
    smooth_pan = 0
    smooth_tilt = 0
    servo_alpha = 0.3
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            result = tracker.track(frame)
            
            if result:
                x, y, w, h = result['bbox']
                obj_x, obj_y = result['center']
                
                # Calculate error
                if INVERT_PAN:
                    error_x = obj_x - center_x
                else:
                    error_x = center_x - obj_x
                
                if INVERT_TILT:
                    error_y = center_y - obj_y
                else:
                    error_y = obj_y - center_y
                
                # Update angles with PID
                if abs(error_x) > dead_zone:
                    pan_angle += pan_pid.update(error_x, dt)
                    pan_angle = max(-90, min(90, pan_angle))
                
                if abs(error_y) > dead_zone:
                    tilt_angle += tilt_pid.update(error_y, dt)
                    tilt_angle = max(-90, min(90, tilt_angle))
                
                # Extra smoothing on servo output
                smooth_pan = servo_alpha * pan_angle + (1 - servo_alpha) * smooth_pan
                smooth_tilt = servo_alpha * tilt_angle + (1 - servo_alpha) * smooth_tilt
                
                pantilthat.pan(int(smooth_pan))
                pantilthat.tilt(int(smooth_tilt))
                
                # Draw tracking
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(frame, (obj_x, obj_y), 5, (0, 255, 0), -1)
                cv2.putText(frame, "WALLET", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            else:
                cv2.putText(frame, "NO WALLET", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            # Draw center
            cv2.line(frame, (center_x - 15, center_y), (center_x + 15, center_y), (0, 0, 255), 1)
            cv2.line(frame, (center_x, center_y - 15), (center_x, center_y + 15), (0, 0, 255), 1)
            
            cv2.putText(frame, f"P:{int(smooth_pan)} T:{int(smooth_tilt)}", 
                       (5, frame_height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
            with frame_lock:
                current_frame = frame.copy()
            
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cap.release()
        pantilthat.pan(0)
        pantilthat.tilt(0)
        print("Done.")


if __name__ == "__main__":
    main()
