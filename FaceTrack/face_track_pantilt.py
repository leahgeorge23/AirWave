#!/usr/bin/env python3
"""
Face Tracking with Pimoroni Pan-Tilt HAT
Tracks faces using OpenCV and keeps them centered using pan/tilt servos.

Based on the original face-track-demo by Claude Pageau, rewritten
for the Pimoroni Pan-Tilt HAT with pantilthat library.
"""

import os
import time
import threading
import cv2
import numpy as np

# Try to import picamera (legacy) first, then picamera2
PICAMERA_VERSION = None
try:
    from picamera2 import Picamera2
    PICAMERA_VERSION = 2
    print("Found: picamera2")
except ImportError:
    pass

if PICAMERA_VERSION is None:
    try:
        from picamera import PiCamera
        from picamera.array import PiRGBArray
        PICAMERA_VERSION = 1
        print("Found: picamera (legacy)")
    except ImportError:
        pass

if PICAMERA_VERSION is None:
    print("Note: No picamera library found, will try OpenCV camera")

try:
    import pantilthat
    PANTILT_AVAILABLE = True
    print("Found: pantilthat")
except ImportError:
    PANTILT_AVAILABLE = False
    print("Warning: pantilthat not installed. Run: pip3 install pantilthat")

# =============================================================================
# Configuration
# =============================================================================

# Camera settings
CAMERA_WIDTH = 320   # Lower resolution for better FPS
CAMERA_HEIGHT = 240
CAMERA_FRAMERATE = 30
CAMERA_HFLIP = False
CAMERA_VFLIP = False

# Pan/Tilt settings (servo range is typically -90 to +90)
PAN_MIN = -90
PAN_MAX = 90
TILT_MIN = -90
TILT_MAX = 90
PAN_START = 0
TILT_START = 0

# Tracking settings
# Base gain - how aggressively to move toward the face
PAN_GAIN = 0.5
TILT_GAIN = 0.5

# Edge boost - extra gain when face is near edge of frame
# This makes tracking more aggressive as face approaches edges
EDGE_ZONE = 0.3  # Outer 30% of frame is considered "edge zone"
EDGE_BOOST = 2.0  # Multiply gain by this when in edge zone

# Dead zone - don't move if face is within this many pixels of center
DEAD_ZONE_X = 8
DEAD_ZONE_Y = 8

# Maximum movement per frame (degrees) - prevents jerky motion
MAX_PAN_STEP = 15
MAX_TILT_STEP = 15

# Face detection settings - try multiple possible locations
FACE_CASCADE_PATHS = [
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
    "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
    "/usr/local/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    "/usr/share/OpenCV/haarcascades/haarcascade_frontalface_default.xml",
]

# Display settings
SHOW_WINDOW = False  # Set to False for headless/SSH operation
WINDOW_SCALE = 1.0   # Scale factor for display window

# Timing
FPS_DISPLAY_INTERVAL = 2.0  # Seconds between FPS updates

# Search pattern settings
SEARCH_TIMEOUT = 3.0  # Seconds without face before starting search
SEARCH_PAN_SPEED = 3  # Degrees per frame for pan search
SEARCH_TILT_SPEED = 2 # Degrees per frame for tilt search

# Debug
DEBUG = True

# =============================================================================
# Camera Classes
# =============================================================================

class PiCamera2Stream:
    """Video stream using picamera2 library (Raspberry Pi OS Bullseye+)."""
    
    def __init__(self, resolution=(CAMERA_WIDTH, CAMERA_HEIGHT), framerate=CAMERA_FRAMERATE):
        self.camera = Picamera2()
        config = self.camera.create_preview_configuration(
            main={"size": resolution, "format": "RGB888"}
        )
        self.camera.configure(config)
        self.frame = None
        self.stopped = False
        
    def start(self):
        self.camera.start()
        time.sleep(1)  # Warm-up time
        threading.Thread(target=self._update, daemon=True).start()
        return self
        
    def _update(self):
        while not self.stopped:
            self.frame = self.camera.capture_array()
            
    def read(self):
        return self.frame
        
    def stop(self):
        self.stopped = True
        self.camera.stop()


class PiCameraLegacyStream:
    """Video stream using legacy picamera library (Raspberry Pi OS Buster and earlier)."""
    
    def __init__(self, resolution=(CAMERA_WIDTH, CAMERA_HEIGHT), framerate=CAMERA_FRAMERATE):
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.framerate = framerate
        self.camera.hflip = CAMERA_HFLIP
        self.camera.vflip = CAMERA_VFLIP
        self.rawCapture = PiRGBArray(self.camera, size=resolution)
        self.stream = self.camera.capture_continuous(
            self.rawCapture, format="bgr", use_video_port=True
        )
        self.frame = None
        self.stopped = False
        
    def start(self):
        threading.Thread(target=self._update, daemon=True).start()
        return self
        
    def _update(self):
        for f in self.stream:
            self.frame = f.array
            self.rawCapture.truncate(0)
            if self.stopped:
                self.stream.close()
                self.rawCapture.close()
                self.camera.close()
                return
                
    def read(self):
        return self.frame
        
    def stop(self):
        self.stopped = True


class OpenCVStream:
    """Video stream using OpenCV (fallback for USB cameras)."""
    
    def __init__(self, src=0, resolution=(CAMERA_WIDTH, CAMERA_HEIGHT)):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        self.stream.set(cv2.CAP_PROP_FPS, CAMERA_FRAMERATE)
        self.frame = None
        self.stopped = False
        
    def start(self):
        threading.Thread(target=self._update, daemon=True).start()
        return self
        
    def _update(self):
        while not self.stopped:
            ret, self.frame = self.stream.read()
            if not ret:
                time.sleep(0.1)
                
    def read(self):
        return self.frame
        
    def stop(self):
        self.stopped = True
        self.stream.release()


# =============================================================================
# Pan-Tilt Controller
# =============================================================================

class PanTiltController:
    """Controls the Pimoroni Pan-Tilt HAT servos."""
    
    def __init__(self):
        self.pan = PAN_START
        self.tilt = TILT_START
        self.enabled = PANTILT_AVAILABLE
        
        if self.enabled:
            # Initialize pantilthat
            pantilthat.servo_enable(1, True)
            pantilthat.servo_enable(2, True)
            self.goto(self.pan, self.tilt)
            
    def goto(self, pan, tilt):
        """Move to specified pan/tilt position."""
        # Clamp values to valid range
        self.pan = max(PAN_MIN, min(PAN_MAX, pan))
        self.tilt = max(TILT_MIN, min(TILT_MAX, tilt))
        
        if self.enabled:
            try:
                pantilthat.pan(int(self.pan))
                pantilthat.tilt(int(self.tilt))
            except Exception as e:
                if DEBUG:
                    print(f"Pan-tilt error: {e}")
                    
        return self.pan, self.tilt
        
    def move_relative(self, pan_delta, tilt_delta):
        """Move relative to current position."""
        return self.goto(self.pan + pan_delta, self.tilt + tilt_delta)
        
    def center(self):
        """Return to center position."""
        return self.goto(PAN_START, TILT_START)
        
    def get_position(self):
        """Get current position."""
        return self.pan, self.tilt
        
    def disable(self):
        """Disable servos."""
        if self.enabled:
            pantilthat.servo_enable(1, False)
            pantilthat.servo_enable(2, False)


# =============================================================================
# Face Detector
# =============================================================================

class FaceDetector:
    """Detects faces using OpenCV Haar cascades."""
    
    def __init__(self):
        self.face_cascade = None
        self._load_cascade()
        
    def _load_cascade(self):
        """Load the face detection cascade."""
        for path in FACE_CASCADE_PATHS:
            if os.path.exists(path):
                self.face_cascade = cv2.CascadeClassifier(path)
                if not self.face_cascade.empty():
                    if DEBUG:
                        print(f"Loaded face cascade from: {path}")
                    return
        
        # If we get here, try to find it anywhere
        import subprocess
        try:
            result = subprocess.run(
                ["find", "/usr", "-name", "haarcascade_frontalface_default.xml"],
                capture_output=True, text=True, timeout=10
            )
            paths = result.stdout.strip().split('\n')
            for path in paths:
                if path and os.path.exists(path):
                    self.face_cascade = cv2.CascadeClassifier(path)
                    if not self.face_cascade.empty():
                        if DEBUG:
                            print(f"Loaded face cascade from: {path}")
                        return
        except Exception:
            pass
                    
        print("Error: Could not load face cascade classifier!")
        print("Try: sudo apt-get install opencv-data")
        
    def detect(self, frame):
        """
        Detect faces in frame.
        Returns list of (x, y, w, h) tuples for each face found.
        """
        if self.face_cascade is None or self.face_cascade.empty():
            return []
            
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,  # Faster detection
            minNeighbors=3,   # Lower = more sensitive
            minSize=(20, 20),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        return faces
        
    def get_largest_face(self, faces):
        """Return the largest face from the list."""
        if len(faces) == 0:
            return None
            
        # Find face with largest area
        largest = max(faces, key=lambda f: f[2] * f[3])
        return largest


# =============================================================================
# Face Tracker
# =============================================================================

class FaceTracker:
    """Main face tracking controller."""
    
    def __init__(self):
        self.pan_tilt = PanTiltController()
        self.detector = FaceDetector()
        self.video_stream = None
        
        # Frame center (target position)
        self.center_x = CAMERA_WIDTH // 2
        self.center_y = CAMERA_HEIGHT // 2
        
        # Edge zone boundaries (where we boost tracking speed)
        self.edge_left = int(CAMERA_WIDTH * EDGE_ZONE)
        self.edge_right = int(CAMERA_WIDTH * (1 - EDGE_ZONE))
        self.edge_top = int(CAMERA_HEIGHT * EDGE_ZONE)
        self.edge_bottom = int(CAMERA_HEIGHT * (1 - EDGE_ZONE))
        
        # FPS tracking
        self.fps_start_time = time.time()
        self.fps_frame_count = 0
        self.current_fps = 0
        
        # State
        self.running = False
        self.last_face_time = 0
        self.search_mode = False
        self.search_pan_direction = 1
        self.search_tilt_direction = 1
        
    def start_camera(self):
        """Initialize and start the camera stream."""
        if PICAMERA_VERSION == 2:
            print("Using PiCamera2...")
            self.video_stream = PiCamera2Stream()
        elif PICAMERA_VERSION == 1:
            print("Using PiCamera (legacy)...")
            self.video_stream = PiCameraLegacyStream()
        else:
            print("Using OpenCV camera...")
            self.video_stream = OpenCVStream()
            
        self.video_stream.start()
        time.sleep(2)  # Allow camera to warm up
        
    def calculate_movement(self, face_x, face_y):
        """
        Calculate how much to move the servos to center the face.
        Uses dynamic gain - moves faster when face is near edges.
        Returns (pan_delta, tilt_delta).
        """
        # Calculate error (how far face is from center)
        error_x = self.center_x - face_x
        error_y = self.center_y - face_y
        
        # Apply dead zone
        if abs(error_x) < DEAD_ZONE_X:
            error_x = 0
        if abs(error_y) < DEAD_ZONE_Y:
            error_y = 0
            
        # Calculate dynamic gain based on position
        # Boost gain when face is in edge zones
        pan_gain = PAN_GAIN
        tilt_gain = TILT_GAIN
        
        # Check if face is in horizontal edge zone
        if face_x < self.edge_left or face_x > self.edge_right:
            pan_gain *= EDGE_BOOST
            
        # Check if face is in vertical edge zone
        if face_y < self.edge_top or face_y > self.edge_bottom:
            tilt_gain *= EDGE_BOOST
            
        # Calculate movement with dynamic gain
        pan_delta = error_x * pan_gain
        tilt_delta = -error_y * tilt_gain  # Invert for correct direction
        
        # Clamp to maximum step size to prevent jerky motion
        pan_delta = max(-MAX_PAN_STEP, min(MAX_PAN_STEP, pan_delta))
        tilt_delta = max(-MAX_TILT_STEP, min(MAX_TILT_STEP, tilt_delta))
        
        return pan_delta, tilt_delta
        
    def search_for_face(self):
        """
        Pan left-right AND tilt up-down in a scanning pattern.
        Scans horizontally, then moves down and scans again.
        """
        pan, tilt = self.pan_tilt.get_position()
        
        # Move pan in current direction
        pan += self.search_pan_direction * SEARCH_PAN_SPEED
        
        # When we hit a pan limit, reverse pan direction and move tilt down
        if pan >= PAN_MAX - 5:
            self.search_pan_direction = -1
            tilt += SEARCH_TILT_SPEED  # Move down
        elif pan <= PAN_MIN + 5:
            self.search_pan_direction = 1
            tilt += SEARCH_TILT_SPEED  # Move down
            
        # When we hit bottom tilt limit, go back to top
        if tilt >= TILT_MAX - 5:
            tilt = TILT_MIN + 10  # Start from top again
            
        # When we hit top tilt limit (if tilting up), go to bottom
        if tilt <= TILT_MIN + 5:
            tilt = TILT_MIN + 10
            
        self.pan_tilt.goto(pan, tilt)
        
    def update_fps(self):
        """Update FPS counter."""
        self.fps_frame_count += 1
        elapsed = time.time() - self.fps_start_time
        
        if elapsed >= FPS_DISPLAY_INTERVAL:
            self.current_fps = self.fps_frame_count / elapsed
            self.fps_frame_count = 0
            self.fps_start_time = time.time()
            
            if DEBUG:
                pan, tilt = self.pan_tilt.get_position()
                print(f"FPS: {self.current_fps:.1f} | Pan: {pan:.0f} Tilt: {tilt:.0f}")
                
    def run(self):
        """Main tracking loop."""
        print("\n" + "=" * 50)
        print("Face Tracking with Pan-Tilt HAT")
        print("=" * 50)
        print(f"Edge zone: outer {int(EDGE_ZONE*100)}% of frame")
        print(f"Edge boost: {EDGE_BOOST}x tracking speed")
        if SHOW_WINDOW:
            print("Press 'q' in the window to quit")
        print("Press Ctrl+C to quit")
        print("=" * 50 + "\n")
        
        self.start_camera()
        self.pan_tilt.center()
        self.running = True
        
        try:
            while self.running:
                # Get frame
                frame = self.video_stream.read()
                if frame is None:
                    time.sleep(0.01)
                    continue
                    
                # Convert from RGB to BGR if using PiCamera2
                if PICAMERA_VERSION == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                # Apply flips if needed (only for non-legacy picamera)
                if PICAMERA_VERSION != 1:
                    if CAMERA_HFLIP:
                        frame = cv2.flip(frame, 1)
                    if CAMERA_VFLIP:
                        frame = cv2.flip(frame, 0)
                    
                # Detect faces
                faces = self.detector.detect(frame)
                face = self.detector.get_largest_face(faces)
                
                if face is not None:
                    x, y, w, h = face
                    
                    # Calculate face center
                    face_x = x + w // 2
                    face_y = y + h // 2
                    
                    # Calculate and apply movement
                    pan_delta, tilt_delta = self.calculate_movement(face_x, face_y)
                    self.pan_tilt.move_relative(pan_delta, tilt_delta)
                    
                    # Update state
                    self.last_face_time = time.time()
                    self.search_mode = False
                    
                    # Check if in edge zone for debug output
                    in_edge = (face_x < self.edge_left or face_x > self.edge_right or
                               face_y < self.edge_top or face_y > self.edge_bottom)
                    
                    if DEBUG and self.fps_frame_count % 5 == 0:
                        pan, tilt = self.pan_tilt.get_position()
                        edge_str = " [EDGE BOOST]" if in_edge else ""
                        print(f"Face at ({face_x}, {face_y}) | Pan: {pan:.1f} Tilt: {tilt:.1f}{edge_str}")
                    
                    # Draw on frame for display
                    if SHOW_WINDOW:
                        # Draw edge zones
                        cv2.rectangle(frame, (self.edge_left, self.edge_top),
                                      (self.edge_right, self.edge_bottom), (100, 100, 100), 1)
                        
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        cv2.circle(frame, (face_x, face_y), 5, (0, 0, 255), -1)
                        cv2.line(frame, (self.center_x - 20, self.center_y),
                                 (self.center_x + 20, self.center_y), (255, 0, 0), 1)
                        cv2.line(frame, (self.center_x, self.center_y - 20),
                                 (self.center_x, self.center_y + 20), (255, 0, 0), 1)
                        
                else:
                    # No face detected
                    if time.time() - self.last_face_time > SEARCH_TIMEOUT:
                        # Start searching if no face for timeout period
                        if not self.search_mode:
                            self.search_mode = True
                            if DEBUG:
                                print("No face detected, searching (pan + tilt)...")
                        self.search_for_face()
                        
                # Update FPS
                self.update_fps()
                
                # Show frame if display is available
                if SHOW_WINDOW:
                    pan, tilt = self.pan_tilt.get_position()
                    cv2.putText(frame, f"FPS: {self.current_fps:.1f}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    cv2.putText(frame, f"Pan: {pan:.0f} Tilt: {tilt:.0f}",
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                                
                    if WINDOW_SCALE != 1.0:
                        display_frame = cv2.resize(frame, None, fx=WINDOW_SCALE, fy=WINDOW_SCALE)
                    else:
                        display_frame = frame
                        
                    cv2.imshow("Face Tracker", display_frame)
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("Quit requested...")
                        self.running = False
                    elif key == ord('c'):
                        print("Centering camera...")
                        self.pan_tilt.center()
                        
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Clean up resources."""
        print("Cleaning up...")
        self.running = False
        
        if self.video_stream:
            self.video_stream.stop()
            
        self.pan_tilt.center()
        time.sleep(0.5)
        self.pan_tilt.disable()
        
        if SHOW_WINDOW:
            cv2.destroyAllWindows()
        print("Done.")


# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point."""
    tracker = FaceTracker()
    tracker.run()


if __name__ == "__main__":
    main()
