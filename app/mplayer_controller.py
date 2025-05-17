import subprocess
import os
import time
import logging
from dotenv import load_dotenv # Add this import

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MPLAYER_LOG_PATH = os.path.join(PROJECT_ROOT, "mplayer.log")
load_dotenv(os.path.join(PROJECT_ROOT, '.env')) # Load .env file

class MPlayerController:
    def __init__(self):
        self.process = None
        self.current_file = None
        self.is_playing_media = False
        self.loop_mode = 'none'  # Track loop mode: 'none', 'file', 'playlist'
        self.pending_playlist_config = None # Stores {'files': list_of_files, 'index': start_index}
        self.file_being_waited_on = None  # Stores the filename of the song whose completion triggers reload
        logger.info(f"MPlayerController initialized. Log path: {MPLAYER_LOG_PATH}")

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

        logger.info(f"Starting MPlayer with file: {full_path}")
        
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
            return True
        except Exception as e:
            logger.error(f"Failed to start MPlayer in load_file: {e}")
            if os.path.exists(MPLAYER_LOG_PATH):
                logger.error(f"MPLAYER_LOG_PATH size on Popen failure in load_file: {os.path.getsize(MPLAYER_LOG_PATH)} bytes.")
            else:
                logger.error(f"MPLAYER_LOG_PATH does not exist on Popen failure in load_file.")
            return False

    def play(self):
        logger.warning("MPlayer does not support pause/resume control in this implementation.")
        return False

    def pause(self):
        logger.warning("MPlayer does not support pause/resume control in this implementation.")
        return False

    def toggle_pause(self):
        return self.pause() if self.is_playing_media else self.play()

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
            self.pending_playlist_config = None # Clear any pending task
            self.file_being_waited_on = None
            return True 

        # Always write/update the temporary playlist file first.
        temp_playlist_path = os.path.join(PROJECT_ROOT, "temp_playlist.txt")
        try:
            with open(temp_playlist_path, 'w') as f:
                for file_item in playlist_files:
                    full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', file_item)
                    f.write(f"{full_path}\\n")
            logger.info(f"Successfully wrote {len(playlist_files)} items to '{temp_playlist_path}'.")
        except Exception as e:
            logger.error(f"Failed to write temporary playlist file '{temp_playlist_path}': {e}")
            return False

        if self.loop_mode == 'playlist':
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
                if self.process and self.process.poll() is None: self.terminate_player()
                return self._execute_playlist_load(playlist_files, start_index)
        else:
            # Not in playlist loop mode. Switch to playlist mode and load.
            logger.info(f"Not in playlist loop mode (current: {self.loop_mode}). Switching to playlist mode and loading.")
            self.loop_mode = 'playlist' 
            if self.process and self.process.poll() is None: self.terminate_player()
            return self._execute_playlist_load(playlist_files, start_index)

    def _execute_playlist_load(self, playlist_files, start_index=0):
        # This method now contains the logic to start/restart MPlayer with a given playlist.
        # It assumes temp_playlist.txt is already written by load_playlist.
        temp_playlist_path = os.path.join(PROJECT_ROOT, "temp_playlist.txt")

        # Ensure any previous MPlayer instance is terminated before starting a new one.
        if self.process and self.process.poll() is None:
            logger.info("Terminating existing MPlayer before executing new playlist load.")
            self.terminate_player() # Resets current_file, is_playing_media, process

        if not playlist_files:
            logger.warning("Playlist is empty in _execute_playlist_load. MPlayer will not be started.")
            self.current_file = None # Ensure state is clean
            self.is_playing_media = False
            return True 

        self._ensure_mplayer_executable()
        
        effective_start_filename = None
        effective_start_file_path = None

        if 0 <= start_index < len(playlist_files):
            effective_start_filename = playlist_files[start_index]
        elif playlist_files: 
            logger.warning(f"Provided start_index {start_index} is out of bounds for playlist of length {len(playlist_files)}. Defaulting to index 0.")
            effective_start_filename = playlist_files[0]
            # start_index = 0 # Correct start_index for state update later - not strictly needed here as it's just for MPlayer cmd
        else: 
            logger.error("Playlist is empty, cannot determine a start file.")
            return False

        if effective_start_filename:
            effective_start_file_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', effective_start_filename)
            if not os.path.exists(effective_start_file_path):
                logger.warning(f"Specified start file '{effective_start_file_path}' not found. Attempting to start playlist from beginning.")
                # Fallback to the first file in the playlist if the specified start_index file doesn't exist
                if playlist_files: # Should always be true if effective_start_filename was set
                    effective_start_filename = playlist_files[0]
                    effective_start_file_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', effective_start_filename)
                    if not os.path.exists(effective_start_file_path):
                        logger.error(f"First file of playlist '{effective_start_file_path}' also not found. Aborting MPlayer start.")
                        self.current_file = None
                        self.is_playing_media = False
                        return False
                else: # Should not happen if initial playlist_files check passed
                    logger.error("Playlist became empty while trying to find a valid start file.")
                    return False
        
        target_device = os.getenv("KTV_TARGET_DEVICE", "laptop")
        cmd = ["mplayer"]

        if target_device == "raspberrypi":
            cmd.extend(["-vo", "fbdev", "-fbdev", "/dev/fb0", "-x", "240", "-y", "320", "-bpp", "16", "-vf", "scale=240:320"])
            logger.info("Configuring MPlayer for Raspberry Pi (framebuffer) - playlist execution")
        else: 
            cmd.extend(["-vo", "x11"])
            logger.info("Configuring MPlayer for Laptop (X11) - playlist execution")
        
        cmd.extend(["-quiet", "-nolirc", "-loop", "0"])

        if effective_start_file_path and os.path.exists(effective_start_file_path):
            cmd.append(effective_start_file_path)
            cmd.extend(["-playlist", temp_playlist_path])
            logger.info(f"MPlayer will start with '{effective_start_filename}' and then use playlist '{temp_playlist_path}'.")
        elif playlist_files: # Should only happen if initial effective_start_file_path was bad but playlist_files[0] is good
            logger.info(f"MPlayer will start with playlist '{temp_playlist_path}' from its beginning as specific start file was invalid/missing.")
            cmd.extend(["-playlist", temp_playlist_path])
            effective_start_filename = playlist_files[0] # Ensure this reflects actual start
        else:
            logger.error("Cannot start MPlayer: playlist is empty and no valid start file could be determined.")
            self.current_file = None
            self.is_playing_media = False
            return False

        try:
            initial_log_line_for_current_file = ""
            # Determine the file MPlayer is expected to log as "Playing" first.
            # If cmd includes a direct file, MPlayer logs that. 
            # If cmd only has -playlist, MPlayer logs the first file from the playlist.
            expected_first_logged_file_path = ""
            if effective_start_file_path and os.path.exists(effective_start_file_path) and cmd[0] == "mplayer" and len(cmd) > 1 and cmd[-2] != "-playlist": # Check if a file is directly passed before -playlist
                 # This logic is a bit fragile; relies on cmd structure.
                 # A more robust way is to see if effective_start_file_path is in cmd before "-playlist"
                 try:
                     idx_playlist_arg = cmd.index("-playlist")
                     # Check if effective_start_file_path is in cmd before idx_playlist_arg
                     if effective_start_file_path in cmd[:idx_playlist_arg]:
                         expected_first_logged_file_path = effective_start_file_path
                 except ValueError: # -playlist not found, means only one file or direct list
                     if effective_start_file_path in cmd:
                        expected_first_logged_file_path = effective_start_file_path
            
            if not expected_first_logged_file_path and playlist_files: # Fallback if MPlayer starts directly from playlist file
                expected_first_logged_file_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', playlist_files[0])


            if expected_first_logged_file_path:
                 initial_log_line_for_current_file = f"Playing {expected_first_logged_file_path}\\n"
            
            with open(MPLAYER_LOG_PATH, "w") as log_file:
                if initial_log_line_for_current_file: # Pre-seed log for _check_mplayer_log_for_current_file
                    log_file.write(initial_log_line_for_current_file)
                logger.debug(f"Attempting to start MPlayer with command: {' '.join(cmd)}")
                self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            
            time.sleep(0.2) 

            if self.process and self.process.poll() is None:
                self.current_file = effective_start_filename 
                self.is_playing_media = True
                logger.info(f"MPlayer started/restarted. Current file set to: '{self.current_file}', Playing: {self.is_playing_media}")
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
