"""
MPV Controller Module

This module will be responsible for interacting with the MPV media player.
It will handle starting, stopping, and controlling playback.
"""

import subprocess
import os
import time
import json
import socket # For IPC
import logging

logger = logging.getLogger(__name__) # This will inherit Flask app's logger configuration

MPV_SOCKET_NAME = "mpvsocket"
# Determine project root dynamically (assuming mpv_controller.py is in 'app' directory)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MPV_SOCKET_PATH = os.path.join(PROJECT_ROOT, MPV_SOCKET_NAME) # Place socket in project root for visibility
MPV_LOG_PATH = os.path.join(PROJECT_ROOT, "mpv.log")

class MPVController:
    def __init__(self):
        self.process = None
        self.current_file = None
        self.is_playing_media = False # More specific than just process running
        logger.info(f"MPVController initialized. Socket path: {MPV_SOCKET_PATH}, Log path: {MPV_LOG_PATH}")

    def _ensure_mpv_executable(self):
        # Simple check if mpv is in PATH
        if subprocess.call(["which", "mpv"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            logger.error("MPV executable not found in PATH. Please install MPV.")
            raise FileNotFoundError("MPV executable not found.")

    def _send_command(self, command_list):
        if not self.process or self.process.poll() is not None:
            logger.warning("Attempted to send command but MPV process is not running.")
            # Try to restart it in a basic idle state if it died unexpectedly
            # self.start_player() # Be careful with recursion or unintended starts
            return False
        
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(MPV_SOCKET_PATH)
            cmd_str = json.dumps({"command": command_list}) + '\n'
            client.sendall(cmd_str.encode('utf-8'))
            # For most commands, we don't strictly need a response immediately
            # response_data = client.recv(1024) # Buffer size
            client.close()
            # logger.debug(f"Sent command: {command_list}, Response: {response_data.decode() if response_data else 'No response'}")
            logger.debug(f"Sent command: {command_list}")
            return True
        except socket.error as e:
            logger.error(f"Socket error sending MPV command '{command_list}': {e}. MPV might have crashed or socket is misconfigured.")
            # Consider attempting to restart MPV here or flagging it as non-responsive
            # self.terminate_player() # Clean up potentially broken state
            # self.start_player()   # And try to restart
            return False
        except Exception as e:
            logger.error(f"Generic error sending MPV command '{command_list}': {e}")
            return False

    def start_player(self):
        self._ensure_mpv_executable()
        if self.process and self.process.poll() is None:
            logger.info("MPV is already running.")
            return True

        if os.path.exists(MPV_SOCKET_PATH):
            logger.warning(f"Socket file {MPV_SOCKET_PATH} exists. Removing before starting MPV.")
            try:
                os.remove(MPV_SOCKET_PATH)
            except OSError as e:
                logger.error(f"Error removing existing socket file: {e}")
                return False # Cannot proceed if socket can't be cleared

        # Command for 2-inch screen, IPC, and logging
        # Using --idle=yes to keep MPV open and responsive to IPC commands
        cmd = [
            'mpv',
            '--no-osc', '--no-osd-bar', '--no-border', '--ontop',
            '--really-quiet', # MPV's own stdout/stderr suppression
            '--autofit=240x320', '--geometry=240x320+0+0',
            '--force-window=immediate',
            '--input-ipc-server=' + MPV_SOCKET_PATH,
            '--idle=yes',
            '--image-display-duration=5', # Default 5s for images
            '--log-file=' + MPV_LOG_PATH,
            '--msg-level=all=info' # MPV log level
        ]

        try:
            logger.info(f"Starting MPV with command: {' '.join(cmd)}")
            # Start MPV in the background
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5) # Increased wait time for MPV to initialize and create socket

            # Check if socket was created
            if not os.path.exists(MPV_SOCKET_PATH):
                logger.error(f"MPV started but socket file {MPV_SOCKET_PATH} was not created.")
                self.terminate_player() # Clean up
                return False
            
            logger.info(f"MPV started successfully. PID: {self.process.pid}")
            self.is_playing_media = False # MPV is idle, not playing a file yet
            return True
        except FileNotFoundError:
            logger.error("MPV command failed: executable not found. Ensure MPV is installed and in PATH.")
            self.process = None
            return False
        except Exception as e:
            logger.error(f"Failed to start MPV: {e}")
            self.process = None
            return False

    def load_file(self, filepath, transition="fade"):
        if not self.process or self.process.poll() is not None:
            logger.warning("MPV not running, attempting to start it before loading file.")
            if not self.start_player():
                logger.error("Failed to start MPV, cannot load file.")
                return False
        
        full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', filepath) # Assuming files are in app/uploads
        if not os.path.exists(full_path):
            logger.error(f"Media file not found: {full_path}")
            return False

        logger.info(f"Loading file: {full_path} with transition: {transition}")
        
        # Simple implementation of transitions
        if transition == "fade" and self.is_playing_media:
            # For a simple fade effect:
            # 1. Set property for crossfading if it's a video, uses MPV's internal fading
            self._send_command(["set_property", "video-sync", "display-resample"])
            # 2. For images, we'll use a basic fade-out and fade-in approach
            file_ext = os.path.splitext(filepath)[1].lower()
            if file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                # For images: gradual decrease in alpha, then load new file
                for i in range(10, 0, -1):  # 10 steps of fading
                    opacity = i / 10.0
                    self._send_command(["set_property", "alpha", str(opacity)])
                    time.sleep(0.05)  # 50ms between steps = ~0.5s total fade
            
            # Now load the new file
            success = self._send_command(["loadfile", full_path, "replace"])
            
            # Fade back in for images
            if file_ext in ['.jpg', '.jpeg', '.png', '.gif'] and success:
                for i in range(1, 11):  # 10 steps of fading in
                    opacity = i / 10.0
                    self._send_command(["set_property", "alpha", str(opacity)])
                    time.sleep(0.05)
            
            if success:
                self.current_file = filepath
                self.is_playing_media = True
                logger.info(f"File {filepath} loaded into MPV with fade transition.")
                return True
        else:
            # No transition or MPV wasn't playing, just load directly
            if self._send_command(["loadfile", full_path, "replace"]):
                self.current_file = filepath
                self.is_playing_media = True
                logger.info(f"File {filepath} loaded into MPV.")
                return True
        
        logger.error(f"Failed to send loadfile command for {filepath}.")
        return False

    def play(self):
        # This command resumes if paused, or starts the loaded file if stopped but loaded.
        # If MPV is idle with no file, it does nothing until a file is loaded.
        if not self.current_file and self.is_playing_media == False:
            logger.info("Play command issued, but no file is loaded and not currently playing. MPV is idle.")
            # This implies the playlist logic in main.py should load a file first.
            return False # Or True, as MPV is technically not in an error state

        if self._send_command(["set", "pause", "no"]):
            self.is_playing_media = True
            logger.info(f"Playback resumed/started for {self.current_file if self.current_file else 'current media'}.")
            return True
        return False

    def pause(self):
        if self._send_command(["set", "pause", "yes"]):
            self.is_playing_media = False
            logger.info(f"Playback paused for {self.current_file if self.current_file else 'current media'}.")
            return True
        return False

    def toggle_pause(self):
        if self._send_command(["cycle", "pause"]):
            # We need to query the actual pause state to update is_playing_media accurately
            # This is more complex, for now, we assume it toggles successfully
            # For a robust solution, query: {"command": ["get_property", "pause"]}
            self.is_playing_media = not self.is_playing_media # This is an assumption
            logger.info(f"Toggled pause. Assumed playing state: {self.is_playing_media}")
            return True
        return False

    def stop(self): # Stops playback, MPV remains idle (shows black due to --idle=yes)
        if self._send_command(["stop"]):
            logger.info("Playback stopped. MPV is idle (should show black screen).")
            self.current_file = None # No specific file is active
            self.is_playing_media = False
            return True
        return False

    # Playlist commands are for MPV's internal playlist, which we might not use directly
    # if Flask manages the queue. If Flask tells MPV to play files one-by-one, these are less relevant.
    def playlist_next(self):
        if self._send_command(["playlist-next", "weak"]): # weak: stop if at end
            # Need to update self.current_file by querying MPV, which is complex.
            # For now, assume Flask will manage current file knowledge.
            logger.info("Sent playlist-next command.")
            self.is_playing_media = True # Assuming it plays something or stops
            return True
        return False

    def playlist_prev(self):
        if self._send_command(["playlist-prev", "weak"]): # weak: stop if at beginning
            logger.info("Sent playlist-prev command.")
            self.is_playing_media = True
            return True
        return False

    def terminate_player(self):
        logger.info("Attempting to terminate MPV player...")
        if self.process:
            if self.process.poll() is None: # If process is running
                logger.info("Sending quit command to MPV...")
                self._send_command(["quit"])
                try:
                    self.process.wait(timeout=3) # Wait for graceful exit
                    logger.info("MPV process terminated gracefully.")
                except subprocess.TimeoutExpired:
                    logger.warning("MPV did not quit gracefully, killing process.")
                    self.process.kill()
                    logger.info("MPV process killed.")
                except Exception as e:
                    logger.error(f"Exception during MPV termination: {e}. Forcing kill.")
                    self.process.kill()
            else:
                logger.info("MPV process was already terminated.")
            self.process = None
            self.current_file = None
            self.is_playing_media = False
        else:
            logger.info("No MPV process was active to terminate.")

        # Clean up socket file if it exists
        if os.path.exists(MPV_SOCKET_PATH):
            logger.info(f"Removing MPV socket file: {MPV_SOCKET_PATH}")
            try:
                os.remove(MPV_SOCKET_PATH)
            except OSError as e:
                logger.error(f"Error removing MPV socket file: {e}")
        return True

    def get_playback_status(self):
        """Queries MPV for its current status. More complex and requires response handling."""
        # Example: {"command": ["get_property", "playback-time"]}
        # Example: {"command": ["get_property", "pause"]}
        # Example: {"command": ["get_property", "path"]}
        # This would require robust request-response handling in _send_command
        # For now, we rely on internal state tracking, which can get out of sync.
        return {
            "is_mpv_running": self.process is not None and self.process.poll() is None,
            "current_file": self.current_file,
            "is_playing_media": self.is_playing_media
        }

# Example usage (for testing this module directly):
if __name__ == '__main__':
    # Setup basic logging for standalone testing
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s')
    
    # Create a dummy uploads folder and a test file for standalone execution
    test_upload_dir = os.path.join(PROJECT_ROOT, 'app', 'uploads')
    os.makedirs(test_upload_dir, exist_ok=True)
    dummy_file_name = "test_image.png"
    dummy_file_path = os.path.join(test_upload_dir, dummy_file_name)
    
    # Create a small dummy PNG if it doesn't exist (requires Pillow or similar, or use a known existing image)
    # For simplicity, let's assume a file exists or MPV handles missing file gracefully for test.
    # You can manually place an image like 'test_image.png' in app/uploads for this test.
    if not os.path.exists(dummy_file_path):
        try:
            from PIL import Image
            img = Image.new('RGB', (60, 30), color = 'red')
            img.save(dummy_file_path)
            logger.info(f"Created dummy file: {dummy_file_path}")
        except ImportError:
            logger.warning("Pillow not installed. Cannot create dummy image. Please place a test image at app/uploads/test_image.png")
            # exit() # Or continue without it if MPV handles it

    controller = MPVController()
    try:
        logger.info("--- Test: Starting MPV Player ---")
        if controller.start_player():
            logger.info("MPV Player started in idle mode.")
            time.sleep(2)

            if os.path.exists(dummy_file_path):
                logger.info(f"--- Test: Loading and Playing '{dummy_file_name}' ---")
                controller.load_file(dummy_file_name)
                time.sleep(1) # Give time for loadfile to process
                controller.play() # Explicitly tell it to play if it was paused or just loaded
                logger.info(f"Playing '{dummy_file_name}'. Should be visible for ~5 seconds.")
                time.sleep(6) # Image display duration + buffer
            else:
                logger.warning(f"Skipping load file test as '{dummy_file_path}' does not exist.")

            logger.info("--- Test: Pausing Playback ---")
            controller.pause()
            logger.info("Playback paused. Should remain on last frame.")
            time.sleep(3)

            logger.info("--- Test: Resuming Playback (or re-playing if image duration passed) ---")
            controller.play()
            logger.info("Playback resumed.")
            time.sleep(3)

            logger.info("--- Test: Stopping Playback (Black Screen) ---")
            controller.stop()
            logger.info("Playback stopped. MPV idle (black screen). Wait 3s.")
            time.sleep(3)
            
            # Test loading another file if available, or re-load
            if os.path.exists(dummy_file_path):
                logger.info(f"--- Test: Re-loading '{dummy_file_name}' ---")
                controller.load_file(dummy_file_name)
                time.sleep(6)
            
        else:
            logger.error("MPV Player failed to start. Aborting tests.")

    except Exception as e:
        logger.error(f"An error occurred during testing: {e}", exc_info=True)
    finally:
        logger.info("--- Test: Terminating MPV Player ---")
        controller.terminate_player()
        logger.info("MPV Player terminated.")

        # Clean up dummy file if created by this script
        # if os.path.exists(dummy_file_path) and 'img' in locals(): # Check if we created it
        #     os.remove(dummy_file_path)
        #     logger.info(f"Removed dummy file: {dummy_file_path}")

