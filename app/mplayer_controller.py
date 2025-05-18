import subprocess
import os
import time
import logging
from dotenv import load_dotenv # Environment variable management

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MPLAYER_LOG_PATH = os.path.join(PROJECT_ROOT, "mplayer.log")
MPLAYER_FIFO_PATH = os.path.join(PROJECT_ROOT, "mplayer.fifo") # FIFO pipe for MPlayer communication
load_dotenv(os.path.join(PROJECT_ROOT, '.env')) # Initialize environment configuration

class MPlayerController:
    def __init__(self):
        self.process = None
        self.current_file = None
        self.is_playing_media = False
        self.is_paused = False  # Indicates current pause state
        self.loop_mode = 'none'  # Controls playback repetition: 'none', 'file', or 'playlist'
        self.pending_playlist_config = None # Stores deferred playlist configuration: {'files': list_of_files, 'index': start_index}
        self.file_being_waited_on = None  # Tracks the file whose completion triggers playlist reload
        self._setup_fifo()  # Initialize FIFO communication channel for MPlayer
        logger.info(f"MPlayerController initialized. Log path: {MPLAYER_LOG_PATH}, FIFO path: {MPLAYER_FIFO_PATH}")

    def _setup_fifo(self):
        """Establishes FIFO (named pipe) for MPlayer slave mode communication."""
        # Remove any existing FIFO to prevent conflicts
        if os.path.exists(MPLAYER_FIFO_PATH):
            try:
                os.unlink(MPLAYER_FIFO_PATH)
                logger.debug(f"Removed existing FIFO pipe: {MPLAYER_FIFO_PATH}")
            except OSError as e:
                logger.error(f"Failed to remove existing FIFO pipe: {e}")
        
        try:
            # Establish new control channel
            os.mkfifo(MPLAYER_FIFO_PATH)
            logger.info(f"Created MPlayer FIFO pipe at: {MPLAYER_FIFO_PATH}")
        except OSError as e:
            logger.error(f"Failed to create FIFO pipe: {e}")

    def _send_command(self, command):
        """Sends a control command to MPlayer via the FIFO channel."""
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
        """Checks for the presence of the MPlayer binary in the system environment."""
        if subprocess.call(["which", "mplayer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            raise FileNotFoundError("MPlayer executable not found.")

    def start_player(self):
        """No-op for MPlayer; included for interface compatibility with other controllers."""
        return True

    def load_file(self, filepath, transition="fade"):
        """Loads and starts playback of a specified media file."""
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
            rpi_options = [
                "-vo", "fbdev:/dev/fb0",
                "-x", "240",
                "-y", "320",
                "-bpp", "16",
                "-vf", "scale=240:320"
            ]
            
            # Configurable performance options from .env
            enable_framedrop = os.getenv("MPLAYER_RPI_ENABLE_FRAMEDROP", "true").lower() == "true"
            lavdopts_string = os.getenv("MPLAYER_RPI_LAVDOPTS", "lowres=1:fast:skiploopfilter=all")

            if enable_framedrop:
                rpi_options.append("-framedrop")
            
            if lavdopts_string and lavdopts_string.strip():
                rpi_options.extend(["-lavdopts", lavdopts_string.strip()])
            
            cmd.extend(rpi_options)
            logger.info(f"Configuring MPlayer for Raspberry Pi (framebuffer) with options: {' '.join(rpi_options)}")
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
                    logger.warning(f"Diagnostic: Log file exists but contains no data after process initialization.")
            else:
                logger.warning(f"Critical diagnostic: Expected log file missing after process initialization.")

            self.current_file = filepath
            self.is_playing_media = True
            self.is_paused = False
            return True
        except Exception as e:
            logger.error(f"Failed to start MPlayer in load_file: {e}")
            if os.path.exists(MPLAYER_LOG_PATH):
                logger.error(f"Diagnostic data: Log file size at failure point: {os.path.getsize(MPLAYER_LOG_PATH)} bytes.")
            else:
                logger.error(f"Diagnostic data: Log file creation failure detected alongside process initialization failure.")
            return False

    def play(self):
        """Starts or resumes playback depending on current state."""
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
        """Pauses playback, retaining current position."""
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
        """Toggles between play and pause states."""
        if not self.process or self.process.poll() is not None:
            logger.warning("Cannot toggle pause: MPlayer is not running")
            return False
            
        logger.info(f"Toggling pause state. Current state - is_paused: {self.is_paused}, is_playing_media: {self.is_playing_media}")
        if self._send_command("pause"):
            self.is_paused = not self.is_paused
            return True
        return False

    def stop(self):
        """Stops playback and terminates the MPlayer process."""
        return self.terminate_player()

    def terminate_player(self):
        """Terminates the MPlayer process and resets playback state."""
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
        """Returns a dictionary summarizing the current playback and process state."""
        current_mplayer_process_running = self.process is not None and self.process.poll() is None
        # Store the current file before log check for accurate change detection
        previous_file_state_before_log_check = self.current_file

        if current_mplayer_process_running and self.loop_mode == 'playlist':
            self._check_mplayer_log_for_current_file() # This might update self.current_file

        # Deferred playlist activation detection system
        if self.pending_playlist_config and self.file_being_waited_on:
            trigger_reload = False
            current_mplayer_process_still_running_after_log_check = self.process is not None and self.process.poll() is None

            if not current_mplayer_process_still_running_after_log_check: # Process termination trigger
                logger.info(f"MPlayer stopped while waiting for '{self.file_being_waited_on}' to finish. Triggering pending playlist load.")
                trigger_reload = True
            # Current file state reflects latest log analysis or None if player stopped
            # Activation occurs when detected file differs from monitored target
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
            "mplayer_is_running": current_mplayer_process_running,
            "current_file": self.current_file,
            "is_playing_media": self.is_playing_media,
            "is_paused": self.is_paused,
            "loop_mode": self.loop_mode
        }
        
    def _check_mplayer_log_for_current_file(self):
        """Parses the MPlayer log to determine the currently playing file."""
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
                        # Extract full path, accounting for MPlayer's potential path formatting variations
                        # Initial extraction captures everything after the "Playing " marker
                        potential_full_path = line[full_path_in_log_start_idx:].strip()

                        # Path normalization process:
                        # Step 1: Remove trailing newline characters
                        potential_full_path = potential_full_path.rstrip('\n')
                        
                        # Step 2: Handle MPlayer's characteristic trailing period
                        if potential_full_path.endswith('.'):
                            potential_full_path = potential_full_path[:-1]
                            
                        # Step 3: Filter out any MPlayer version information
                        if "MPlayer" in potential_full_path:
                            potential_full_path = potential_full_path.split("MPlayer")[0].strip()
                        
                        # Extract bare filename from normalized path
                        new_file = os.path.basename(potential_full_path)
                        
                        # File validation: Construct and verify expected filesystem location
                        # Ensures the extracted filename corresponds to an actual media file
                        expected_disk_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', new_file)
                        if os.path.exists(expected_disk_path):
                            # Update current file if a change is detected
                            if new_file != self.current_file:
                                logger.info(f"File change detected in MPlayer log: {new_file} (was: {self.current_file})")
                                self.current_file = new_file
                            break 
                        else:
                            # Diagnostic: Warn if log-reported file does not exist on disk
                            logger.warning(f"Found filename in log '{new_file}' (from path '{potential_full_path}') that doesn't exist at expected location '{expected_disk_path}'")
                    except Exception as e:
                        logger.error(f"Error parsing filename from log line: {line.strip()}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error checking MPlayer log for current file: {e}")

    def load_playlist(self, playlist_files, start_index=0):
        """Loads a playlist and starts playback according to the current loop mode."""
        if not playlist_files:
            logger.warning("Empty playlist provided to load_playlist. Stopping player.")
            self.stop() 
            self.pending_playlist_config = None 
            self.file_being_waited_on = None
            return True 

        # Playlist file generation is handled by _execute_playlist_load
        current_active_loop_mode = self.loop_mode 

        if current_active_loop_mode == 'playlist':
            if self.is_playing_media and self.current_file:
                # Queue playlist for activation after current file finishes
                self.pending_playlist_config = {'files': list(playlist_files), 'index': start_index}
                self.file_being_waited_on = self.current_file 
                logger.info(f"Playlist updated. Changes for {len(playlist_files)} files (target start index {start_index}) will apply after current file '{self.current_file}' finishes.")
            else:
                # Immediate execution path: No active playback to preserve
                logger.info("Playlist mode: No current file playing or player stopped. Starting new playlist immediately.")
                return self._execute_playlist_load(playlist_files, start_index)
        else:
            # Standard playlist loading for non-playlist loop modes
            logger.info(f"Current mode is '{current_active_loop_mode}'. Loading new playlist. Player will operate according to self.loop_mode ('{self.loop_mode}') for this load.")
            return self._execute_playlist_load(playlist_files, start_index)

    def _execute_playlist_load(self, playlist_files, start_index=0):
        """Executes the loading and playback of a playlist, handling file validation and process management."""
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
            # Reorder playlist to start at the specified index
            raw_ordered_list = playlist_files[start_index:] + playlist_files[:start_index]
            
            # Validate existence of each file in the playlist
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
                        f.write(f"{full_path}\n")  # Standard line separator
                    else:
                        f.write(f"{full_path}")  # No trailing newline for final entry
            logger.info(f"Successfully wrote {len(ordered_files_for_tempfile_basenames)} items to '{temp_playlist_path}', starting with '{actual_start_filename_basename}'.")
        except Exception as e:
            logger.error(f"Failed to write temporary playlist file '{temp_playlist_path}': {e}")
            return False

        actual_start_file_full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', actual_start_filename_basename)

        target_device = os.getenv("KTV_TARGET_DEVICE", "laptop")
        cmd = ["mplayer", "-slave", "-input", f"file={MPLAYER_FIFO_PATH}", "-quiet", "-nolirc"]

        if target_device == "raspberrypi":
            cmd.extend(["-vo", "fbdev:/dev/fb0", "-x", "240", "-y", "320", "-bpp", "16", "-vf", "scale=240:320"])
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
            # Pre-populate log with initial file marker for immediate status detection
            initial_log_line_for_current_file = f"Playing {actual_start_file_full_path}.\n"
            
            with open(MPLAYER_LOG_PATH, "w") as log_file:
                log_file.write(initial_log_line_for_current_file)
                logger.debug(f"Attempting to start MPlayer with command: {' '.join(cmd)}")
                self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            
            time.sleep(0.2)  # Brief initialization delay for process stability

            if self.process and self.process.poll() is None:
                # Process successfully launched; update state
                self.current_file = actual_start_filename_basename
                self.is_playing_media = True
                self.is_paused = False
                logger.info(f"MPlayer started/restarted. Current file set to: '{self.current_file}', Playing: {self.is_playing_media}, Mode: {self.loop_mode}")
            else:
                # Process launch failure; reset state and abort
                logger.error("MPlayer process failed to start or exited immediately.")
                self.current_file = None 
                self.is_playing_media = False
                self.process = None 
                return False
            return True
        except Exception as e:
            # Exception handling for process launch failures
            logger.error(f"Critical error in _execute_playlist_load: {e}", exc_info=True)
            self.process = None
            self.current_file = None
            self.is_playing_media = False
            return False

    def playlist_next(self):
        """Advances to the next playlist item using MPlayer's native navigation."""
        if self.loop_mode == 'playlist' and self.process and self.process.poll() is None:
            logger.info("Sending pt_step 1 to MPlayer for next track.")
            return self._send_command("pt_step 1")
        else:
            logger.warning("playlist_next called but not in playlist mode or MPlayer not running.")
            return False

    def playlist_prev(self):
        """Returns to the previous playlist item using MPlayer's native navigation."""
        if self.loop_mode == 'playlist' and self.process and self.process.poll() is None:
            logger.info("Sending pt_step -1 to MPlayer for previous track.")
            return self._send_command("pt_step -1")
        else:
            logger.warning("playlist_prev called but not in playlist mode or MPlayer not running.")
            return False

    def set_loop_mode(self, mode):
        """
        Sets the playback loop mode for MPlayer.
        Args:
            mode (str): Desired loop mode ('none', 'file', or 'playlist').
        Returns:
            bool: True if mode was set successfully, False otherwise.
        """
        if mode not in ['none', 'file', 'playlist']:
            logger.warning(f"Invalid loop mode specified: {mode}. Must be 'none', 'file', or 'playlist'.")
            return False
            
        if self.loop_mode == mode:
            # No action needed if already set
            return True

        logger.info(f"Setting loop mode from '{self.loop_mode}' to '{mode}'.")
        self.loop_mode = mode
        
        # Note: New loop mode is applied on next media load
        return True

    def get_loop_status(self):
        """Returns the current loop mode status as a dictionary."""
        return {
            "loop_file": self.loop_mode == 'file',
            "loop_playlist": self.loop_mode == 'playlist',
            "loop_mode": self.loop_mode
        }
