from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import logging
import time # Added to fix NameError
import json # Added for playlist persistence
import threading # For the image auto-advance timer
import atexit # For cleanup on exit

# Custom logging setup
from logging_config import setup_logging

# MPlayer Controller instead of MPV Controller
from mplayer_controller import MPlayerController

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Configuration ---
# Determine project root dynamically (assuming main.py is in 'app' directory)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'app', 'uploads')
PLAYLIST_FILE = os.path.join(PROJECT_ROOT, 'playlist.json') # For persisting playlist
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300 MB upload limit

# --- Logging Setup ---
# Call setup_logging, passing the app instance and desired log file name (relative to project root)
setup_logging(app, log_filename="server.log")
logger = app.logger # Use Flask's configured logger

# --- Media Management (In-memory for simplicity first) ---
media_playlist = [] # List of filenames (relative to UPLOAD_FOLDER)
current_media_index = -1
is_playing = False
loop_playlist = False
current_loop_mode = 'none'  # Persist the last set loop mode
# current_transition = "fade" # Default, if we implement selectable transitions

# --- Playlist Persistence Functions ---
def load_playlist_from_file():
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
    try:
        with open(PLAYLIST_FILE, 'w') as f:
            json.dump(media_playlist, f, indent=4)
        logger.info(f"Playlist saved to {PLAYLIST_FILE}")
    except Exception as e:
        logger.error(f"Error saving playlist to {PLAYLIST_FILE}: {e}")

# Load playlist at startup
load_playlist_from_file()

# --- MPlayer Controller Instance ---
mpv = MPlayerController() # Initialize the controller with MPlayer instead of MPV

# --- Playlist Synchronization Function ---
def synchronize_playlist_with_uploads():
    """
    Scans the UPLOAD_FOLDER for media files and updates media_playlist
    and playlist.json to match.
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

# --- Utility Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    logger.info(f"Serving index.html. Current playlist: {media_playlist}")
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_files():
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
                if filename not in media_playlist: # Avoid duplicates
                    media_playlist.append(filename)
                uploaded_filenames.append(filename)
                logger.info(f"Successfully uploaded and saved: {filename}")
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
    global current_loop_mode, current_media_index, is_playing, media_playlist, loop_playlist

    mpv_status = mpv.get_playback_status()
    
    # MPlayer doesn't have internal playlist management, so we need to simplify this
    
    mpv_is_running = mpv_status.get('is_mpv_running', False)
    actual_current_file_from_mpv = None
    is_mpv_playing_media = False

    if mpv_is_running:
        actual_current_file_from_mpv = mpv_status.get('current_file')
        is_mpv_playing_media = mpv_status.get('is_playing_media', False)
        
        # MPlayer doesn't have playlist position, so we need to rely on our own tracking
        if actual_current_file_from_mpv and actual_current_file_from_mpv in media_playlist:
            try:
                current_media_index = media_playlist.index(actual_current_file_from_mpv)
            except ValueError:
                logger.warning(f"MPlayer playing {actual_current_file_from_mpv}, in Flask playlist but index() failed.")
        
    # Update Flask's global is_playing state based on MPlayer's actual state
    if is_playing != is_mpv_playing_media and mpv_is_running:
        logger.info(f"Flask's is_playing ({is_playing}) differs from MPlayer's ({is_mpv_playing_media}). Updating Flask's state.")
        is_playing = is_mpv_playing_media

    # If MPlayer is not running, reflect that.
    if not mpv_is_running and is_playing:
        is_playing = False
        current_media_index = -1 # Reset index if MPlayer died
        logger.info("MPlayer is not running. Setting is_playing to False and resetting index.")

    # Fallback for currentFile if not accurately determined from MPlayer
    display_current_file = actual_current_file_from_mpv
    if display_current_file is None and 0 <= current_media_index < len(media_playlist):
        display_current_file = media_playlist[current_media_index]
    elif display_current_file is None and not media_playlist:
        display_current_file = None

    is_paused = mpv_status.get('is_paused', False) if mpv_is_running else False
    
    return jsonify({
        "playlist": media_playlist,
        "currentFile": display_current_file,
        "isPlaying": is_playing, # Use the synced is_playing state
        "isPaused": is_paused,  # Include paused state
        "loop_mode": current_loop_mode,
        "mpv_is_running": mpv_is_running,
        "currentIndex": current_media_index # For UI highlighting
    })

@app.route('/api/control/play', methods=['POST'])
def control_play():
    global current_media_index, is_playing, media_playlist, current_loop_mode # current_loop_mode is main.py's perspective
    
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
    controller_status = mpv.get_playback_status() 
    actual_controller_loop_mode = controller_status.get('loop_mode')

    logger.info(f"Play command: Attempting to play '{file_to_play}' at index {current_media_index}. Main's current_loop_mode: {current_loop_mode}. Controller's actual_loop_mode: {actual_controller_loop_mode}")
    
    playback_started = False
    if actual_controller_loop_mode == 'playlist': # Use the controller's actual reported loop mode
        logger.info(f"Initiating playback with playlist mode (based on controller state). Full playlist will be loaded starting at index {current_media_index}.")
        if mpv.load_playlist(media_playlist, current_media_index):
            playback_started = True
    else:
        logger.info(f"Controller's loop mode is '{actual_controller_loop_mode}', not 'playlist'. Falling back to load_file for '{file_to_play}'.")
        if mpv.load_file(file_to_play):
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
    global is_playing
    
    if not mpv.get_playback_status().get('is_mpv_running'):
        return jsonify({"error": "MPlayer is not running"}), 503
    
    if mpv.pause():
        logger.info("Playback paused")
        is_playing = False  # Update global play state
        return jsonify({"status": "paused"})
    else:
        return jsonify({"error": "Failed to pause playback"}), 500

@app.route('/api/control/toggle_pause', methods=['POST'])
def control_toggle_pause():
    global is_playing
    
    if not mpv.get_playback_status().get('is_mpv_running'):
        return jsonify({"error": "MPlayer is not running"}), 503
    
    if mpv.toggle_pause():
        status = mpv.get_playback_status()
        is_playing = not status.get('is_paused', False)  # Update global play state
        state = "paused" if status.get('is_paused', False) else "playing"
        logger.info(f"Toggled pause state. Current state: {state}")
        return jsonify({"status": state})
    else:
        return jsonify({"error": "Failed to toggle playback state"}), 500

@app.route('/api/control/stop', methods=['POST'])
def control_stop():
    global is_playing, current_media_index
    if mpv.stop():
        is_playing = False
        current_media_index = -1
        logger.info("Playback stopped. MPlayer terminated. Index reset.")
        return jsonify({"status": "stopped"})
    else:
        logger.warning("Failed to send stop command to MPlayer.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPlayer is not running."}), 503
        return jsonify({"error": "Failed to stop playback."}), 500

def _play_next_or_prev(direction, from_auto_advance=False):
    global current_media_index, is_playing, media_playlist, loop_playlist, current_loop_mode

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
        mpv.stop()
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
                mpv.stop()
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
    if mpv.load_file(file_to_play):
        is_playing = True
        logger.info(f"Successfully loaded and started {file_to_play} for {direction}.")
        return jsonify({"status": f"playing_{direction}", "currentFile": file_to_play, "currentIndex": current_media_index})
    else:
        is_playing = False
        logger.error(f"MPlayer failed to load file for {direction}: {file_to_play}")
        mpv.stop() # Stop MPlayer if load fails
        current_media_index = original_index # Revert index on failure
        return jsonify({"error": f"MPlayer could not load file '{file_to_play}' for {direction}. Playback stopped."}), 500

def get_playlist_data_for_response():
    """Helper function to get current playlist data, callable by other routes for immediate refresh."""
    global current_media_index, is_playing, media_playlist, current_loop_mode

    # Get the latest status from MPlayer
    mpv_status_internal = mpv.get_playback_status()
    mpv_is_running_internal = mpv_status_internal.get('is_mpv_running', False)
    actual_current_file_internal = mpv_status_internal.get('current_file')
    is_mpv_playing_media_internal = mpv_status_internal.get('is_playing_media', False)

    if mpv_is_running_internal:
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
        if is_playing != is_mpv_playing_media_internal:
             logger.info(f"Syncing playing state: {is_playing} -> {is_mpv_playing_media_internal}")
             is_playing = is_mpv_playing_media_internal
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
    is_paused_internal = mpv_status_internal.get('is_paused', False) if mpv_is_running_internal else False
    
    return {
        "playlist": media_playlist,
        "currentFile": display_file,
        "isPlaying": is_playing,
        "isPaused": is_paused_internal,
        "loop_mode": current_loop_mode,
        "mpv_is_running": mpv_is_running_internal,
        "currentIndex": current_media_index
    }

@app.route('/api/control/next', methods=['POST'])
def control_next():
    return _play_next_or_prev("next")

@app.route('/api/control/previous', methods=['POST'])
def control_previous():
    return _play_next_or_prev("previous")

@app.route('/api/playlist/set_next', methods=['POST'])
def set_next_track():
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
    global loop_playlist
    data = request.get_json()
    if data and 'loop' in data and isinstance(data['loop'], bool):
        loop_playlist = data['loop']
        logger.info(f"Playlist loop status set to: {loop_playlist}")
        return jsonify({"loop_status": loop_playlist})
    return jsonify({"error": "Invalid request. 'loop' boolean field required."}), 400

@app.route('/api/settings/loop_mode', methods=['POST'])
def set_loop_mode():
    global current_loop_mode, loop_playlist, media_playlist, current_media_index, is_playing
    data = request.get_json()
    if not data or 'mode' not in data:
        return jsonify({"error": "Mode missing in request"}), 400
        
    mode = data['mode']
    if mode not in ['none', 'file', 'playlist']:
        return jsonify({"error": "Invalid mode. Use 'none', 'file', or 'playlist'"}), 400
    
    # Set the loop mode in the MPlayer controller
    if mpv.set_loop_mode(mode):
        current_loop_mode = mode
        loop_playlist = (mode == 'playlist')
        logger.info(f"Loop mode set to: {mode}")
        
        # If we're currently playing a file or playlist, reload with the new loop setting
        if is_playing and 0 <= current_media_index < len(media_playlist):
            current_file = media_playlist[current_media_index]
            if mode == 'playlist' and len(media_playlist) > 1:
                # For playlist mode, we always need to reload to apply loop settings
                logger.info(f"Loading playlist with {len(media_playlist)} items starting at index {current_media_index}")
                mpv.load_playlist(media_playlist, current_media_index)
            else:
                # For single file mode or no loop mode, we must reload the current file with the new settings
                logger.info(f"Loading single file with loop={mode}: {current_file}")
                mpv.load_file(current_file)
    else:
        logger.warning(f"Failed to set loop mode to {mode}")
    
    return jsonify(get_playlist_data_for_response())

@app.route('/api/control/loop_file', methods=['POST'])
def loop_current_file():
    # MPlayer doesn't support looping in this implementation
    logger.warning("Loop file not supported in MPlayer implementation.")
    return jsonify({"warning": "Loop file not supported in this player implementation."}), 200

@app.route('/api/playlist/delete', methods=['POST'])
def delete_file_from_playlist():
    global media_playlist, current_media_index, is_playing
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename missing in request."}), 400

    filename = data['filename']
    if filename not in media_playlist:
        return jsonify({"error": f"File '{filename}' not found in playlist."}), 404

    idx = media_playlist.index(filename)
    media_playlist.pop(idx)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file from disk: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")

    if current_media_index == idx:
        mpv.stop()
        is_playing = False
        current_media_index = -1
    elif current_media_index > idx:
        current_media_index -= 1

    save_playlist_to_file()
    logger.info(f"Deleted '{filename}' from playlist.")
    return jsonify({"status": "deleted", "filename": filename, "playlist": media_playlist})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    logger.debug(f"Request for uploaded file: {filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/mplayer/restart', methods=['POST'])
def restart_mplayer_route():
    logger.info("API call to restart MPlayer.")
    mpv.terminate_player()
    time.sleep(0.5)
    if mpv.start_player():
        logger.info("MPlayer restarted successfully via API.")
        return jsonify({"status": "mplayer_restarted"}), 200
    else:
        logger.error("Failed to restart MPlayer via API.")
        return jsonify({"error": "Failed to restart MPlayer."}), 500

@app.teardown_appcontext
def teardown_mpv(exception=None):
    pass

# Synchronize playlist after loading and before starting app
synchronize_playlist_with_uploads()

import atexit
def cleanup_on_exit():
    logger.info("Flask application is exiting. Terminating MPlayer.")
    mpv.terminate_player()
atexit.register(cleanup_on_exit)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created upload folder: {UPLOAD_FOLDER} on startup.")
    
    # Initial load is done above.
    # synchronize_playlist_with_uploads() is called after load_playlist_from_file()
    logger.info(f"Playlist after sync: {media_playlist}")

    logger.info("Starting Flask with MPlayer support...")

    app.run(host='0.0.0.0', port=5000, debug=False)
