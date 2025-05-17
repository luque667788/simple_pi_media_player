import subprocess
import os
import time
import logging
from dotenv import load_dotenv # Add this import

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MPLAYER_LOG_PATH = os.path.join(PROJECT_ROOT, "mplayer.log")
MPLAYER_FIFO_PATH = os.path.join(PROJECT_ROOT, "mplayer.fifo") # Add FIFO path
load_dotenv(os.path.join(PROJECT_ROOT, '.env')) # Load .env file

class MPlayerController:
    def __init__(self):
        self.process = None
        self.current_file = None
        self.is_playing_media = False
        self.is_paused = False  # Track paused state
        self.loop_mode = 'none'  # Track loop mode: 'none', 'file', 'playlist'
        self.pending_playlist_config = None # Stores {'files': list_of_files, 'index': start_index}
        self.file_being_waited_on = None  # Stores the filename of the song whose completion triggers reload
        self._setup_fifo()  # Set up the FIFO pipe on initialization
        logger.info(f"MPlayerController initialized. Log path: {MPLAYER_LOG_PATH}, FIFO path: {MPLAYER_FIFO_PATH}")

    def _setup_fifo(self):
        """Set up the FIFO (named pipe) for communicating with MPlayer in slave mode"""
        # Remove existing FIFO if it exists
        if os.path.exists(MPLAYER_FIFO_PATH):
            try:
                os.unlink(MPLAYER_FIFO_PATH)
                logger.debug(f"Removed existing FIFO pipe: {MPLAYER_FIFO_PATH}")
            except OSError as e:
                logger.error(f"Failed to remove existing FIFO pipe: {e}")
        
        try:
            # Create a new FIFO pipe
            os.mkfifo(MPLAYER_FIFO_PATH)
            logger.info(f"Created MPlayer FIFO pipe at: {MPLAYER_FIFO_PATH}")
        except OSError as e:
            logger.error(f"Failed to create FIFO pipe: {e}")

    def _send_command(self, command):
        """Send a command to MPlayer through the FIFO pipe"""
        if not self.process or self.process.poll() is not None:
            logger.warning("Tried to send command but MPlayer is not running")
            return False
            
        try:
            with open(MPLAYER_FIFO_PATH, 'w') as fifo:
                fifo.write(f"{command}\n")
                fifo.flush()
            logger.debug(f"Sent command to MPlayer: {command}")
            return True
        except Exception as e:
            logger.error(f"Failed to send command to MPlayer: {e}")
            return False

    def _ensure_mplayer_executable(self):
        if subprocess.call(["which", "mplayer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            logger.error("MPlayer executable not found in PATH.")
            raise FileNotFoundError("MPlayer executable not found.")

    def start_player(self):
        # Nothing to do here anymore; MPlayer does not use a daemon mode like mpv's --idle
        return True

    def load_file(self, filepath, transition="fade"):
        self._ensure_mplayer_executable()
        if self.process:
            self.terminate_player()

        full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', filepath)
        if not os.path.exists(full_path):
            logger.error(f"Media file not found: {full_path}")
            return False

        logger.info(f"Starting MPlayer with file in slave mode: {full_path}")
        
        # Make sure FIFO exists
        if not os.path.exists(MPLAYER_FIFO_PATH):
            self._setup_fifo()
            
        target_device = os.getenv("KTV_TARGET_DEVICE", "laptop") # Get target device from .env
        
        cmd = ["mplayer"]

        if target_device == "raspberrypi":
            cmd.extend([
                "-vo", "fbdev",
                "-fbdev", "/dev/fb0", # Corrected path for framebuffer
                "-x", "240",
                "-y", "320",
                "-bpp", "16",
                "-vf", "scale=240:320"
            ])
            logger.info("Configuring MPlayer for Raspberry Pi (framebuffer)")
        else: # Default to laptop (X11)
            cmd.extend([
                "-vo", "x11",
            ])
            logger.info("Configuring MPlayer for Laptop (X11)")
        
        # Add loop parameter based on loop mode
        if self.loop_mode == 'file':
            cmd.extend(["-loop", "0"])  # 0 means infinite loop
            logger.info("Adding file loop mode (infinite)")
        
        cmd.extend([
            "-quiet",
            "-nolirc",
            "-slave",  # Enable slave mode for control commands
            "-input", f"file={MPLAYER_FIFO_PATH}", # Specify FIFO for commands
            full_path
        ])

        try:
            with open(MPLAYER_LOG_PATH, "w") as log_file:
                logger.debug(f"Attempting to start MPlayer with command: {' '.join(cmd)}")
                self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            
            time.sleep(0.2) # Brief pause to allow MPlayer to start and potentially write to log

            if os.path.exists(MPLAYER_LOG_PATH):
                log_size = os.path.getsize(MPLAYER_LOG_PATH)
                logger.debug(f"MPLAYER_LOG_PATH ({MPLAYER_LOG_PATH}) exists after Popen in load_file. Size: {log_size} bytes.")
                if log_size == 0:
                    logger.warning(f"MPLAYER_LOG_PATH is 0 bytes immediately after MPlayer Popen call in load_file.")
            else:
                logger.warning(f"MPLAYER_LOG_PATH ({MPLAYER_LOG_PATH}) does not exist after Popen in load_file.")

            self.current_file = filepath
            self.is_playing_media = True
            self.is_paused = False
            return True
        except Exception as e:
            logger.error(f"Failed to start MPlayer in load_file: {e}")
            if os.path.exists(MPLAYER_LOG_PATH):
                logger.error(f"MPLAYER_LOG_PATH size on Popen failure in load_file: {os.path.getsize(MPLAYER_LOG_PATH)} bytes.")
            else:
                logger.error(f"MPLAYER_LOG_PATH does not exist on Popen failure in load_file.")
            return False

    def play(self):
        """Resume playback if paused, otherwise starts playback"""
        if not self.process or self.process.poll() is not None:
            logger.warning("Cannot play: MPlayer is not running")
            return False
            
        if self.is_paused:
            logger.info("Resuming playback from paused state")
            if self._send_command("pause"):
                self.is_paused = False
                self.is_playing_media = True
                return True
        else:
            logger.info("Play command sent, but player is already in playing state")
            return True
        return False

    def pause(self):
        """Pause playback if playing"""
        if not self.process or self.process.poll() is not None:
            logger.warning("Cannot pause: MPlayer is not running")
            return False
            
        if not self.is_paused and self.is_playing_media:
            logger.info("Pausing playback")
            if self._send_command("pause"):
                self.is_paused = True
                return True
        else:
            logger.info("Pause command sent, but player is already paused or not playing")
            return True
        return False

    def toggle_pause(self):
        """Toggle between play and pause states"""
        if not self.process or self.process.poll() is not None:
            logger.warning("Cannot toggle pause: MPlayer is not running")
            return False
            
        logger.info(f"Toggling pause state. Current state - is_paused: {self.is_paused}, is_playing_media: {self.is_playing_media}")
        if self._send_command("pause"):
            self.is_paused = not self.is_paused
            return True
        return False

    def stop(self):
        return self.terminate_player()

    def terminate_player(self):
        logger.info("Attempting to terminate MPlayer...")
        if self.process:
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                    logger.info("MPlayer terminated.")
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    logger.warning("MPlayer killed after timeout.")
            self.process = None
            self.current_file = None
            self.is_playing_media = False
            self.is_paused = False
        return True

    def get_playback_status(self):
        current_mplayer_process_running = self.process is not None and self.process.poll() is None
        # Store the current file *before* the log check potentially changes it.
        # This helps determine if the specific file we were waiting for has indeed changed.
        previous_file_state_before_log_check = self.current_file

        if current_mplayer_process_running and self.loop_mode == 'playlist':
            self._check_mplayer_log_for_current_file() # This might update self.current_file

        # Check for pending playlist update
        if self.pending_playlist_config and self.file_being_waited_on:
            trigger_reload = False
            current_mplayer_process_still_running_after_log_check = self.process is not None and self.process.poll() is None

            if not current_mplayer_process_still_running_after_log_check: # MPlayer stopped
                logger.info(f"MPlayer stopped while waiting for '{self.file_being_waited_on}' to finish. Triggering pending playlist load.")
                trigger_reload = True
            # self.current_file is now the file reported by the log (or None if mplayer stopped and was cleaned up)
            # We compare it against the file we explicitly started waiting for.
            elif self.current_file != self.file_being_waited_on:
                logger.info(f"Detected file change from '{self.file_being_waited_on}' to '{self.current_file}'. Triggering pending playlist load.")
                trigger_reload = True
            
            if trigger_reload:
                config = self.pending_playlist_config
                self.pending_playlist_config = None
                self.file_being_waited_on = None
                
                logger.info(f"Executing deferred playlist load: {len(config['files'])} files, start index {config['index']}.")
                # Terminate player if it was still somehow running 
                # (e.g. log showed next song but process still there, or it stopped but self.process wasn't None yet)
                if self.process and self.process.poll() is None:
                     self.terminate_player() # ensure clean state before reload
                
                # If MPlayer stopped on its own, self.process might be None already.
                # terminate_player handles self.process being None gracefully.
                # Call _execute_playlist_load regardless of whether terminate_player was called just now or earlier.
                self._execute_playlist_load(config['files'], config['index'])
                # After _execute_playlist_load, self.current_file and self.is_playing_media are updated by it.
                # The status returned below will reflect the new state.
                # Update current_mplayer_process_running as _execute_playlist_load starts a new process.
                current_mplayer_process_running = self.process is not None and self.process.poll() is None


        return {
            "is_mpv_running": current_mplayer_process_running,
            "current_file": self.current_file,
            "is_playing_media": self.is_playing_media,
            "is_paused": self.is_paused,
            "loop_mode": self.loop_mode
        }
        
    def _check_mplayer_log_for_current_file(self):
        """Check MPlayer log to determine the currently playing file"""
        if not os.path.exists(MPLAYER_LOG_PATH):
            return
            
        try:
            with open(MPLAYER_LOG_PATH, "r") as log_file:
                lines = log_file.readlines()
            
            if not lines:
                logger.warning("MPlayer log file is empty")
                return
                
            # Scan the log from the end to find the most recently played file
            for line in reversed(lines):
                if "Playing " in line and "/uploads/" in line:
                    try:
                        # Extract the full path string after "Playing "
                        full_path_in_log_start_idx = line.find("Playing ") + len("Playing ")
                        # Find the end of the path. MPlayer might add a period or other characters.
                        # We'll take everything until the end of the line for now, then use basename.
                        potential_full_path = line[full_path_in_log_start_idx:].strip()

                        # More robust cleaning of the path from log
                        # First, handle any trailing newline characters (actual newlines)
                        potential_full_path = potential_full_path.rstrip('\n')
                        
                        # Then handle the typical trailing period that MPlayer adds
                        if potential_full_path.endswith('.'):
                            potential_full_path = potential_full_path[:-1]
                            
                        # Handle MPlayer version info that might be captured as part of the line
                        if "MPlayer" in potential_full_path:
                            potential_full_path = potential_full_path.split("MPlayer")[0].strip()
                        
                        # Now extract just the filename
                        new_file = os.path.basename(potential_full_path)
                        
                        # Verify this is a real file (sanity check)
                        # Construct the expected full path on disk for verification
                        expected_disk_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', new_file)
                        if os.path.exists(expected_disk_path):
                            # Check if the current file has changed
                            if new_file != self.current_file:
                                logger.info(f"File change detected in MPlayer log: {new_file} (was: {self.current_file})")
                                self.current_file = new_file
                            break 
                        else:
                            # This is where the "Found filename in log that doesn't exist" warning originates.
                            # If new_file is just the basename, and it's not found, the issue is that
                            # MPlayer is reporting a file that truly isn't in the uploads folder,
                            # or the PROJECT_ROOT or 'app/uploads' path components are incorrect,
                            # or new_file itself is still malformed (e.g. hidden characters not stripped).
                            logger.warning(f"Found filename in log '{new_file}' (from path '{potential_full_path}') that doesn't exist at expected location '{expected_disk_path}'")
                    except Exception as e:
                        logger.error(f"Error parsing filename from log line: {line.strip()}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error checking MPlayer log for current file: {e}")

    def load_playlist(self, playlist_files, start_index=0):
        if not playlist_files:
            logger.warning("Empty playlist provided to load_playlist. Stopping player.")
            self.stop() 
            self.pending_playlist_config = None 
            self.file_being_waited_on = None
            return True 

        # The writing of temp_playlist.txt is now fully handled by _execute_playlist_load.
        # It will use playlist_files and start_index to create the correctly ordered temp file.

        current_active_loop_mode = self.loop_mode 

        if current_active_loop_mode == 'playlist':
            if self.is_playing_media and self.current_file:
                # Playlist mode, and a file is currently playing.
                # Defer the actual MPlayer restart until the current song finishes.
                self.pending_playlist_config = {'files': list(playlist_files), 'index': start_index}
                self.file_being_waited_on = self.current_file 
                logger.info(f"Playlist updated. Changes for {len(playlist_files)} files (target start index {start_index}) will apply after current file '{self.current_file}' finishes.")
                return True
            else:
                # Playlist mode, but nothing is playing or current_file is not set.
                logger.info("Playlist mode: No current file playing or player stopped. Starting new playlist immediately.")
                return self._execute_playlist_load(playlist_files, start_index)
        else:
            # Not in playlist loop mode (e.g., 'none' or 'file'). 
            logger.info(f"Current mode is '{current_active_loop_mode}'. Loading new playlist. Player will operate according to self.loop_mode ('{self.loop_mode}') for this load.")
            
            # _execute_playlist_load will handle terminating any old process if necessary
            # and will use the current self.loop_mode to configure MPlayer.
            return self._execute_playlist_load(playlist_files, start_index)

    def _execute_playlist_load(self, playlist_files, start_index=0):
        if self.process and self.process.poll() is None:
            logger.info("Terminating existing MPlayer before executing new playlist load.")
            self.terminate_player()

        if not playlist_files:
            logger.warning("Playlist is empty in _execute_playlist_load. MPlayer will not be started.")
            self.current_file = None 
            self.is_playing_media = False
            return True 

        self._ensure_mplayer_executable()
        
        if not os.path.exists(MPLAYER_FIFO_PATH):
            self._setup_fifo()

        ordered_files_for_tempfile_basenames = []
        actual_start_filename_basename = None

        if not (0 <= start_index < len(playlist_files)) and playlist_files:
            logger.warning(f"Provided start_index {start_index} is out of bounds for playlist of length {len(playlist_files)}. Defaulting to index 0.")
            start_index = 0
        
        if playlist_files:
            raw_ordered_list = playlist_files[start_index:] + playlist_files[:start_index]
            
            # Filter out non-existent files
            for f_basename in raw_ordered_list:
                if os.path.exists(os.path.join(PROJECT_ROOT, 'app', 'uploads', f_basename)):
                    ordered_files_for_tempfile_basenames.append(f_basename)
                else:
                    logger.warning(f"File '{f_basename}' not found in uploads. Removing from current playlist session.")
            
            if not ordered_files_for_tempfile_basenames:
                logger.error("No valid, existing files found in the playlist to play after filtering.")
                self.current_file = None
                self.is_playing_media = False
                return True 
            
            actual_start_filename_basename = ordered_files_for_tempfile_basenames[0]
        else:
            logger.error("Playlist is empty, cannot determine a start file (should have been caught earlier).")
            return False

        temp_playlist_path = os.path.join(PROJECT_ROOT, "temp_playlist.txt")
        try:
            with open(temp_playlist_path, 'w') as f:
                for idx, file_item_basename in enumerate(ordered_files_for_tempfile_basenames):
                    full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', file_item_basename)
                    if idx < len(ordered_files_for_tempfile_basenames) - 1:
                        f.write(f"{full_path}\n")  # Use an actual newline character
                    else:
                        f.write(f"{full_path}")
            logger.info(f"Successfully wrote {len(ordered_files_for_tempfile_basenames)} items to '{temp_playlist_path}', starting with '{actual_start_filename_basename}'.")
        except Exception as e:
            logger.error(f"Failed to write temporary playlist file '{temp_playlist_path}': {e}")
            return False

        actual_start_file_full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', actual_start_filename_basename)

        target_device = os.getenv("KTV_TARGET_DEVICE", "laptop")
        cmd = ["mplayer", "-slave", "-input", f"file={MPLAYER_FIFO_PATH}", "-quiet", "-nolirc"]

        if target_device == "raspberrypi":
            cmd.extend(["-vo", "fbdev", "-fbdev", "/dev/fb0", "-x", "240", "-y", "320", "-bpp", "16", "-vf", "scale=240:320"])
        else: 
            cmd.extend(["-vo", "x11"])
        
        if self.loop_mode == 'playlist':
            cmd.extend(["-loop", "0"])
            cmd.extend(["-playlist", temp_playlist_path])
            logger.info(f"Configuring MPlayer for playlist mode with: -loop 0 -playlist {temp_playlist_path}")
        elif self.loop_mode == 'file':
            cmd.append(actual_start_file_full_path)
            cmd.extend(["-loop", "0"])
            logger.info(f"Configuring MPlayer for file loop mode with: {actual_start_filename_basename} -loop 0")
        elif self.loop_mode == 'none':
            cmd.extend(["-playlist", temp_playlist_path]) # Plays through the playlist once
            logger.info(f"Configuring MPlayer for 'none' loop mode (play playlist once) with: -playlist {temp_playlist_path}")
        else:
            logger.error(f"Unknown loop_mode '{self.loop_mode}' in _execute_playlist_load. Defaulting to playing playlist once.")
            cmd.extend(["-playlist", temp_playlist_path])

        try:
            initial_log_line_for_current_file = f"Playing {actual_start_file_full_path}.\n"  # Use actual newline character
            
            with open(MPLAYER_LOG_PATH, "w") as log_file:
                log_file.write(initial_log_line_for_current_file)
                logger.debug(f"Attempting to start MPlayer with command: {' '.join(cmd)}")
                self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            
            time.sleep(0.2) 

            if self.process and self.process.poll() is None:
                self.current_file = actual_start_filename_basename
                self.is_playing_media = True
                self.is_paused = False
                logger.info(f"MPlayer started/restarted. Current file set to: '{self.current_file}', Playing: {self.is_playing_media}, Mode: {self.loop_mode}")
            else:
                logger.error("MPlayer process failed to start or exited immediately.")
                # ... (log reading logic from previous thought if desired) ...
                self.current_file = None 
                self.is_playing_media = False
                self.process = None 
                return False
            return True
        except Exception as e:
            logger.error(f"Critical error in _execute_playlist_load: {e}", exc_info=True)
            # ... (cleanup logic from previous thought if desired) ...
            self.process = None
            self.current_file = None
            self.is_playing_media = False
            return False

    def playlist_next(self):
        """Advance to the next item in the playlist if in playlist mode using MPlayer's native playlist navigation."""
        if self.loop_mode == 'playlist' and self.process and self.process.poll() is None:
            # Use MPlayer's native playlist navigation
            logger.info("Sending pt_step 1 to MPlayer for next track.")
            return self._send_command("pt_step 1")
        else:
            logger.warning("playlist_next called but not in playlist mode or MPlayer not running.")
            return False

    def playlist_prev(self):
        """Go to the previous item in the playlist if in playlist mode using MPlayer's native playlist navigation."""
        if self.loop_mode == 'playlist' and self.process and self.process.poll() is None:
            logger.info("Sending pt_step -1 to MPlayer for previous track.")
            return self._send_command("pt_step -1")
        else:
            logger.warning("playlist_prev called but not in playlist mode or MPlayer not running.")
            return False

    def set_loop_mode(self, mode):
        """
        Set the loop mode for MPlayer.
        
        Args:
            mode (str): The loop mode ('none', 'file', or 'playlist').
            
        Returns:
            bool: True if the mode was set successfully, False otherwise.
        """
        if mode not in ['none', 'file', 'playlist']:
            logger.warning(f"Invalid loop mode specified: {mode}. Must be 'none', 'file', or 'playlist'.")
            return False
            
        if self.loop_mode == mode:
            # logger.info(f"Loop mode is already {mode}. No change made.") # Optional: reduce noise
            return True

        logger.info(f"Setting loop mode from '{self.loop_mode}' to '{mode}'.")
        self.loop_mode = mode
        
        # The new loop mode will be applied the next time media is loaded 
        # (e.g., via load_file, load_playlist, or when a pending playlist config is applied).
        # No immediate player restart is done here to keep this method simple.
        # If an immediate change is desired while playing, the user/frontend might need to trigger a reload.
        return True

    def get_loop_status(self):
        return {
            "loop_file": self.loop_mode == 'file',
            "loop_playlist": self.loop_mode == 'playlist',
            "loop_mode": self.loop_mode
        }
