import subprocess
import os
import time
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MPLAYER_LOG_PATH = os.path.join(PROJECT_ROOT, "mplayer.log")

class MPlayerController:
    def __init__(self):
        self.process = None
        self.current_file = None
        self.is_playing_media = False
        self.loop_mode = 'none'  # Track loop mode: 'none', 'file', 'playlist'
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
        
        cmd = [
            "mplayer",
            "-vo", "x11",  # Use X11 output instead of framebuffer for GUI environments
        ]
        
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
                self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            self.current_file = filepath
            self.is_playing_media = True
            return True
        except Exception as e:
            logger.error(f"Failed to start MPlayer: {e}")
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
        # Check MPlayer log file to determine if the file has changed
        if self.process is not None and self.process.poll() is None and self.loop_mode == 'playlist':
            self._check_mplayer_log_for_current_file()
            
        return {
            "is_mpv_running": self.process is not None and self.process.poll() is None,
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
                        # Extract filename from path in the log
                        start_idx = line.rfind("/uploads/") + 9  # 9 is length of "/uploads/"
                        if start_idx < 9:  # If "/uploads/" not found
                            continue
                            
                        # MPlayer may have additional text after the filename
                        # Common formats:
                        # - "Playing /path/to/uploads/filename.mp4"
                        # - "Playing /path/to/uploads/filename.mp4."
                        # - "Playing /path/to/uploads/filename.mp4 ..."
                        
                        # First try to find a space or newline after the filename
                        end_idx = -1
                        for marker in [" ", "\n", "."]:
                            pos = line.find(marker, start_idx)
                            if pos != -1 and (end_idx == -1 or pos < end_idx):
                                end_idx = pos
                        
                        if end_idx == -1:  # No delimiter found
                            end_idx = len(line)
                            
                        new_file = line[start_idx:end_idx].strip()
                        
                        # Verify this is a real file (sanity check)
                        if os.path.exists(os.path.join(PROJECT_ROOT, 'app', 'uploads', new_file)):
                            # Check if the current file has changed
                            if new_file != self.current_file:
                                logger.info(f"File change detected in MPlayer log: {new_file} (was: {self.current_file})")
                                self.current_file = new_file
                            break
                        else:
                            logger.warning(f"Found filename in log that doesn't exist: {new_file}")
                    except Exception as e:
                        logger.error(f"Error parsing filename from log line: {line.strip()}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error checking MPlayer log for current file: {e}")

    def load_playlist(self, playlist_files, start_index=0):
        if not playlist_files:
            logger.warning("Empty playlist provided.")
            return self.stop()
            
        # Create a temporary playlist
        if self.loop_mode == 'playlist':
            logger.info("Using playlist loop mode")
            return self._load_playlist_with_loop(playlist_files, start_index)
        
        return self.load_file(playlist_files[start_index])
    
    def _load_playlist_with_loop(self, playlist_files, start_index=0):
        temp_playlist_path = os.path.join(PROJECT_ROOT, "temp_playlist.txt")
        
        # Create the playlist file
        try:
            # Generate playlist without rotation - let MPlayer play from any index
            with open(temp_playlist_path, 'w') as f:
                for file in playlist_files:
                    full_path = os.path.join(PROJECT_ROOT, 'app', 'uploads', file)
                    f.write(f"{full_path}\n")
                    
            logger.info(f"Created temporary playlist with {len(playlist_files)} files, will start at index {start_index}")
            
            # Start MPlayer with the playlist and loop
            self._ensure_mplayer_executable()
            
            # Determine the correct file to play
            start_file = None
            if 0 <= start_index < len(playlist_files):
                start_file = os.path.join(PROJECT_ROOT, 'app', 'uploads', playlist_files[start_index])
            
            # Only terminate if we're not already playing or if explicitly requested to restart
            terminate_needed = True
            if self.process and self.process.poll() is None and self.current_file:
                # If we're already playing a file in the playlist and it's still valid,
                # don't terminate - just let the current file finish playing
                if self.current_file in playlist_files:
                    terminate_needed = False
                    logger.info(f"Playlist updated but keeping current playback of {self.current_file}")
            
            if terminate_needed:
                if self.process:
                    self.terminate_player()
                    
                cmd = [
                    "mplayer", 
                    "-vo", "x11",
                    "-quiet",
                    "-nolirc",
                    "-loop", "0",  # Loop infinitely
                ]
                
                if start_file:
                    # Specify the initial file and then use the playlist for future files
                    cmd.extend([start_file, "-playlist", temp_playlist_path])
                else:
                    # Just use the playlist from the beginning
                    cmd.extend(["-playlist", temp_playlist_path])
                
                # Clear log file so we can track what's currently playing
                with open(MPLAYER_LOG_PATH, "w") as log_file:
                    # First write a line that indicates the starting file
                    if start_file:
                        log_file.write(f"Playing {start_file}\n")
                    self.process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                    
                if start_index < len(playlist_files):
                    self.current_file = playlist_files[start_index]
                    self.is_playing_media = True
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create or play playlist: {e}")
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
