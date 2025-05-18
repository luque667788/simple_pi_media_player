from flask import Flask, request, jsonify, render_template, send_from_directory
import os # Import for operating system dependent functionalities
import json # Import for JSON manipulation
import time # Import for time-related functions
import atexit # Import for registering cleanup functions
import subprocess # Import for running external scripts/commands

# Custom logging configuration
from .logging_config import setup_logging

# Use MPlayerController for media playback management
from .mplayer_controller import MPlayerController

# Initialize Flask application with specified template and static directories
app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Application Configuration ---
# Dynamically determine the project root directory (assumes main.py is in 'app')
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'app', 'uploads')
PLAYLIST_FILE = os.path.join(PROJECT_ROOT, 'playlist.json') # Path for persistent playlist storage
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # Set upload limit to 300 MB

# --- Logging Setup ---
# Initialize logging with custom configuration and log file
setup_logging(app, log_filename="server.log")
logger = app.logger # Use Flask's logger instance

# --- Media Playlist State (In-memory for runtime operations) ---
media_playlist = [] # Stores filenames relative to UPLOAD_FOLDER
current_media_index = -1
is_playing = False
loop_playlist = False
current_loop_mode = 'none'  # Tracks the last set loop mode
# current_transition = "fade" # Placeholder for future transition effects

# --- Playlist Persistence Utilities ---
def load_playlist_from_file():
    """Loads the playlist from persistent storage, or initializes an empty list if unavailable."""
    global media_playlist
    try:
        if os.path.exists(PLAYLIST_FILE):
            with open(PLAYLIST_FILE, 'r') as f:
                loaded_playlist = json.load(f)
                if isinstance(loaded_playlist, list):
                    media_playlist = loaded_playlist
                    logger.info(f"Playlist loaded from {PLAYLIST_FILE}: {media_playlist}")
                else:
                    logger.warning(f"Invalid playlist format in {PLAYLIST_FILE}. Starting with empty playlist.")
                    media_playlist = []
        else:
            logger.info(f"{PLAYLIST_FILE} not found. Starting with empty playlist.")
            media_playlist = []
    except Exception as e:
        logger.error(f"Error loading playlist from {PLAYLIST_FILE}: {e}. Starting with empty playlist.")
        media_playlist = []

def save_playlist_to_file():
    """Persists the current playlist to disk as JSON."""
    try:
        with open(PLAYLIST_FILE, 'w') as f:
            json.dump(media_playlist, f, indent=4)
        logger.info(f"Playlist saved to {PLAYLIST_FILE}")
    except Exception as e:
        logger.error(f"Error saving playlist to {PLAYLIST_FILE}: {e}")

# Load playlist at application startup
load_playlist_from_file()

# --- MPlayer Controller Instance ---
mplayer = MPlayerController() # Instantiate controller for MPlayer operations

# --- Playlist Synchronization Utility ---
def synchronize_playlist_with_uploads():
    """
    Scans the upload directory for valid media files and synchronizes the in-memory playlist
    and persistent playlist file accordingly.
    """
    global media_playlist
    logger.info("Synchronizing playlist with files in upload folder...")
    
    if not os.path.exists(UPLOAD_FOLDER):
        logger.warning(f"Upload folder {UPLOAD_FOLDER} does not exist. Cannot synchronize.")
        # If playlist.json had entries but folder is gone, clear the playlist
        if media_playlist:
            logger.info("Clearing in-memory playlist as upload folder is missing.")
            media_playlist = []
            save_playlist_to_file()
        return

    try:
        # Ensure ALLOWED_EXTENSIONS are lowercase for comparison
        allowed_ext_lower = {ext.lower() for ext in ALLOWED_EXTENSIONS}
        actual_files_in_uploads = {
            f for f in os.listdir(UPLOAD_FOLDER) 
            if os.path.isfile(os.path.join(UPLOAD_FOLDER, f)) and \
               f.rsplit('.', 1)[-1].lower() in allowed_ext_lower
        }
        logger.debug(f"Files found in uploads folder: {actual_files_in_uploads}")
        
        # Ensure media_playlist contains only filenames, not full paths, for comparison
        # This should already be the case if load_playlist_from_file and uploads are consistent
        playlist_files_set = set(media_playlist)
        
        files_to_add = actual_files_in_uploads - playlist_files_set
        files_to_remove = playlist_files_set - actual_files_in_uploads
        
        made_changes = False
        
        if files_to_add:
            # Add while trying to maintain some order, e.g., sort them
            for f_add in sorted(list(files_to_add)): # Sort for consistent ordering
                media_playlist.append(f_add) 
            logger.info(f"Added to playlist (found in uploads but not in playlist.json): {sorted(list(files_to_add))}")
            made_changes = True
            
        if files_to_remove:
            # Create a new list excluding the files to remove, preserving order for the rest
            new_media_playlist = [f for f in media_playlist if f not in files_to_remove]
            media_playlist = new_media_playlist
            logger.info(f"Removed from playlist (in playlist.json but not found in uploads): {sorted(list(files_to_remove))}")
            made_changes = True
            
        if made_changes:
            logger.info(f"Playlist synchronized. New playlist: {media_playlist}")
            save_playlist_to_file()
        else:
            logger.info("Playlist is already synchronized with the uploads folder.")
            
    except Exception as e:
        logger.error(f"Error synchronizing playlist with uploads folder: {e}")

# --- File Extension Validation ---
def allowed_file(filename):
    """Checks if the provided filename has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Flask Route Definitions ---
@app.route('/')
def index():
    """Serves the main application HTML page."""
    logger.info(f"Serving index.html. Current playlist: {media_playlist}")
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Handles media file uploads via POST requests."""
    global media_playlist
    if 'mediaFiles' not in request.files:
        logger.warning("Upload attempt with no 'mediaFiles' part.")
        return jsonify({"error": "No file part in the request"}), 400
    
    files = request.files.getlist('mediaFiles')
    uploaded_filenames = []
    errors = []

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        try:
            os.makedirs(app.config['UPLOAD_FOLDER'])
            logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")
        except OSError as e:
            logger.error(f"Could not create upload folder: {e}")
            return jsonify({"error": "Could not create upload directory on server."}), 500

    for file in files:
        if file.filename == '':
            logger.warning("Upload attempt with an empty filename.")
            errors.append("One or more files had no selected filename.")
            continue
        if file and allowed_file(file.filename):
            filename = file.filename # Consider werkzeug.utils.secure_filename for production
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(save_path)
                logger.info(f"File saved: {save_path}")
                
                # Transcode the video after it's uploaded
                transcode_result = transcode_video(save_path)
                if transcode_result:
                    logger.info(f"Video successfully transcoded: {filename}")
                else:
                    logger.warning(f"Video transcoding failed or was skipped for: {filename}")
                
                if filename not in media_playlist: # Avoid duplicates
                    media_playlist.append(filename)
                uploaded_filenames.append(filename)
                logger.info(f"Successfully uploaded, transcoded, and added to playlist: {filename}")
            except Exception as e:
                logger.error(f"Error saving file {filename}: {e}")
                errors.append(f"Could not save file {filename}.")
        elif file.filename:
            logger.warning(f"Upload attempt with disallowed file type: {file.filename}")
            errors.append(f"File type not allowed for {file.filename}.")

    if uploaded_filenames:
        save_playlist_to_file() # Save playlist after successful uploads
        return jsonify({
            "message": "Files processed.", 
            "uploaded": uploaded_filenames, 
            "playlist": media_playlist,
            "errors": errors
        }), 200 if not errors else 207 # 207 Multi-Status if some uploads failed
    else:
        return jsonify({"error": "No files were successfully uploaded.", "details": errors}), 400

@app.route('/api/playlist', methods=['GET'])
def get_playlist():
    """Returns the current playlist and playback status as JSON."""
    global current_loop_mode, current_media_index, is_playing, media_playlist, loop_playlist

    mplayer_status = mplayer.get_playback_status()
    
    # MPlayer doesn't have internal playlist management, so we need to simplify this

    mplayer_is_running = mplayer_status.get('mplayer_is_running', False)
    actual_current_file_from_mplayer = None
    is_mplayer_playing_media = False

    if mplayer_is_running:
        actual_current_file_from_mplayer = mplayer_status.get('current_file')
        is_mplayer_playing_media = mplayer_status.get('is_playing_media', False)
        
        # MPlayer doesn't have playlist position, so we need to rely on our own tracking
        if actual_current_file_from_mplayer and actual_current_file_from_mplayer in media_playlist:
            try:
                current_media_index = media_playlist.index(actual_current_file_from_mplayer)
            except ValueError:
                logger.warning(f"MPlayer playing {actual_current_file_from_mplayer}, in Flask playlist but index() failed.")
        
    # Update Flask's global is_playing state based on MPlayer's actual state
    if is_playing != is_mplayer_playing_media and mplayer_is_running:
        logger.info(f"Flask's is_playing ({is_playing}) differs from MPlayer's ({is_mplayer_playing_media}). Updating Flask's state.")
        is_playing = is_mplayer_playing_media

    # If MPlayer is not running, reflect that.
    if not mplayer_is_running and is_playing:
        is_playing = False
        current_media_index = -1 # Reset index if MPlayer died
        logger.info("MPlayer is not running. Setting is_playing to False and resetting index.")

    # Fallback for currentFile if not accurately determined from MPlayer
    display_current_file = actual_current_file_from_mplayer
    if display_current_file is None and 0 <= current_media_index < len(media_playlist):
        display_current_file = media_playlist[current_media_index]
    elif display_current_file is None and not media_playlist:
        display_current_file = None

    is_paused = mplayer_status.get('is_paused', False) if mplayer_is_running else False
    
    return jsonify({
        "playlist": media_playlist,
        "currentFile": display_current_file,
        "isPlaying": is_playing, # Use the synced is_playing state
        "isPaused": is_paused,  # Include paused state
        "loop_mode": current_loop_mode,
        "mplayer_is_running": mplayer_is_running,
        "currentIndex": current_media_index # For UI highlighting
    })

@app.route('/api/control/play', methods=['POST'])
def control_play():
    """Handles play requests, including resuming or starting playback."""
    global current_media_index, is_playing, media_playlist, current_loop_mode # current_loop_mode is main.py's perspective
    
    # First check if MPlayer is running and paused - if so, just unpause it
    controller_status = mplayer.get_playback_status()
    if (controller_status.get('mplayer_is_running') and 
        controller_status.get('is_paused') and 
        controller_status.get('is_playing_media')):
        logger.info("Play command: MPlayer is paused. Unpausing instead of loading.")
        if mplayer.play():  # Use the play() method which will unpause if paused
            is_playing = True
            return jsonify({
                "status": "playing", 
                "currentFile": controller_status.get('current_file'),
                "currentIndex": current_media_index
            })
    
    data = request.get_json(silent=True) or {}
    target_filename = data.get('filename')

    if not media_playlist:
        logger.info("Play command received but playlist is empty.")
        return jsonify({"status": "playlist_empty", "message": "Playlist is empty. Upload media first."}), 400
    
    if target_filename:
        if target_filename in media_playlist:
            current_media_index = media_playlist.index(target_filename)
        else:
            logger.warning(f"Play requested for specific file '{target_filename}' not in playlist.")
            return jsonify({"error": f"File '{target_filename}' not found in playlist."}), 404
    elif current_media_index == -1 and media_playlist: # If nothing playing or stopped, start from beginning
        current_media_index = 0
    elif not (0 <= current_media_index < len(media_playlist)) and media_playlist: # If index is somehow invalid
        logger.warning(f"Invalid current_media_index {current_media_index}, resetting to 0.")
        current_media_index = 0
    
    file_to_play = media_playlist[current_media_index]
    
    # Get the loop mode directly from the MPlayerController instance
    controller_status = mplayer.get_playback_status() 
    actual_controller_loop_mode = controller_status.get('loop_mode')

    logger.info(f"Play command: Attempting to play '{file_to_play}' at index {current_media_index}. Main's current_loop_mode: {current_loop_mode}. Controller's actual_loop_mode: {actual_controller_loop_mode}")
    
    playback_started = False
    if actual_controller_loop_mode == 'playlist': # Use the controller's actual reported loop mode
        logger.info(f"Initiating playback with playlist mode (based on controller state). Full playlist will be loaded starting at index {current_media_index}.")
        if mplayer.load_playlist(media_playlist, current_media_index):
            playback_started = True
    else:
        logger.info(f"Controller's loop mode is '{actual_controller_loop_mode}', not 'playlist'. Falling back to load_file for '{file_to_play}'.")
        if mplayer.load_file(file_to_play):
            playback_started = True

    if playback_started:
        is_playing = True
        logger.info(f"Playback started for: {file_to_play} (or playlist starting with it). Index: {current_media_index}")
        return jsonify({"status": "playing", "currentFile": file_to_play, "currentIndex": current_media_index})
    else:
        is_playing = False
        return jsonify({"error": "Failed to start playback. Check server logs."}), 500

@app.route('/api/control/pause', methods=['POST'])
def control_pause():
    """Handles pause requests for the current playback session."""
    global is_playing

    if not mplayer.get_playback_status().get('mplayer_is_running'):
        return jsonify({"error": "MPlayer is not running"}), 503
    
    if mplayer.pause():
        logger.info("Playback paused")
        is_playing = False  # Update global play state
        return jsonify({"status": "paused"})
    else:
        return jsonify({"error": "Failed to pause playback"}), 500

@app.route('/api/control/toggle_pause', methods=['POST'])
def control_toggle_pause():
    """Toggles between play and pause states."""
    global is_playing

    if not mplayer.get_playback_status().get('mplayer_is_running'):
        return jsonify({"error": "MPlayer is not running"}), 503
    
    if mplayer.toggle_pause():
        status = mplayer.get_playback_status()
        is_playing = not status.get('is_paused', False)  # Update global play state
        state = "paused" if status.get('is_paused', False) else "playing"
        logger.info(f"Toggled pause state. Current state: {state}")
        return jsonify({"status": state})
    else:
        return jsonify({"error": "Failed to toggle playback state"}), 500

@app.route('/api/control/stop', methods=['POST'])
def control_stop():
    """Stops playback and resets playback state."""
    global is_playing, current_media_index
    if mplayer.stop():
        is_playing = False
        current_media_index = -1
        try:
            # Clear the framebuffer after stopping MPlayer
            logger.info("Attempting to clear framebuffer...")
            fb_width, fb_height, fb_bpp = 240, 320, 16  # Defaults
            fb_size = fb_width * fb_height * (fb_bpp // 8)
            fb_clear_command = ["dd", "if=/dev/zero", "of=/dev/fb0", f"bs={fb_size}", "count=1"]
            process = subprocess.Popen(fb_clear_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=5) # Add a timeout
            if process.returncode == 0:
                logger.info("Framebuffer cleared successfully.")
            else:
                logger.error(f"Failed to clear framebuffer. Return code: {process.returncode}")
                if stdout:
                    logger.error(f"Framebuffer clear stdout: {stdout.decode().strip()}")
                if stderr:
                    logger.error(f"Framebuffer clear stderr: {stderr.decode().strip()}")
        except subprocess.TimeoutExpired:
            logger.error("Framebuffer clear command timed out.")
            if process:
                process.kill() # Ensure the process is killed if it times out
                process.communicate() # Clean up
        except FileNotFoundError:
            logger.warning("dd command not found. Framebuffer not cleared. This is expected if not on a system with /dev/fb0.")
        except Exception as e:
            logger.error(f"An error occurred while trying to clear framebuffer: {e}")
        logger.info("Playback stopped. MPlayer terminated. Index reset.")
        return jsonify({"status": "stopped"})
    else:
        logger.warning("Failed to send stop command to MPlayer.")
        if not mplayer.get_playback_status().get('mplayer_is_running'):
            return jsonify({"error": "MPlayer is not running."}), 503
        return jsonify({"error": "Failed to stop playback."}), 500

def _play_next_or_prev(direction, from_auto_advance=False):
    """
    Advances to the next or previous track in the playlist, depending on direction.
    Handles both manual and auto-advance scenarios.
    """
    global current_media_index, is_playing, media_playlist, loop_playlist, current_loop_mode

    # Use MPlayer's native playlist navigation if in playlist mode and MPlayer is running
    controller_status = mplayer.get_playback_status()
    if controller_status.get('loop_mode') == 'playlist' and controller_status.get('mplayer_is_running'):
        if direction == "next":
            success = mplayer.playlist_next()
        else:
            success = mplayer.playlist_prev()
        if success:
            logger.info(f"Sent pt_step command to MPlayer for {direction} in playlist mode.")
            return jsonify(get_playlist_data_for_response())
        else:
            logger.warning(f"Failed to send pt_step command to MPlayer for {direction}.")
            return jsonify({"error": f"Failed to advance playlist ({direction}) in MPlayer."}), 500

    is_background = from_auto_advance
    if not is_background:
        try:
            from flask import has_app_context
            is_background = not has_app_context()
        except (ImportError, RuntimeError):
            is_background = True

    logger.debug(f"_play_next_or_prev called for '{direction}'. Loop mode: {current_loop_mode}")

    if not media_playlist:
        logger.info(f"Next/Prev called but playlist is empty.")
        mplayer.stop()
        is_playing = False
        return jsonify({"status": "playlist_empty"}), 400

    # MPlayer handles playlist logic entirely on Flask side
    num_items = len(media_playlist)
    if current_media_index == -1: # If stopped or uninitialized, start from 0 for next/prev
        current_media_index = 0
        if direction == "previous": # if prev is hit when uninitialized, go to last if looping, else 0
             current_media_index = num_items - 1 if loop_playlist else 0

    original_index = current_media_index
    if direction == "next":
        current_media_index += 1
        if current_media_index >= num_items:
            if loop_playlist:
                current_media_index = 0
                logger.info("Reached end of Flask playlist, looping to start.")
            else:
                logger.info("Reached end of Flask playlist, no loop. Stopping.")
                mplayer.stop()
                is_playing = False
                current_media_index = num_items - 1 # Stay on last item visually
                return jsonify({"status": "playlist_ended", "currentFile": media_playlist[current_media_index], "currentIndex": current_media_index})
    elif direction == "previous":
        current_media_index -= 1
        if current_media_index < 0:
            if loop_playlist:
                current_media_index = num_items - 1
                logger.info("Reached start of Flask playlist, looping to end.")
            else:
                logger.info("Reached start of Flask playlist, no loop. Staying at first item.")
                current_media_index = 0
    
    if not (0 <= current_media_index < len(media_playlist)):
        logger.error(f"Index {current_media_index} out of bounds after next/prev logic. Resetting to 0.")
        current_media_index = 0
        if not media_playlist:
             return jsonify({"error": "Playlist is empty"}), 400

    file_to_play = media_playlist[current_media_index]
    logger.info(f"Changing track ({direction}) via Flask to: {file_to_play} at index {current_media_index}")
    if mplayer.load_file(file_to_play):
        is_playing = True
        logger.info(f"Successfully loaded and started {file_to_play} for {direction}.")
        return jsonify({"status": f"playing_{direction}", "currentFile": file_to_play, "currentIndex": current_media_index})
    else:
        is_playing = False
        logger.error(f"MPlayer failed to load file for {direction}: {file_to_play}")
        mplayer.stop() # Stop MPlayer if load fails
        current_media_index = original_index # Revert index on failure
        return jsonify({"error": f"MPlayer could not load file '{file_to_play}' for {direction}. Playback stopped."}), 500

def get_playlist_data_for_response():
    """Helper to assemble current playlist and playback state for API responses."""
    global current_media_index, is_playing, media_playlist, current_loop_mode

    # Get the latest status from MPlayer
    mplayer_status_internal = mplayer.get_playback_status()
    mplayer_is_running_internal = mplayer_status_internal.get('mplayer_is_running', False)
    actual_current_file_internal = mplayer_status_internal.get('current_file')
    is_mplayer_playing_media_internal = mplayer_status_internal.get('is_playing_media', False)

    if mplayer_is_running_internal:
        # Check if MPlayer reports a current file
        if actual_current_file_internal:
            if actual_current_file_internal in media_playlist:
                try:
                    # Update the index to match the current file from MPlayer
                    new_index = media_playlist.index(actual_current_file_internal)
                    if new_index != current_media_index:
                        logger.info(f"Current file changed from index {current_media_index} to {new_index}: {actual_current_file_internal}")
                        current_media_index = new_index
                except ValueError:
                    logger.warning(f"File '{actual_current_file_internal}' reported by MPlayer not found in playlist.")
            else:
                # MPlayer reports a file that's not in our playlist - log this unusual situation
                logger.warning(f"MPlayer reports playing file not in playlist: {actual_current_file_internal}")
        
        # Sync is_playing state with MPlayer
        if is_playing != is_mplayer_playing_media_internal:
             logger.info(f"Syncing playing state: {is_playing} -> {is_mplayer_playing_media_internal}")
             is_playing = is_mplayer_playing_media_internal
    else:
        # MPlayer is not running
        if is_playing:
            logger.info("MPlayer is not running but is_playing=True. Resetting to False.")
            is_playing = False
        current_media_index = -1

    # Determine what file to display in the UI
    display_file = actual_current_file_internal
    if display_file is None and 0 <= current_media_index < len(media_playlist):
        display_file = media_playlist[current_media_index]
    
    # Get paused state from MPlayer
    is_paused_internal = mplayer_status_internal.get('is_paused', False) if mplayer_is_running_internal else False
    
    return {
        "playlist": media_playlist,
        "currentFile": display_file,
        "isPlaying": is_playing,
        "isPaused": is_paused_internal,
        "loop_mode": current_loop_mode,
        "mplayer_is_running": mplayer_is_running_internal,
        "currentIndex": current_media_index
    }

@app.route('/api/control/next', methods=['POST'])
def control_next():
    """API endpoint to advance to the next track."""
    return _play_next_or_prev("next")

@app.route('/api/control/previous', methods=['POST'])
def control_previous():
    """API endpoint to return to the previous track."""
    return _play_next_or_prev("previous")

@app.route('/api/playlist/set_next', methods=['POST'])
def set_next_track():
    """Moves a specified file to play next in the playlist order."""
    global media_playlist, current_media_index, is_playing, current_loop_mode
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename missing in request."}), 400
    
    filename_to_set_next = data['filename']
    if filename_to_set_next not in media_playlist:
        return jsonify({"error": f"File '{filename_to_set_next}' not found in playlist."}), 404

    try:
        target_idx_in_playlist = media_playlist.index(filename_to_set_next)
    except ValueError:
        return jsonify({"error": "File somehow not in playlist after check (race condition?)"}), 500

    # Move the file to the next slot after the current one, do not start playback or change current track
    if not (0 <= current_media_index < len(media_playlist)):
        # If nothing is playing, move the file to the start (after index -1, i.e., at 0)
        new_pos = 0
    else:
        new_pos = current_media_index + 1
    if target_idx_in_playlist == new_pos or target_idx_in_playlist == new_pos - 1:
        # Already in the correct position, nothing to do
        return jsonify({"status": "already_next", "playlist": media_playlist, "currentIndex": current_media_index })
    item_to_move = media_playlist.pop(target_idx_in_playlist)
    # Adjust new_pos if the item was before the insertion point
    if target_idx_in_playlist < new_pos:
        new_pos -= 1
    media_playlist.insert(new_pos, item_to_move)
    save_playlist_to_file()
    logger.info(f"Moved '{filename_to_set_next}' to position {new_pos} (next in playlist). New playlist: {media_playlist}")
    
    # If we're in playlist loop mode, we don't need to reload immediately
    # The changes will take effect when the current file finishes
    # Just log that the order has changed
    if is_playing and current_loop_mode == 'playlist' and 0 <= current_media_index < len(media_playlist):
        logger.info(f"Playlist order changed. Changes will take effect when current file finishes playing.")

    return jsonify({"status": "next_item_set", "nextFile": filename_to_set_next, "playlist": media_playlist, "currentIndex": current_media_index })

@app.route('/api/settings/loop', methods=['POST'])
def set_loop():
    """Legacy endpoint for toggling playlist loop (not used with MPlayer)."""
    global loop_playlist
    data = request.get_json()
    if data and 'loop' in data and isinstance(data['loop'], bool):
        loop_playlist = data['loop']
        logger.info(f"Playlist loop status set to: {loop_playlist}")
        return jsonify({"loop_status": loop_playlist})
    return jsonify({"error": "Invalid request. 'loop' boolean field required."}), 400

@app.route('/api/settings/loop_mode', methods=['POST'])
def set_loop_mode():
    """Sets the loop mode for playback (none, file, or playlist)."""
    global current_loop_mode, loop_playlist, media_playlist, current_media_index, is_playing
    data = request.get_json()
    if not data or 'mode' not in data:
        return jsonify({"error": "Mode missing in request"}), 400
        
    mode = data['mode']
    if mode not in ['none', 'file', 'playlist']:
        return jsonify({"error": "Invalid mode. Use 'none', 'file', or 'playlist'"}), 400
    
    # Set the loop mode in the MPlayer controller
    if mplayer.set_loop_mode(mode):
        current_loop_mode = mode
        loop_playlist = (mode == 'playlist')
        logger.info(f"Loop mode set to: {mode}")
        
        # If we're currently playing a file or playlist, reload with the new loop setting
        if is_playing and 0 <= current_media_index < len(media_playlist):
            current_file = media_playlist[current_media_index]
            if mode == 'playlist' and len(media_playlist) > 1:
                # For playlist mode, we always need to reload to apply loop settings
                logger.info(f"Loading playlist with {len(media_playlist)} items starting at index {current_media_index}")
                mplayer.load_playlist(media_playlist, current_media_index)
            else:
                # For single file mode or no loop mode, we must reload the current file with the new settings
                logger.info(f"Loading single file with loop={mode}: {current_file}")
                mplayer.load_file(current_file)
    else:
        logger.warning(f"Failed to set loop mode to {mode}")
    
    return jsonify(get_playlist_data_for_response())


@app.route('/api/playlist/delete', methods=['POST'])
def api_playlist_delete():
    """Deletes a file from the playlist and disk."""
    global media_playlist, current_media_index, is_playing

    try:
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({"error": "Missing filename"}), 400
        
        filename = data['filename']
        
        # Verify that file exists
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Check if the file being deleted is currently playing
        is_deleting_current = False
        # If we're playing something, check if it's the file we're deleting
        if is_playing and current_media_index >= 0 and current_media_index < len(media_playlist):
            is_deleting_current = (media_playlist[current_media_index] == filename)
        
        if is_deleting_current:
            # Stop playback if currently playing
            mplayer.stop()
            is_playing = False
            # If there are other files, we'll need to adjust the index
            if len(media_playlist) > 1:
                # We'll reset the index to the beginning in update_playlist_after_delete
                # This will be handled by the playlist code after delete
                pass

        # Before removing from playlist, get index
        try:
            file_index = media_playlist.index(filename)
        except ValueError:
            return jsonify({"error": f"File not in playlist: {filename}"}), 400
        
        # Remove from playlist
        media_playlist.remove(filename)
        
        # Update index if needed
        if current_media_index >= file_index:
            # If we're removing a file before or at the current index, adjust the index
            current_media_index = max(0, current_media_index - 1) if media_playlist else -1
        
        # Save playlist changes
        save_playlist_to_file()
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File deleted: {filename}")
            else:
                logger.warning(f"File not found for deletion (but removed from playlist): {filename}")
        except Exception as e:
            logger.error(f"Error deleting file {filename}: {str(e)}")
            return jsonify({"error": f"Error deleting file: {str(e)}"}), 500
        
        # Return success response
        return jsonify({
            "status": "deleted", 
            "message": f"File {filename} deleted",
            "playlist": media_playlist,
            "currentFile": media_playlist[current_media_index] if 0 <= current_media_index < len(media_playlist) else None,
            "currentIndex": current_media_index,
            "isPlaying": is_playing,
        })
        
    except Exception as e:
        logger.error(f"Error in delete API: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/playlist/reorder', methods=['POST'])
def reorder_playlist_items():
    """Reorders items in the playlist based on a new list of filenames."""
    global media_playlist
    
    try:
        data = request.get_json()
        if not data or 'order' not in data:
            return jsonify({"error": "Missing order parameter"}), 400
        
        new_order = data['order']
        
        # Validate that all files in new_order exist in media_playlist
        if not all(item in media_playlist for item in new_order):
            return jsonify({"error": "New order contains files not in the current playlist"}), 400
            
        # Validate that all files in media_playlist exist in new_order
        if not all(item in new_order for item in media_playlist):
            return jsonify({"error": "New order is missing files from the current playlist"}), 400
        
        # Update the playlist order
        media_playlist = new_order
        
        # Save the updated playlist
        save_playlist_to_file()
        
        # Return success response
        return jsonify({
            "status": "reordered",
            "playlist": media_playlist,
            "mplayer_is_running": mplayer.get_playback_status().get('is_mplayer_running', False)
        })
        
    except Exception as e:
        logger.error(f"Error reordering playlist: {e}")
        return jsonify({"error": "Failed to reorder playlist"}), 500

@app.route('/api/server/stop', methods=['POST'])
def stop_server():
    """Stops the systemd service for this application."""
    try:
        logger.info("Received request to stop the server via systemctl.")
        # It's crucial that the user running this Flask app (e.g., 'pi')
        # has sudo privileges to run systemctl stop without a password.
        # This typically involves configuring /etc/sudoers or /etc/sudoers.d/
        # Example sudoers entry: pi ALL=(ALL) NOPASSWD: /bin/systemctl stop simple_media_player.service
        command = ["sudo", "systemctl", "stop", "simple_media_player.service"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            logger.info("Successfully issued systemctl stop command.")
            return jsonify({"status": "stopping", "message": "Server stop command issued."}), 200
        else:
            logger.error(f"Failed to stop server via systemctl. Return code: {process.returncode}")
            logger.error(f"Stderr: {stderr.decode().strip()}")
            logger.error(f"Stdout: {stdout.decode().strip()}")
            return jsonify({
                "status": "error", 
                "message": "Failed to issue server stop command.",
                "error_details": stderr.decode().strip()
            }), 500
    except Exception as e:
        logger.error(f"Exception while trying to stop server: {e}")
        return jsonify({"status": "error", "message": "An unexpected error occurred."}), 500

# --- MPlayer Process Management ---
def start_mplayer_process_if_not_running():
    """Starts the MPlayer process if it's not already running."""
    global mplayer

    status = mplayer.get_playback_status()
    if status.get('mplayer_is_running'):
        logger.info("MPlayer is already running.")
        return True

    logger.info("Starting MPlayer process...")
    # Attempt to start the MPlayer process
    if mplayer.start():
        logger.info("MPlayer process started successfully.")
        return True
    else:
        logger.error("Failed to start MPlayer process.")
        return False

def transcode_video(file_path):
    """
    Transcodes a video file using the transcode_videos.sh script.
    
    Args:
        file_path (str): The path to the video file to transcode
        
    Returns:
        bool: True if transcoding was successful, False otherwise
    """
    try:
        # Only transcode if we're targeting a Raspberry Pi (as defined in .env)
        target_device = os.getenv("KTV_TARGET_DEVICE", "laptop")
        #if target_device != "raspberrypi":
        #    logger.info(f"Skipping transcoding for {file_path} - target device is {target_device}, not raspberrypi")
        #    return True
            
        transcode_script = os.path.join(PROJECT_ROOT, "transcode_videos.sh")
        
        if not os.path.exists(transcode_script):
            logger.error(f"Transcoding script not found: {transcode_script}")
            return False
            
        logger.info(f"Starting transcoding for {file_path}")
        
        # Run the transcoding script with the video file as an argument
        # We use subprocess.run() instead of os.system() for better error handling
        result = subprocess.run(
            [transcode_script, file_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully transcoded: {file_path}")
            logger.debug(f"Transcode output: {result.stdout}")
            return True
        else:
            logger.error(f"Transcoding failed for {file_path} with exit code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during transcoding for {file_path}: {e}")
        return False

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created upload folder: {UPLOAD_FOLDER} on startup.")
    
    # Initial load is done above.
    # synchronize_playlist_with_uploads() is called after load_playlist_from_file()
    logger.info(f"Playlist after sync: {media_playlist}")

    logger.info("Starting Flask with MPlayer support...")

    app.run(host='0.0.0.0', port=5000, debug=False)
