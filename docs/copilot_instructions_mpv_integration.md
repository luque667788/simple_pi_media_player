# MPV Integration Specifications

## 1. Overview

MPV will be used as the media playback engine. The Flask backend will control MPV, likely through its command-line interface or its IPC (Inter-Process Communication) mechanism if more complex control is needed. For simplicity, command-line control is preferred initially.

## 2. `mpv_controller.py` Module

This Python module will encapsulate all MPV interaction logic. The Flask app will call functions from this module.

**Core Responsibilities:**

*   Starting MPV with appropriate settings for the 2-inch screen.
*   Playing a specified media file.
*   Pausing/resuming playback.
*   Stopping playback (and displaying a black screen).
*   Skipping to the next/previous file (which involves stopping the current MPV instance and starting a new one, or using MPV playlist commands).
*   Applying transitions (this is the most complex part with command-line MPV).

## 3. MPV Command-Line Control

MPV offers extensive command-line options.

*   **Basic Playback**: `mpv /path/to/media.mp4`
*   **Fullscreen**: `mpv --fullscreen /path/to/media.mp4`
*   **Screen Size & Position (Crucial for 2-inch display)**:
    *   `--geometry=240x320+0+0` (width x height + x_offset + y_offset)
    *   `--autofit=240x320` (scale down to fit within this resolution while maintaining aspect ratio)
    *   `--no-border` (removes window decorations)
    *   `--ontop` (keeps the window on top)
    *   `--no-osc` (disables On-Screen Controller)
    *   `--no-osd-bar` (disables On-Screen Display for seekbar, etc.)
    *   `--really-quiet` (suppresses console output from MPV)
    *   `--idle=yes` (keeps MPV open after playback finishes, can be used to show black screen) or `once` to exit.
    *   `--force-window=immediate` (useful for headless environments or specific window management)

*   **Example Command for the 2-inch screen:**
    ```bash
    mpv --no-osc --no-osd-bar --no-border --ontop --really-quiet --autofit=240x320 --geometry=240x320+0+0 --force-window=immediate /path/to/media.mp4
    ```
    For images, MPV can display them for a certain duration:
    ```bash
    mpv --no-osc --no-osd-bar --no-border --ontop --really-quiet --autofit=240x320 --geometry=240x320+0+0 --force-window=immediate --image-display-duration=5 /path/to/image.jpg
    ```
    (Default image duration is 1 second if `--image-display-duration` is not set. This can be configured).

## 4. Managing MPV Process

*   The `mpv_controller.py` will use Python's `subprocess` module to launch and manage the MPV process.
*   A single MPV instance will be managed. To play a new file, the current instance might need to be terminated and a new one started, or MPV's playlist/IPC commands used.
*   **PID Management**: Keep track of the MPV process ID (PID) to send signals (pause, stop/kill).

## 5. Transitions with Command-Line MPV

Achieving smooth fade, dissolve, and slide transitions purely with command-line MPV by launching separate instances for each file is challenging.

*   **Option 1: Basic (No True Transitions)**
    *   Simply stop one MPV instance and start another. This will be abrupt.
*   **Option 2: MPV's Built-in (Limited for this use case)**
    *   MPV has some internal support for transitions between playlist items if playing a playlist directly, but controlling this externally via CLI for dynamic queues is complex.
*   **Option 3: Using MPV's IPC Server (More Complex, More Control)**
    *   MPV can be started with an IPC server: `mpv --input-ipc-server=/tmp/mpvsocket ...`
    *   Python can then send JSON commands to this socket to load files, control playback, and potentially manage more complex behaviors. This is the most robust way to achieve smoother transitions without relying on external tools.
        *   Commands like `loadfile`, `playlist-next`, `playlist-prev`, `set property pause true/false`.
        *   For transitions like fade-out/fade-in, one might use `vf` (video filter) commands if possible via IPC, or by having MPV play a black frame and then the next item.
*   **Option 4: External Scripting/Tools (Adds Dependency)**
    *   Using tools like `ffmpeg` to pre-process or generate transition effects, then played by MPV. This adds significant complexity.

**Decision for Simplicity:**

*   **Initial Implementation**: Start with **Option 1** (abrupt change) or a very simple "fade to black" then "fade from black" by playing a black screen (e.g., a black image or short black video) between media items if the transition is "fade".
*   **"Dissolve" and "Slide"**: These are very hard with CLI MPV. For true simplicity, these might be out of scope or faked (e.g., "dissolve" is just a quick fade-out/fade-in).
*   **Focus on "Fade"**: A simple fade can be simulated by:
    1.  Current media playing.
    2.  (Optional) Use MPV command to reduce volume/opacity if possible via IPC (if chosen).
    3.  Stop MPV.
    4.  Start MPV with a black image for a very short duration (e.g., 0.5s).
    5.  Stop MPV (black image).
    6.  Start MPV with the new media.

**If IPC is chosen (`--input-ipc-server=/tmp/mpvsocket`):**
The `mpv_controller.py` would need a function to send commands to the socket.
```python
import subprocess
import socket
import json
import time
import os

MPV_SOCKET = "/tmp/mpvsocket" # Ensure this path is writable and consistent

class MPVController:
    def __init__(self):
        self.process = None
        self.current_file = None

    def _send_command(self, command_list):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(MPV_SOCKET)
            # Command must be a JSON string followed by a newline
            cmd_str = json.dumps({"command": command_list}) + '\n'
            client.sendall(cmd_str.encode())
            # Optionally, receive response
            # response = client.recv(1024)
            client.close()
            # return json.loads(response.decode()) if response else None
            return True # Simplified
        except Exception as e:
            print(f"Error sending MPV command: {e}")
            # Attempt to restart MPV if socket is dead?
            return False

    def start_player(self, initial_file=None):
        if self.process and self.process.poll() is None:
            print("MPV already running.")
            if initial_file:
                self.load_file(initial_file)
            return

        # Base command for the 2-inch screen
        # Ensure --idle=yes to keep MPV open for IPC commands
        cmd = [
            'mpv', '--no-osc', '--no-osd-bar', '--no-border', '--ontop',
            '--really-quiet', '--autofit=240x320', '--geometry=240x320+0+0',
            '--force-window=immediate', '--input-ipc-server=' + MPV_SOCKET,
            '--idle=yes', '--image-display-duration=5' # Default 5s for images
        ]
        if initial_file:
            cmd.append(initial_file)
        
        # Remove socket file if it exists from a previous unclean shutdown
        if os.path.exists(MPV_SOCKET):
            os.remove(MPV_SOCKET)

        self.process = subprocess.Popen(cmd)
        time.sleep(1) # Give MPV time to start and create the socket

    def load_file(self, filepath, transition="fade"):
        # For simplicity, "fade" transition means load immediately.
        # More complex transitions would involve multiple commands.
        if not self.process or self.process.poll() is not None:
            self.start_player(filepath) # Start MPV if not running
        else:
            self._send_command(["loadfile", filepath, "replace"])
        self.current_file = filepath
        # For a "fade" effect:
        # 1. (If playing) Send command to fade out (e.g. animate property vf lavfi-add "fade=out:st=0:d=0.5")
        # 2. Wait 0.5s
        # 3. Send loadfile command
        # 4. Send command to fade in (e.g. animate property vf lavfi-add "fade=in:st=0:d=0.5")

    def play_pause(self): # Toggles play/pause
        self._send_command(["cycle", "pause"])

    def pause(self):
        self._send_command(["set", "pause", "yes"])
    
    def resume(self):
        self._send_command(["set", "pause", "no"])

    def stop(self): # Stops playback and shows black screen (due to --idle=yes and loading nothing or a black image)
        self._send_command(["stop"]) 
        # To ensure black screen, could load a black image:
        # self._send_command(["loadfile", "/path/to/black.png", "replace"])
        self.current_file = None

    def next_track(self):
        self._send_command(["playlist-next", "weak"]) # weak: stop playback if at end

    def prev_track(self):
        self._send_command(["playlist-prev", "weak"]) # weak: stop playback if at beginning

    def terminate_player(self):
        if self.process:
            if self.process.poll() is None: # If process is running
                self._send_command(["quit"])
                try:
                    self.process.wait(timeout=5) # Wait for graceful exit
                except subprocess.TimeoutExpired:
                    self.process.kill() # Force kill if not exiting
            self.process = None
        if os.path.exists(MPV_SOCKET):
            os.remove(MPV_SOCKET)

# Example Usage (conceptual, will be called by Flask routes)
# controller = MPVController()
# controller.start_player() # Starts MPV in idle mode
# controller.load_file("/path/to/media1.mp4")
# time.sleep(10)
# controller.load_file("/path/to/image.jpg", transition="fade")
# time.sleep(5)
# controller.terminate_player()
```

## 6. Displaying on the 2-inch Screen Only

*   The MPV command needs to be configured to output to the correct display. On Raspberry Pi, this usually means ensuring the X server (if used) or DRM/KMS is targeting the small screen.
*   If running without a desktop environment (headless with X or DRM/KMS), MPV should take over the primary display.
*   The `--geometry` and `--autofit` options are key.
*   The web interface for control will be accessed from another device (PC, phone), not the Pi's 2-inch screen.

## 7. Simplification for Transitions

*   **Fade**: Implement as "stop current, play black screen (short), play next".
*   **Dissolve/Slide**: Mark as "future enhancement" or simplify to be identical to "fade" to meet the "very simple" requirement. The IPC method offers the best path if these are strictly needed later.

## 8. MPV Logging
*   MPV can log to a file: `--log-file=/path/to/mpv.log`. This should be configured in `mpv_controller.py`.
*   Log level can be set, e.g., `--msg-level=all=info`.
