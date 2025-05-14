from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import logging
import time # Added to fix NameError
import json # Added for playlist persistence
import threading # For the image auto-advance timer

# Custom logging setup
from logging_config import setup_logging

# MPV Controller (initially a placeholder, will be developed)
from mpv_controller import MPVController

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Configuration ---
# Determine project root dynamically (assuming main.py is in 'app' directory)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'app', 'uploads')
PLAYLIST_FILE = os.path.join(PROJECT_ROOT, 'playlist.json') # For persisting playlist
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv'}

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
image_auto_advance_interval_seconds = 0 # 0 means disabled, value in seconds
image_advance_timer = None # Will hold the threading.Timer object
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

# --- MPV Controller Instance ---
mpv = MPVController() # Initialize the controller

# --- Utility Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image_file(filename):
    if not filename:
        return False
    # Get the file extension
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ['png', 'jpg', 'jpeg', 'gif']

def cancel_image_advance_timer():
    global image_advance_timer
    if image_advance_timer and image_advance_timer.is_alive(): # Check if timer is active
        image_advance_timer.cancel()
        image_advance_timer = None
        logger.debug("Cancelled existing image advance timer.")

def trigger_auto_next(expected_image_filename):
    global current_media_index, media_playlist, is_playing, logger
    logger.debug(f"Image advance timer triggered for {expected_image_filename}.")
    
    if is_playing and \
       0 <= current_media_index < len(media_playlist) and \
       media_playlist[current_media_index] == expected_image_filename and \
       is_image_file(media_playlist[current_media_index]):
        
        logger.info(f"Image timer expired for {expected_image_filename}, attempting to advance to next.")
        # Create an application context for background operation
        with app.app_context():
            _play_next_or_prev('next')
    else:
        logger.debug(f"Image advance timer for {expected_image_filename} is no longer relevant or conditions not met. "
                     f"Current file: {media_playlist[current_media_index] if 0 <= current_media_index < len(media_playlist) else 'None'}, "
                     f"Is playing: {is_playing}")

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
    global current_loop_mode  # use the persisted mode
    global current_media_index, is_playing, media_playlist, image_auto_advance_interval_seconds
    mpv_status = mpv.get_playback_status()
    
    is_playing = mpv_status.get('is_playing_media', is_playing)
    current_file_from_mpv = mpv_status.get('current_file')

    if current_file_from_mpv and current_file_from_mpv in media_playlist:
        try:
            new_index = media_playlist.index(current_file_from_mpv)
            if current_media_index != new_index:
                logger.debug(f"Syncing current_media_index from {current_media_index} to {new_index} based on MPV state ({current_file_from_mpv}).")
                current_media_index = new_index
        except ValueError:
            logger.warning(f"MPV playing {current_file_from_mpv}, which is in media_playlist but index() failed. This is unexpected.")
    elif current_file_from_mpv and current_file_from_mpv not in media_playlist:
        logger.warning(f"MPV playing {current_file_from_mpv}, which is NOT in our managed media_playlist. State may be desynced.")
    elif not current_file_from_mpv:
        if is_playing:
            logger.debug(f"MPV reports no file path, but internal state was is_playing=True. Correcting to False.")
            is_playing = False

    return jsonify({
        "playlist": media_playlist,
        "currentFile": media_playlist[current_media_index] if 0 <= current_media_index < len(media_playlist) else None,
        "isPlaying": is_playing,
        "loop_mode": current_loop_mode,
        "mpv_is_running": mpv_status.get('is_mpv_running', False),
        "image_auto_advance_interval_seconds": image_auto_advance_interval_seconds
    })

@app.route('/api/settings/image_interval', methods=['POST'])
def set_image_interval():
    global image_auto_advance_interval_seconds, is_playing, current_media_index, media_playlist, image_advance_timer
    data = request.get_json()
    if data and 'interval' in data:
        try:
            interval = int(data['interval'])
            if interval >= 0:
                old_interval = image_auto_advance_interval_seconds
                image_auto_advance_interval_seconds = interval
                logger.info(f"Image auto-advance interval changed from {old_interval}s to {image_auto_advance_interval_seconds}s.")
                
                cancel_image_advance_timer()

                if is_playing and \
                   0 <= current_media_index < len(media_playlist) and \
                   is_image_file(media_playlist[current_media_index]) and \
                   image_auto_advance_interval_seconds > 0:
                    
                    current_playing_image = media_playlist[current_media_index]
                    image_advance_timer = threading.Timer(image_auto_advance_interval_seconds, trigger_auto_next, args=[current_playing_image])
                    image_advance_timer.start()
                    logger.info(f"Restarted image advance timer for currently playing image {current_playing_image} with new interval {image_auto_advance_interval_seconds}s.")

                return jsonify({"status": "success", "image_auto_advance_interval_seconds": image_auto_advance_interval_seconds})
            else:
                return jsonify({"error": "Interval must be a non-negative integer."}), 400
        except ValueError:
            return jsonify({"error": "Invalid interval format. Must be an integer."}), 400
    return jsonify({"error": "Interval missing in request."}), 400

@app.route('/api/control/play', methods=['POST'])
def control_play():
    global current_media_index, is_playing, media_playlist, image_advance_timer
    
    cancel_image_advance_timer()

    data = request.get_json(silent=True) or {}
    target_filename = data.get('filename')

    if not mpv.start_player():
        logger.error("MPV failed to start. Cannot play.")
        return jsonify({"error": "MPV player is not available."}), 503

    if target_filename:
        if target_filename in media_playlist:
            current_media_index = media_playlist.index(target_filename)
        else:
            logger.warning(f"Play requested for specific file '{target_filename}' not in playlist.")
            return jsonify({"error": f"File '{target_filename}' not found in playlist."}), 404
    elif not media_playlist:
        logger.info("Play command received but playlist is empty.")
        return jsonify({"status": "playlist_empty", "message": "Playlist is empty. Upload media first."}), 400
    elif current_media_index == -1 and media_playlist:
        current_media_index = 0
    elif not (0 <= current_media_index < len(media_playlist)) and media_playlist:
        logger.warning(f"Invalid current_media_index {current_media_index}, resetting to 0.")
        current_media_index = 0
    
    if not media_playlist:
        return jsonify({"status": "playlist_empty", "message": "Playlist is empty."}), 400

    file_to_play = media_playlist[current_media_index]
    logger.info(f"Play command: Attempting to play '{file_to_play}' at index {current_media_index}")

    if mpv.load_file(file_to_play):
        if mpv.play():
            is_playing = True
            logger.info(f"Playback started for: {file_to_play}")

            if is_image_file(file_to_play) and image_auto_advance_interval_seconds > 0:
                image_advance_timer = threading.Timer(image_auto_advance_interval_seconds, trigger_auto_next, args=[file_to_play])
                image_advance_timer.start()
                logger.info(f"Started image advance timer for {file_to_play} ({image_auto_advance_interval_seconds}s).")
            
            return jsonify({"status": "playing", "currentFile": file_to_play, "currentIndex": current_media_index, "image_auto_advance_interval_seconds": image_auto_advance_interval_seconds})
        else:
            is_playing = False
            logger.error(f"MPV loaded file {file_to_play} but failed to ensure playback state.")
            return jsonify({"error": f"Loaded {file_to_play} but failed to start/resume playback in MPV."}), 500
    else:
        is_playing = False
        logger.error(f"MPV failed to load file: {file_to_play}")
        return jsonify({"error": f"MPV could not load file '{file_to_play}'."}), 500

@app.route('/api/control/pause', methods=['POST'])
def control_pause():
    global is_playing
    if mpv.pause():
        is_playing = False
        logger.info("Playback paused.")
        return jsonify({"status": "paused"})
    else:
        logger.warning("Failed to send pause command to MPV or MPV not running.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to pause playback."}), 500

@app.route('/api/control/toggle_pause', methods=['POST'])
def control_toggle_pause():
    global is_playing, current_media_index, media_playlist, image_advance_timer
    
    was_playing = is_playing 

    if mpv.toggle_pause():
        mpv_state = mpv.get_playback_status()
        is_playing = mpv_state.get('is_playing_media', False)
        current_file_from_mpv = mpv_state.get('current_file')

        logger.info(f"Toggle pause successful. MPV reports playing: {is_playing}, file: {current_file_from_mpv}")

        if is_playing:
            if 0 <= current_media_index < len(media_playlist) and \
               is_image_file(media_playlist[current_media_index]) and \
               image_auto_advance_interval_seconds > 0:
                
                cancel_image_advance_timer()
                current_image_file = media_playlist[current_media_index]
                image_advance_timer = threading.Timer(image_auto_advance_interval_seconds, trigger_auto_next, args=[current_image_file])
                image_advance_timer.start()
                logger.info(f"Unpaused: Started/Restarted image advance timer for {current_image_file} ({image_auto_advance_interval_seconds}s).")
        else:
            if 0 <= current_media_index < len(media_playlist) and \
               is_image_file(media_playlist[current_media_index]) and \
               image_advance_timer and getattr(image_advance_timer, 'args', [None])[0] == media_playlist[current_media_index]:
                cancel_image_advance_timer()
                logger.info(f"Paused: Cancelled image advance timer for {media_playlist[current_media_index]}.")

        return jsonify({"status": "toggled", "isPlaying": is_playing, "currentFile": current_file_from_mpv, "image_auto_advance_interval_seconds": image_auto_advance_interval_seconds})
    else:
        logger.warning("Failed to send toggle_pause command to MPV.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to toggle pause."}), 500

@app.route('/api/control/stop', methods=['POST'])
def control_stop():
    global is_playing, current_media_index
    cancel_image_advance_timer()
    if mpv.stop():
        is_playing = False
        current_media_index = -1
        logger.info("Playback stopped. MPV now idle (black screen). Index reset.")
        return jsonify({"status": "stopped"})
    else:
        logger.warning("Failed to send stop command to MPV.")
        if not mpv.get_playback_status().get('is_mpv_running'):
            return jsonify({"error": "MPV is not running."}), 503
        return jsonify({"error": "Failed to stop playback."}), 500

def _play_next_or_prev(direction):
    global current_media_index, is_playing, media_playlist, loop_playlist, image_advance_timer

    cancel_image_advance_timer()

    # Check if we're in a background thread (timer context)
    is_background = False
    try:
        from flask import has_app_context
        is_background = not has_app_context()
    except (ImportError, RuntimeError):
        # If we can't import has_app_context or there's an error, assume it might be background
        is_background = True

    if not media_playlist:
        logger.info(f"Next/Prev called but playlist is empty.")
        mpv.stop()
        is_playing = False
        if is_background:
            # Return None instead of a response when called from background
            return None
        return jsonify({"status": "playlist_empty"}), 400

    if not mpv.get_playback_status().get('is_mpv_running'):
        logger.warning("Next/Prev called but MPV is not running. Attempting to start.")
        if not mpv.start_player():
            if is_background:
                # Return None instead of a response when called from background
                return None
            return jsonify({"error": "MPV is not running and could not be started."}), 503
        if not (0 <= current_media_index < len(media_playlist)):
            current_media_index = 0
    
    num_items = len(media_playlist)
    if direction == "next":
        current_media_index += 1
        if current_media_index >= num_items:
            if loop_playlist:
                current_media_index = 0
                logger.info("Reached end of playlist, looping to start.")
            else:
                logger.info("Reached end of playlist, no loop. Stopping.")
                mpv.stop()
                is_playing = False
                current_media_index = num_items -1
                if is_background:
                    # Return None instead of a response when called from background
                    return None
                return jsonify({"status": "playlist_ended"})
    elif direction == "previous":
        current_media_index -= 1
        if current_media_index < 0:
            if loop_playlist:
                current_media_index = num_items - 1
                logger.info("Reached start of playlist, looping to end.")
            else:
                logger.info("Reached start of playlist, no loop. Staying at first item.")
                current_media_index = 0

    file_to_play = media_playlist[current_media_index]
    logger.info(f"Changing track ({direction}) to: {file_to_play} at index {current_media_index}")
    if mpv.load_file(file_to_play):
        if mpv.play():
            is_playing = True
            logger.info(f"Successfully loaded and started {file_to_play} for {direction}.")
            if is_image_file(file_to_play) and image_auto_advance_interval_seconds > 0:
                image_advance_timer = threading.Timer(image_auto_advance_interval_seconds, trigger_auto_next, args=[file_to_play])
                image_advance_timer.start()
                logger.info(f"Started image advance timer for {file_to_play} ({image_auto_advance_interval_seconds}s) after {direction}.")
            if is_background:
                # Return None instead of a response when called from background
                return None
            return jsonify({"status": f"playing_{direction}", "currentFile": file_to_play, "currentIndex": current_media_index})
        else:
            is_playing = False
            logger.error(f"Loaded {file_to_play} for {direction}, but failed to start playback.")
            if is_background:
                # Return None instead of a response when called from background
                return None
            return jsonify({"error": f"Loaded {file_to_play} but failed to start/resume playback in MPV."}), 500
    else:
        is_playing = False
        logger.error(f"MPV failed to load file for {direction}: {file_to_play}")
        mpv.stop()
        if is_background:
            # Return None instead of a response when called from background
            return None
        return jsonify({"error": f"MPV could not load file '{file_to_play}' for {direction}. Playback stopped."}), 500

@app.route('/api/control/next', methods=['POST'])
def control_next():
    return _play_next_or_prev("next")

@app.route('/api/control/previous', methods=['POST'])
def control_previous():
    return _play_next_or_prev("previous")

@app.route('/api/playlist/set_next', methods=['POST'])
def set_next_track():
    global media_playlist, current_media_index, is_playing
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

    if not is_playing or not (0 <= current_media_index < len(media_playlist)):
        current_media_index = target_idx_in_playlist
        save_playlist_to_file()
        return control_play()
    else:
        logger.info(f"Setting '{filename_to_set_next}' to play after '{media_playlist[current_media_index]}'.")
        media_playlist.pop(target_idx_in_playlist)
        new_pos = current_media_index + 1
        media_playlist.insert(new_pos, filename_to_set_next)
        save_playlist_to_file()
        logger.info(f"Playlist reordered. New playlist: {media_playlist}")
        return jsonify({"status": "next_item_set", "nextFile": filename_to_set_next, "playlist": media_playlist})

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
    global current_loop_mode
    data = request.get_json()
    if not data or 'mode' not in data:
        return jsonify({"error": "Mode missing in request"}), 400
        
    mode = data['mode']
    if mode not in ['none', 'file', 'playlist']:
        return jsonify({"error": "Invalid mode. Use 'none', 'file', or 'playlist'"}), 400
        
    if mpv.set_loop_mode(mode):
        current_loop_mode = mode
        return jsonify({"status": "success", "loop_mode": mode})
    return jsonify({"error": "Failed to set loop mode"}), 500

@app.route('/api/control/loop_file', methods=['POST'])
def loop_current_file():
    if mpv.toggle_loop_file():
        return jsonify({"status": "success", "message": "Loop toggled for current file"})
    return jsonify({"status": "error", "message": "Failed to toggle loop"}), 500

@app.route('/api/playlist/delete', methods=['POST'])
def delete_file_from_playlist():
    global media_playlist, current_media_index, is_playing, image_advance_timer
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

    if image_advance_timer and image_advance_timer.is_alive() and \
       hasattr(image_advance_timer, 'args') and image_advance_timer.args and \
       image_advance_timer.args[0] == filename:
        cancel_image_advance_timer()
        logger.debug(f"Cancelled image timer because the timed file {filename} is being deleted.")

    save_playlist_to_file()
    logger.info(f"Deleted '{filename}' from playlist.")
    return jsonify({"status": "deleted", "filename": filename, "playlist": media_playlist})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    logger.debug(f"Request for uploaded file: {filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/mpv/restart', methods=['POST'])
def restart_mpv_route():
    logger.info("API call to restart MPV.")
    mpv.terminate_player()
    time.sleep(0.5)
    if mpv.start_player():
        logger.info("MPV restarted successfully via API.")
        return jsonify({"status": "mpv_restarted"}), 200
    else:
        logger.error("Failed to restart MPV via API.")
        return jsonify({"error": "Failed to restart MPV."}), 500

@app.teardown_appcontext
def teardown_mpv(exception=None):
    pass

import atexit
def cleanup_on_exit():
    logger.info("Flask application is exiting. Terminating MPV player.")
    mpv.terminate_player()
atexit.register(cleanup_on_exit)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created upload folder: {UPLOAD_FOLDER} on startup.")
    
    logger.info(f"Initial playlist: {media_playlist}")

    logger.info("Attempting to start MPV on Flask application startup...")
    if mpv.start_player():
        logger.info("MPV started successfully in idle mode.")
    else:
        logger.warning("MPV failed to start on application startup. It may need to be started manually or via an API call.")

    app.run(host='0.0.0.0', port=5000, debug=False)
