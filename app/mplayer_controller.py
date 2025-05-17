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
                # logger.warning("MPlayer log file is empty") # Can be too noisy if checked frequently
                return
                
            # Scan the log from the end to find the most recently played file
            for line in reversed(lines):
                if "Playing " in line and "/uploads/" in line: # Ensure it's one of our uploaded files
                    try:
                        # Extract the full path string after "Playing "
                        full_path_in_log_start_idx = line.find("Playing ") + len("Playing ")
                        # Find the end of the path. MPlayer might add a period or other characters.
                        # We'll take everything until the end of the line for now, then use basename.
                        potential_full_path = line[full_path_in_log_start_idx:].strip()

                        # Remove common trailing characters MPlayer might add, like '.'
                        if potential_full_path.endswith('.'):
                            potential_full_path = potential_full_path[:-1]
                        
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
                                # If a file change is detected and we were waiting for a specific file to end (for pending playlist),
                                # this current_file update is what get_playback_status will use to trigger the pending load.
                            break 
                        else:
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

        # Deferral logic: if media is playing and we are not already waiting for a file to finish
        # The self.loop_mode for the upcoming playlist is already set by the API before this call.
        if self.is_playing_media and self.current_file and self.file_being_waited_on is None:
            logger.info(f"Current media '{self.current_file}' is playing. Deferring load of new playlist ({len(playlist_files)} files, start index {start_index}). Loop mode for new playlist will be '{self.loop_mode}'.")
            self.pending_playlist_config = {'files': list(playlist_files), 'index': start_index}
            self.file_being_waited_on = self.current_file 
            return True
        else:
            # Execute immediately (nothing playing, or already in a deferred state that's now processing)
            logger.info(f"Executing playlist load immediately. Target loop mode: '{self.loop_mode}'.")
            # _execute_playlist_load will terminate any existing MPlayer instance if necessary.
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
            
        # Determine the actual starting filename and reorder playlist for temp file
        if not (0 <= start_index < len(playlist_files)):
            logger.warning(f"Provided start_index {start_index} is out of bounds for playlist of length {len(playlist_files)}. Defaulting to index 0.")
            start_index = 0
        
        actual_start_filename = playlist_files[start_index]
        # Create the reordered list for temp_playlist.txt: items from start_index to end, then items from 0 to start_index-1
        reordered_playlist_for_file = playlist_files[start_index:] + playlist_files[:start_index]

        # Write the reordered playlist to temp_playlist.txt (still useful for 'none' mode or debugging)
        temp_playlist_path = os.path.join(PROJECT_ROOT, "temp_playlist.txt")
        if not reordered_playlist_for_file: 
            logger.error("Reordered playlist is empty, cannot proceed.")
            return False
            
        try:
            with open(temp_playlist_path, 'w') as f:
                for file_item in reordered_playlist_for_file:
                    full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', file_item)
                    if not os.path.exists(full_path):
                        logger.warning(f"File {full_path} in reordered playlist does not exist. MPlayer might skip it or error if passed directly.")
                    f.write(f"{full_path}\n") # Write actual newline
            logger.info(f"Successfully wrote reordered playlist ({len(reordered_playlist_for_file)} items, starting with {actual_start_filename}) to '{temp_playlist_path}'.")
        except Exception as e:
            logger.error(f"Failed to write reordered temporary playlist file '{temp_playlist_path}': {e}")
            return False
        
        # Base MPlayer command
        cmd = ["mplayer", "-slave", "-input", f"file={MPLAYER_FIFO_PATH}", "-quiet", "-nolirc"]

        target_device = os.getenv("KTV_TARGET_DEVICE", "laptop")
        if target_device == "raspberrypi":
            cmd.extend(["-vo", "fbdev", "-fbdev", "/dev/fb0", "-x", "240", "-y", "320", "-bpp", "16", "-vf", "scale=240:320"])
        else: 
            cmd.extend(["-vo", "x11"])
        
        # Add loop mode and playlist/file arguments
        # self.loop_mode should be set by API calls prior to load_playlist/_execute_playlist_load
        if self.loop_mode == 'playlist':
            cmd.extend(["-loop", "0"]) # Loop the entire sequence of files provided on CLI
            logger.info("Configuring MPlayer for playlist loop (files on CLI with -loop 0).")
            
            paths_for_cmd = []
            # Use reordered_playlist_for_file so MPlayer starts with actual_start_filename
            for file_item in reordered_playlist_for_file: 
                full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', file_item)
                if os.path.exists(full_path):
                    paths_for_cmd.append(full_path)
                else:
                    # This file won't be added to MPlayer's command line arguments
                    logger.warning(f"File {full_path} for playlist CLI command does not exist. Skipping.")
            
            if not paths_for_cmd:
                logger.error("Playlist loop mode: No valid files to play (all files missing or playlist empty after filtering?). Aborting MPlayer start.")
                self.current_file = None
                self.is_playing_media = False
                return False
            cmd.extend(paths_for_cmd)

        elif self.loop_mode == 'none': # Play one single file once, then stop/end.
            logger.info(f"Configuring MPlayer to play single file once: '{actual_start_filename}'.")
            file_to_play_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', actual_start_filename)
            if os.path.exists(file_to_play_path):
                cmd.append(file_to_play_path) # Add only the single file to play, no -loop, no -playlist
            else:
                logger.error(f"None loop mode: File '{file_to_play_path}' for single play not found. Aborting MPlayer start.")
                self.current_file = None
                self.is_playing_media = False
                return False

        elif self.loop_mode == 'file':
            logger.info(f"Configuring MPlayer for single file loop: '{actual_start_filename}' (file on CLI with -loop 0).")
            cmd.extend(["-loop", "0"])
            file_to_play_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', actual_start_filename)
            if os.path.exists(file_to_play_path):
                cmd.append(file_to_play_path)
            else:
                logger.error(f"File loop mode: File '{file_to_play_path}' for looping not found. Aborting MPlayer start.")
                self.current_file = None
                self.is_playing_media = False
                return False
        else: 
            logger.error(f"Unexpected loop_mode: '{self.loop_mode}'. Defaulting to playing playlist once via -playlist arg.")
            cmd.extend(["-playlist", temp_playlist_path])


        # Pre-seed log for _check_mplayer_log_for_current_file
        # actual_start_filename is the first file MPlayer will play in all configured modes.
        initial_log_line_for_current_file = ""
        if actual_start_filename: 
            expected_first_logged_file_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', actual_start_filename)
            # Check if this file would actually be played (e.g. exists and was added to paths_for_cmd or is in temp_playlist.txt)
            # For simplicity, we just check existence here; MPlayer will log what it actually plays.
            if os.path.exists(expected_first_logged_file_path):
                 initial_log_line_for_current_file = f"Playing {expected_first_logged_file_path}\\n"
            else:
                logger.warning(f"Cannot pre-seed log: starting file '{expected_first_logged_file_path}' does not exist.")
        
        try:
            with open(MPLAYER_LOG_PATH, "w") as log_file:
                if initial_log_line_for_current_file:
                    log_file.write(initial_log_line_for_current_file)
                logger.debug(f"Attempting to start MPlayer with command: {' '.join(cmd)}")
                self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            
            time.sleep(0.2) # Brief pause for MPlayer to start

            if self.process and self.process.poll() is None:
                # Set current_file to the one MPlayer is expected to start with.
                # _check_mplayer_log_for_current_file will verify/update this based on actual log.
                self.current_file = actual_start_filename 
                self.is_playing_media = True
                self.is_paused = False
                logger.info(f"MPlayer started/restarted. Expected start file: '{self.current_file}', Playing: {self.is_playing_media}, Loop Mode: {self.loop_mode}")
            else:
                logger.error("MPlayer process failed to start or exited immediately after attempting to load playlist.")
                self.current_file = None 
                self.is_playing_media = False
                self.process = None 
                return False
            return True
        except Exception as e:
            logger.error(f"Critical error in _execute_playlist_load: {e}", exc_info=True)
            if self.process:
                try:
                    if self.process.poll() is None: self.process.kill()
                except: pass 
            self.process = None
            self.current_file = None
            self.is_playing_media = False
            return False

    def playlist_next(self):
        logger.warning("MPlayer does not support internal playlist control.")
        return False

    def playlist_prev(self):
        logger.warning("MPlayer does not support internal playlist control.")
        return False

    def set_loop_mode(self, mode):
        """
        Set the loop mode for MPlayer.
        
        Args:
            mode (str): The loop mode ('none', 'file', or 'playlist').
            
        Returns:
            bool: True if the mode was set, False otherwise.
        """
        if mode not in ['none', 'file', 'playlist']:
            logger.warning(f"Invalid loop mode: {mode}")
            return False
            
        self.loop_mode = mode
        logger.info(f"Loop mode set to: {mode}")
        return True

    def get_loop_status(self):
        return {
            "loop_file": self.loop_mode == 'file',
            "loop_playlist": self.loop_mode == 'playlist',
            "loop_mode": self.loop_mode
        }
