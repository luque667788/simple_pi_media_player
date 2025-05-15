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

    def _execute_command_and_get_response(self, command_list):
        """Send command to MPV and wait for a response"""
        if not self.process or self.process.poll() is not None:
            logger.warning("Attempted to send command but MPV process is not running.")
            return None
        
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(MPV_SOCKET_PATH)
            # Set a unique request ID to match the response
            request_id = int(time.time() * 1000) % 1000000
            cmd_str = json.dumps({"command": command_list, "request_id": request_id}) + '\n'
            client.sendall(cmd_str.encode('utf-8'))
            
            # Wait for and parse response - timeout after 1 second
            client.settimeout(1.0)
            response_data = client.recv(1024)
            client.close()
            
            if not response_data:
                logger.warning(f"No response data received for command: {command_list}")
                return None
                
            try:
                # The response might contain multiple JSON objects (e.g., if events are emitted)
                # We need to find the one that matches our request_id
                for line in response_data.decode('utf-8').splitlines():
                    try:
                        resp = json.loads(line)
                        if 'request_id' in resp and resp['request_id'] == request_id:
                            return resp
                    except json.JSONDecodeError:
                        continue
                        
                logger.warning(f"Could not find matching response for request_id {request_id}")
                return None
            except Exception as e:
                logger.error(f"Failed to parse response from MPV: {e}, Data: {response_data}")
                return None
        except socket.timeout:
            logger.error(f"Socket timeout getting response for MPV command '{command_list}'")
            return None
        except socket.error as e:
            logger.error(f"Socket error getting response for MPV command '{command_list}': {e}")
            return None
        except Exception as e:
            logger.error(f"Generic error getting response for MPV command '{command_list}': {e}")
            return None

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
            '--really-quiet', # MPV\'s own stdout/stderr suppression
            '--autofit=240x320', '--geometry=240x320+0+0',
            '--force-window=immediate',
            '--input-ipc-server=' + MPV_SOCKET_PATH,
            '--idle=yes', # Keep MPV open and responsive
            '--keep-open=no', # IMPORTANT: When a file ends, stop and report EOF, don't keep last frame.
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

    def load_playlist(self, playlist_files, start_index=0):
        """Loads a list of files into MPV's internal playlist and sets the starting position."""
        if not self.process or self.process.poll() is not None:
            logger.warning("MPV not running, attempting to start it before loading playlist.")
            if not self.start_player():
                logger.error("Failed to start MPV, cannot load playlist.")
                return False
        
        if not playlist_files:
            logger.warning("load_playlist called with an empty list of files.")
            self._send_command(["stop"]) # Stop any current playback
            self._send_command(["playlist-clear"]) # Clear MPV's playlist
            self.current_file = None
            self.is_playing_media = False
            return True # Successfully cleared playlist

        logger.info(f"Loading playlist into MPV: {playlist_files} starting at index {start_index}")

        self._send_command(["playlist-clear"])
        # logger.debug("Sent playlist-clear to MPV.")

        for filename in playlist_files:
            full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', filename)
            if os.path.exists(full_path):
                # Use 'append' to add to MPV's playlist without starting playback immediately
                self._send_command(["loadfile", full_path, "append"])
                # logger.debug(f"Appended {filename} to MPV playlist.")
            else:
                logger.warning(f"File {filename} not found at {full_path}, skipping in MPV playlist load.")
        
        # Set the starting position in MPV's playlist (0-indexed)
        if 0 <= start_index < len(playlist_files):
            self._send_command(["set_property", "playlist-pos", start_index])
            # logger.debug(f"Set MPV playlist-pos to {start_index}.")
            self.current_file = playlist_files[start_index] # Anticipate current file
        else:
            logger.warning(f"Invalid start_index {start_index} for playlist of length {len(playlist_files)}. Defaulting to 0.")
            self._send_command(["set_property", "playlist-pos", 0])
            if playlist_files: # Check if playlist_files is not empty
                self.current_file = playlist_files[0]
            else:
                self.current_file = None # Should not happen if playlist_files is checked above

        # self.is_playing_media = False # Playback is initiated by a separate play command
        logger.info(f"MPV playlist loaded. Current anticipated file: {self.current_file}")
        return True

    def load_file(self, filepath, transition="fade"): # Transition currently not used
        if not self.process or self.process.poll() is not None:
            logger.warning("MPV not running, attempting to start it before loading file.")
            if not self.start_player(): # This will now also set keep-open=no
                logger.error("Failed to start MPV, cannot load file.")
                return False
        
        full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', filepath) # Assuming files are in app/uploads
        if not os.path.exists(full_path):
            logger.error(f"Media file not found: {full_path}")
            return False

        logger.info(f"Loading file: {full_path} with transition: {transition}")
        
        # Simplified: Just load and replace. Transitions can be added back later.
        if self._send_command(["loadfile", full_path, "replace"]):
            self.current_file = filepath
            # self.is_playing_media = False # Playback is initiated by a separate play command
            logger.info(f"File {filepath} loaded into MPV (replace).")
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
        """Toggle between play and pause states"""
        if self._send_command(["cycle", "pause"]):
            # Query the actual pause state after toggling
            pause_response = self._execute_command_and_get_response(["get_property", "pause"])
            if pause_response and "data" in pause_response:
                self.is_playing_media = not pause_response["data"]
                logger.info(f"Toggled pause. Actual playing state from MPV: {self.is_playing_media}")
            else:
                # If we can't get the state, assume it toggled successfully
                self.is_playing_media = not self.is_playing_media
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
        if self._send_command(["playlist-next", "weak"]): # weak: stop if at end and not looping
            logger.info("Sent playlist-next command to MPV.")
            # self.is_playing_media = True # State will be updated by get_playback_status
            return True
        logger.warning("Failed to send playlist-next command to MPV.")
        return False

    def playlist_prev(self):
        if self._send_command(["playlist-prev", "weak"]): # weak: stop if at beginning and not looping
            logger.info("Sent playlist-prev command to MPV.")
            # self.is_playing_media = True # State will be updated by get_playback_status
            return True
        logger.warning("Failed to send playlist-prev command to MPV.")
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
        """Queries MPV for its current status."""
        status = {
            "is_mpv_running": self.process is not None and self.process.poll() is None,
            "current_file": self.current_file,
            "is_playing_media": self.is_playing_media
        }
        
        if not status["is_mpv_running"]:
            return status

        # Check if we're at end-of-file - directly detects video completion
        try:
            eof_resp = self._execute_command_and_get_response(["get_property", "eof-reached"])
            if eof_resp and "data" in eof_resp:
                status["eof_reached"] = eof_resp["data"]
                if eof_resp["data"]:
                    status["status"] = "stopped"
                    logger.info("MPV reports end-of-file reached")
        except Exception as e:
            logger.error(f"Error querying MPV eof-reached: {e}")
            
        # Also check idle-active as backup
        if "status" not in status:
            try:
                idle_resp = self._execute_command_and_get_response(["get_property", "idle-active"])
                if idle_resp and "data" in idle_resp and idle_resp["data"]:
                    status["status"] = "stopped"
                else:
                    # Query pause state: False => playing, True => paused
                    pause_resp = self._execute_command_and_get_response(["get_property", "pause"])
                    if pause_resp and "data" in pause_resp:
                        status["status"] = "paused" if pause_resp["data"] else "playing"
                        status["is_playing_media"] = not pause_resp["data"]
                    else:
                        status["status"] = None
            except Exception as e:
                logger.error(f"Error querying MPV status: {e}")
                status["status"] = None

        return status

    def get_loop_status(self):
        """Get current loop settings"""
        loop_status = {"loop_file": False, "loop_playlist": False}
        
        if not self.process or self.process.poll() is not None:
            return loop_status
            
        try:
            # Get loop-file status
            loop_file_response = self._execute_command_and_get_response(["get_property", "loop-file"])
            if loop_file_response and "data" in loop_file_response:
                loop_status["loop_file"] = loop_file_response["data"] != "no"
                
            # Get loop-playlist status
            loop_playlist_response = self._execute_command_and_get_response(["get_property", "loop-playlist"])
            if loop_playlist_response and "data" in loop_playlist_response:
                loop_status["loop_playlist"] = loop_playlist_response["data"] != "no"
                
        except Exception as e:
            logger.error(f"Failed to get loop status: {e}")
            
        return loop_status

    def set_loop_mode(self, mode):
        """Set loop mode for MPV.
           Uses MPV's internal playlist features when mode is 'playlist'.
        Args:
            mode (str): One of 'none', 'file', or 'playlist'
        """
        try:
            if mode == 'none': # Stop at end of file (if single) or end of playlist (if MPV playlist was loaded)
                self._send_command(["set_property", "loop-file", "no"])
                self._send_command(["set_property", "loop-playlist", "no"])
                self._send_command(["set_property", "keep-open", "no"]) 
                logger.info("MPV loop mode set for 'none': loop-file=no, loop-playlist=no, keep-open=no.")
            elif mode == 'file': # Loop the current file indefinitely
                self._send_command(["set_property", "loop-file", "inf"])
                self._send_command(["set_property", "loop-playlist", "no"]) # Ensure MPV doesn't advance its own playlist
                self._send_command(["set_property", "keep-open", "yes"]) 
                logger.info("MPV loop mode set for 'file': loop-file=inf, loop-playlist=no, keep-open=yes.")
            elif mode == 'playlist': # MPV handles playlist looping and advancement
                self._send_command(["set_property", "loop-file", "no"]) # Individual files should not loop
                self._send_command(["set_property", "loop-playlist", "inf"]) # Loop the entire MPV playlist
                self._send_command(["set_property", "keep-open", "no"]) # When a file in playlist ends, MPV goes to next
                logger.info("MPV loop mode set for 'playlist': loop-file=no, loop-playlist=inf, keep-open=no.")
            else:
                logger.warning(f"Unknown loop mode: {mode}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to set loop mode {mode}: {e}")
            return False

    def toggle_loop_file(self):
        """Toggle loop mode for the current file"""
        if self._send_command(["cycle", "loop-file"]):
            # Query the actual loop-file state after toggling
            loop_file_response = self._execute_command_and_get_response(["get_property", "loop-file"])
            if loop_file_response and "data" in loop_file_response:
                is_looping_file = loop_file_response["data"] != "no"
                logger.info(f"Toggled loop-file. Actual state from MPV: {'looping' if is_looping_file else 'not looping'}")
                return True
            else:
                logger.warning("Toggled loop-file, but could not determine actual state from MPV.")
                return True # Assume success
        return False

    def toggle_loop_playlist(self):
        """Toggle loop mode for the playlist"""
        if self._send_command(["cycle", "loop-playlist"]):
            # Query the actual loop-playlist state after toggling
            loop_playlist_response = self._execute_command_and_get_response(["get_property", "loop-playlist"])
            if loop_playlist_response and "data" in loop_playlist_response:
                is_looping_playlist = loop_playlist_response["data"] != "no"
                logger.info(f"Toggled loop-playlist. Actual state from MPV: {'looping' if is_looping_playlist else 'not looping'}")
                return True
            else:
                logger.warning("Toggled loop-playlist, but could not determine actual state from MPV.")
                return True # Assume success
        return False

    # Example usage (for testing this module directly):
if __name__ == '__main__':
    # Setup basic logging for standalone testing
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s')
    
    # Use a test video file from uploads directory
    test_upload_dir = os.path.join(PROJECT_ROOT, 'app', 'uploads')
    os.makedirs(test_upload_dir, exist_ok=True)
    # Pick the first .mp4 file found in uploads for testing
    test_video_file = None
    for f in os.listdir(test_upload_dir):
        if f.lower().endswith('.mp4'):
            test_video_file = f
            break
    
    if not test_video_file:
        logger.error("No .mp4 video file found in app/uploads for testing. Please add a test video.")
    else:
        controller = MPVController()
        try:
            logger.info("--- Test: Starting MPV Player ---")
            if controller.start_player():
                logger.info("MPV Player started in idle mode.")
                time.sleep(2)

                logger.info(f"--- Test: Loading and Playing '{test_video_file}' ---")
                controller.load_file(test_video_file)
                time.sleep(1) # Give time for loadfile to process
                controller.play() # Explicitly tell it to play if it was paused or just loaded
                logger.info(f"Playing '{test_video_file}'. Should be visible for ~5 seconds.")
                time.sleep(6) # Video display duration + buffer

                logger.info("--- Test: Pausing Playback ---")
                controller.pause()
                logger.info("Playback paused. Should remain on last frame.")
                time.sleep(3)

                logger.info("--- Test: Resuming Playback (or re-playing if video duration passed) ---")
                controller.play()
                logger.info("Playback resumed.")
                time.sleep(3)

                logger.info("--- Test: Stopping Playback (Black Screen) ---")
                controller.stop()
                logger.info("Playback stopped. MPV idle (black screen). Wait 3s.")
                time.sleep(3)
            else:
                logger.error("MPV Player failed to start. Aborting tests.")

        except Exception as e:
            logger.error(f"An error occurred during testing: {e}", exc_info=True)
        finally:
            logger.info("--- Test: Terminating MPV Player ---")
            controller.terminate_player()
            logger.info("MPV Player terminated.")

