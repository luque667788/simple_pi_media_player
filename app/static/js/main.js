document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element References ---
    const mediaUploadInput = document.getElementById('mediaUploadInput');
    const uploadButton = document.getElementById('uploadButton');
    const uploadStatus = document.getElementById('uploadStatus');

    const playButton = document.getElementById('playButton');
    const pauseButton = document.getElementById('pauseButton');
    const togglePauseButton = document.getElementById('togglePauseButton');
    const stopButton = document.getElementById('stopButton');
    const prevButton = document.getElementById('prevButton');
    const nextButton = document.getElementById('nextButton');
    const loopCheckbox = document.getElementById('loopCheckbox');
    const loopModeSelect = document.getElementById('loopModeSelect');
    
    // Playlist editing controls
    const editPlaylistButton = document.getElementById('editPlaylistButton');
    const savePlaylistButton = document.getElementById('savePlaylistButton');

    const playlistUl = document.getElementById('playlistUl');

    const currentFileSpan = document.getElementById('currentFile');
    const playerStateSpan = document.getElementById('playerState');
    const mpvProcessStatusSpan = document.getElementById('mpvProcessStatus');
    const refreshStatusButton = document.getElementById('refreshStatusButton');
    const restartMpvButton = document.getElementById('restartMpvButton');
    const endServerButton = document.getElementById('endServerButton'); // Added this line

    // Upload overlay elements
    const uploadOverlay = document.getElementById('uploadOverlay');
    const overlayStatusText = document.getElementById('overlayStatusText');

    // Application state
    let editMode = false;
    let currentPlaylistFiles = []; // Store current playlist filenames

    // --- API Communication Helper ---
    async function fetchAPI(endpoint, method = 'GET', body = null) {
        const options = {
            method: method,
            headers: {}
        };
        if (body) {
            if (body instanceof FormData) {
                // FormData sets its own Content-Type
            } else {
                options.headers['Content-Type'] = 'application/json';
            }
            options.body = (body instanceof FormData) ? body : JSON.stringify(body);
        }

        try {
            const response = await fetch(`/api${endpoint}`, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! Status: ${response.status}` }));
                console.error('API Error:', errorData);
                uploadStatus.textContent = `Error: ${errorData.error || response.statusText}`;
                uploadStatus.className = 'error-message';
                return null;
            }
            return await response.json();
        } catch (error) {
            console.error('Fetch API Error:', error);
            uploadStatus.textContent = `Network error: ${error.message}`;
            uploadStatus.className = 'error-message';
            return null;
        }
    }

    // --- UI Update Logic ---
    function updatePlaylistUI(playlist = [], currentFile = null, loop_mode = 'none') {
        playlistUl.innerHTML = '';
        if (!Array.isArray(playlist)) {
            console.error("Playlist data is not an array:", playlist);
            playlist = [];
        }
        
        // Add or remove edit-mode class based on current mode
        if (editMode) {
            playlistUl.classList.add('edit-mode');
            playlistUl.classList.remove('playlist-view-mode-active'); // Ensure this is off in edit mode
        } else {
            playlistUl.classList.remove('edit-mode');
            // Add a specific class if in playlist loop mode and not editing
            if (loop_mode === 'playlist') {
                playlistUl.classList.add('playlist-view-mode-active');
            } else {
                playlistUl.classList.remove('playlist-view-mode-active');
            }
        }
        
        playlist.forEach((item, index) => {
            const li = document.createElement('li');
            li.dataset.filename = item;
            
            if (editMode) {
                // In edit mode, add drag handle and make item draggable
                li.draggable = true;
                li.classList.add('draggable');
                
                const dragHandle = document.createElement('span');
                dragHandle.className = 'drag-handle';
                li.appendChild(dragHandle);
                
                // Drag event listeners
                li.addEventListener('dragstart', () => {
                    li.classList.add('dragging');
                });
                
                li.addEventListener('dragend', () => {
                    li.classList.remove('dragging');
                });
            }

            // Play button/text
            const playSpan = document.createElement('span');
            playSpan.textContent = item;
            playSpan.className = 'play-title';
            
            if (item === currentFile) {
                li.classList.add('playing');
            }
            
            // Only add click event if NOT in editMode AND loop_mode is NOT 'playlist'
            if (!editMode && loop_mode !== 'playlist') {
               playSpan.addEventListener('click', () => playSpecificFile(item));
            }

            // Add delete button (only visible in edit mode or if nothing is playing)
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Delete';
            deleteButton.className = 'delete-btn';
            
            // Only show delete button in edit mode or if nothing is playing
            if (!editMode && currentFile) {
                deleteButton.style.display = 'none';
            }
            
            deleteButton.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(`Delete "${item}" from playlist and disk?`)) {
                    const response = await fetchAPI('/playlist/delete', 'POST', { filename: item });
                    if (response && response.status === "deleted") {
                        uploadStatus.textContent = `"${item}" deleted.`;
                        uploadStatus.className = 'success-message';
                        fetchAndRefreshStatus();
                    } else {
                        uploadStatus.textContent = response?.error || 'Delete failed.';
                        uploadStatus.className = 'error-message';
                    }
                }
            });

            li.appendChild(playSpan);
            
            // Don't show Play Next button in either mode - it's no longer needed
            // as per the requirements
            
            li.appendChild(deleteButton);
            playlistUl.appendChild(li);
        });
        
        // Add drag-and-drop event listeners to the playlist in edit mode
        if (editMode) {
            playlistUl.addEventListener('dragover', e => {
                e.preventDefault();
                const afterElement = getDragAfterElement(playlistUl, e.clientY);
                const draggable = document.querySelector('.dragging');
                if (draggable) { // Check if draggable exists
                    if (afterElement == null) {
                        playlistUl.appendChild(draggable);
                    } else {
                        playlistUl.insertBefore(draggable, afterElement);
                    }
                } else {
                    // console.warn('Dragover event fired but no draggable element found.');
                }
            });
        }
    }
    
    // Helper to determine drag-and-drop insertion point
    function getDragAfterElement(container, y) {
        const draggableElements = [...container.querySelectorAll('.draggable:not(.dragging)')];
        
        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;
            
            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            } else {
                return closest;
            }
        }, { offset: Number.NEGATIVE_INFINITY }).element;
    }

    function updateStatusUI(data) {
        if (!data) return;
        currentFileSpan.textContent = data.currentFile || 'None';
        playerStateSpan.textContent = data.isPlaying ? 'Playing' : 'Paused/Idle';
        if(data.status === "playlist_empty") playerStateSpan.textContent = "Playlist Empty";
        if(data.status === "playlist_ended") playerStateSpan.textContent = "Playlist Ended";
        if(data.status === "stopped") playerStateSpan.textContent = "Stopped";
        
        // Update loop mode dropdown
        if (data.loop_mode) {
            loopModeSelect.value = data.loop_mode;
        }
        mpvProcessStatusSpan.textContent = data.mplayer_is_running ? "Running" : "Not Running/Error";
        
        // Update playlist UI, passing loop_mode
        updatePlaylistUI(data.playlist, data.currentFile, data.loop_mode);
        if (data.playlist && Array.isArray(data.playlist)) {
            currentPlaylistFiles = data.playlist; // Update current playlist files
        }
        
        // Show/hide global next/prev buttons based on loop_mode and not in edit mode
        if (data.loop_mode === 'playlist' && !editMode) {
            prevButton.style.display = '';
            nextButton.style.display = '';
        } else {
            prevButton.style.display = 'none';
            nextButton.style.display = 'none';
        }
        
        // Disable/enable control buttons based on edit mode
        const controlButtons = [playButton, pauseButton, togglePauseButton, stopButton, 
                               prevButton, nextButton, restartMpvButton];
        controlButtons.forEach(button => {
            button.disabled = editMode;
        });
        
        // Disable/enable upload section based on edit mode and if anything is playing
        uploadButton.disabled = editMode || data.currentFile;
        mediaUploadInput.disabled = editMode || data.currentFile;
    }

    // --- Playlist Edit Mode Management ---
    function enableEditMode() {
        editMode = true;
        editPlaylistButton.style.display = 'none';
        savePlaylistButton.style.display = 'inline-block';
        fetchAndRefreshStatus();
    }
    
    function disableEditMode() {
        editMode = false;
        editPlaylistButton.style.display = 'inline-block';
        savePlaylistButton.style.display = 'none';
        fetchAndRefreshStatus();
    }
    
    // Retrieve playlist order from UI for reordering
    function getPlaylistOrder() {
        const items = [...playlistUl.querySelectorAll('li')];
        return items.map(item => item.dataset.filename);
    }
    
    // --- Event Handlers and API Integration ---
    async function fetchAndRefreshStatus() {
        const data = await fetchAPI('/playlist');
        if (data) {
            updateStatusUI(data);
        }
    }

    if (endServerButton) {
        endServerButton.addEventListener('click', async () => {
            if (confirm('Are you sure you want to stop the server? You will need to reboot or use the command line to restart it.')) {
                const response = await fetchAPI('/server/stop', 'POST');
                if (response && response.status === 'stopping') {
                    alert('Server is stopping. The page might become unresponsive.');
                    // Optionally, disable UI elements here
                    document.querySelectorAll('button, input, select').forEach(el => el.disabled = true);
                } else {
                    alert('Failed to send stop command to server or server already stopped.');
                }
            }
        });
    }

    uploadButton.addEventListener('click', async () => {
        if (mediaUploadInput.files.length === 0) {
            uploadStatus.textContent = 'Please select files to upload.';
            uploadStatus.className = 'error-message';
            return;
        }
        const selectedFile = mediaUploadInput.files[0];

        // Feature 1: Prevent Re-upload of Existing Files
        if (currentPlaylistFiles.includes(selectedFile.name)) {
            uploadStatus.textContent = `Error: File "${selectedFile.name}" already exists in the playlist.`;
            uploadStatus.className = 'error-message';
            mediaUploadInput.value = ''; // Clear file input
            return;
        }

        const formData = new FormData();
        formData.append('mediaFiles', selectedFile);

        // Show overlay
        overlayStatusText.textContent = `Uploading "${selectedFile.name}"... Please wait.`;
        uploadOverlay.style.display = 'flex';
        // Disable all buttons and inputs during upload
        document.querySelectorAll('button, input, select').forEach(el => el.disabled = true);

        uploadStatus.textContent = 'Uploading...';
        uploadStatus.className = '';
        const response = await fetchAPI('/upload', 'POST', formData);

        if (response && response.files_accepted && response.files_accepted.length > 0) {
            const uploadedFilename = response.files_accepted[0];
            overlayStatusText.textContent = `Transcoding "${uploadedFilename}"... This may take a while.`;
            // Don't hide overlay or re-enable inputs yet. Start polling.
            pollForFileInPlaylist(uploadedFilename);
        } else {
            // Upload failed or was not accepted by the backend for processing
            uploadOverlay.style.display = 'none';
            document.querySelectorAll('button, input, select').forEach(el => el.disabled = false);
            // fetchAPI would have set an error message in uploadStatus
            if (!response) { // If fetchAPI itself failed
                uploadStatus.textContent = uploadStatus.textContent || 'Upload request failed.';
                uploadStatus.className = 'error-message';
            } else if (response.error) { // If backend returned a specific error for the upload
                 uploadStatus.textContent = response.error;
                 uploadStatus.className = 'error-message';
            } else if (response.errors && response.errors.length > 0) {
                uploadStatus.textContent = `Upload error: ${response.errors.map(e => e.error || e.filename).join(', ')}`;
                uploadStatus.className = 'error-message';
            }
             else {
                uploadStatus.textContent = response.message || 'Upload processed, but file not queued for transcoding.';
                uploadStatus.className = 'error-message'; // Treat as error if not accepted
            }
            mediaUploadInput.value = ''; // Clear file input
            fetchAndRefreshStatus(); // Refresh status to correctly set disabled states
        }
    });

    async function pollForFileInPlaylist(filenameToWaitFor, maxAttempts = 60, interval = 5000) { // Poll for 5 minutes (60 * 5s)
        let attempts = 0;

        const poller = setInterval(async () => {
            attempts++;
            console.log(`Polling for ${filenameToWaitFor}, attempt ${attempts}`);
            const statusData = await fetchAPI('/playlist');

            if (statusData && statusData.playlist && statusData.playlist.includes(filenameToWaitFor)) {
                clearInterval(poller);
                uploadOverlay.style.display = 'none';
                document.querySelectorAll('button, input, select').forEach(el => el.disabled = false);
                
                uploadStatus.textContent = `"${filenameToWaitFor}" successfully added and ready.`;
                uploadStatus.className = 'success-message';
                mediaUploadInput.value = ''; // Clear file input
                fetchAndRefreshStatus(); // Final full refresh
                return;
            }

            if (attempts >= maxAttempts) {
                clearInterval(poller);
                uploadOverlay.style.display = 'none';
                document.querySelectorAll('button, input, select').forEach(el => el.disabled = false);
                uploadStatus.textContent = `Error: Timed out waiting for "${filenameToWaitFor}" to appear in playlist. Check server logs.`;
                uploadStatus.className = 'error-message';
                mediaUploadInput.value = '';
                fetchAndRefreshStatus();
            }
        }, interval);
    }

    async function playSpecificFile(filename) {
        uploadStatus.textContent = `Stopping current playback to play "${filename}"...`;
        uploadStatus.className = '';
        const stopResp = await fetchAPI('/control/stop', 'POST');

        if (!stopResp || (stopResp.status !== "stopped" && stopResp.currentFile !== null && stopResp.status !== "playlist_empty")) {
            uploadStatus.textContent = stopResp?.error || `Failed to stop player before playing "${filename}".`;
            uploadStatus.className = 'error-message';
            fetchAndRefreshStatus(); // Refresh status to reflect actual state
            return;
        }

        // Wait a brief moment to ensure the stop command is processed
        await new Promise(resolve => setTimeout(resolve, 200));

        uploadStatus.textContent = `Playing "${filename}"...`;
        uploadStatus.className = '';
        const response = await fetchAPI('/control/play', 'POST', { filename });
        if (response) updateStatusUI(response);
        fetchAndRefreshStatus(); // Get full status update
    }
    
    async function setNextTrack(filename) {
        uploadStatus.textContent = `Setting "${filename}" to play next...`;
        uploadStatus.className = '';
        const response = await fetchAPI('/playlist/set_next', 'POST', { filename });
        if (response) {
            uploadStatus.textContent = `"${filename}" will play next after current file finishes.`;
            uploadStatus.className = 'success-message';
            fetchAndRefreshStatus(); // Refresh to see updated playlist order
        }
    }

    playButton.addEventListener('click', async () => {
        const response = await fetchAPI('/control/play', 'POST');
        if (response) updateStatusUI(response);
        fetchAndRefreshStatus();
    });

    pauseButton.addEventListener('click', async () => {
        const response = await fetchAPI('/control/pause', 'POST');
        if (response) updateStatusUI(response);
        fetchAndRefreshStatus();
    });

    togglePauseButton.addEventListener('click', async () => {
        const response = await fetchAPI('/control/toggle_pause', 'POST');
        if (response) updateStatusUI(response);
        fetchAndRefreshStatus();
    });

    stopButton.addEventListener('click', async () => {
        const stopResp = await fetchAPI('/control/stop', 'POST');
        if (!stopResp || (stopResp.status !== "stopped" && stopResp.currentFile !== null)) {
            uploadStatus.textContent = stopResp?.error || 'Failed to stop MPlayer.';
            uploadStatus.className = 'error-message';
            // Attempt to refresh status anyway, as loop mode might still be settable
            fetchAndRefreshStatus();
            return;
        }
        uploadStatus.textContent = 'MPlayer process stopped. Setting screen to black. Press play to start again.';
        fetchAndRefreshStatus();
    });

    nextButton.addEventListener('click', async () => {
        const response = await fetchAPI('/control/next', 'POST');
        if (response) updateStatusUI(response);
        fetchAndRefreshStatus();
    });

    prevButton.addEventListener('click', async () => {
        const response = await fetchAPI('/control/previous', 'POST');
        if (response) updateStatusUI(response);
        fetchAndRefreshStatus();
    });

    loopModeSelect.addEventListener('change', async () => {
        const mode = loopModeSelect.value;
        // First, restart MPlayer process
        uploadStatus.textContent = 'Restarting MPlayer process for mode change...';
        uploadStatus.className = '';
        const stopResp = await fetchAPI('/control/stop', 'POST');
        if (!stopResp || (stopResp.status !== "stopped" && stopResp.currentFile !== null)) {
            uploadStatus.textContent = stopResp?.error || 'Failed to stop MPlayer for mode change.';
            uploadStatus.className = 'error-message';
            // Attempt to refresh status anyway, as loop mode might still be settable
            fetchAndRefreshStatus();
            return;
        }
        uploadStatus.textContent = 'MPlayer process stopped. Setting loop mode...';
        uploadStatus.className = '';
        // Wait a moment to ensure MPlayer is up
        await new Promise(res => setTimeout(res, 700));
        // Now set the loop mode
        const response = await fetchAPI('/settings/loop_mode', 'POST', { mode: mode });
        if (response && response.loop_mode === mode) {
            uploadStatus.textContent = `Loop mode set to: ${mode}`;
            uploadStatus.className = 'success-message';
            updateStatusUI(response); // Optionally update UI with new status
        } else {
            console.log('Failed to set loop mode:', response);
            uploadStatus.textContent = response?.error || 'Failed to set loop mode (and no error message).';
            uploadStatus.className = 'error-message';
        }
    });

    refreshStatusButton.addEventListener('click', fetchAndRefreshStatus);

    restartMpvButton.addEventListener('click', async () => {
        if(confirm("Are you sure you want to restart the MPlayer process? This might interrupt playback.")){
            uploadStatus.textContent = 'Restarting MPlayer process...';
            uploadStatus.className = '';
            // First, stop the player
            const stopResponse = await fetchAPI('/control/stop', 'POST');
            if (stopResponse && (stopResponse.status === "stopped" || stopResponse.currentFile === null)) {
                uploadStatus.textContent = 'Player stopped. Attempting to restart playback...';
                uploadStatus.className = '';

                // Then, try to play again (which effectively restarts if it was playing or starts if it was stopped)
                // We wait a very short moment to ensure the stop command has fully processed on the backend
                await new Promise(resolve => setTimeout(resolve, 200)); 
                const playResponse = await fetchAPI('/control/play', 'POST');

                if (playResponse && playResponse.status === "playing") {
                    updateStatusUI(playResponse);
                    // Update the status message to indicate successful restart
                    uploadStatus.textContent = 'MPlayer process effectively restarted (stopped and started).';
                    uploadStatus.className = 'success-message';
                } else if (playResponse && playResponse.status === "playlist_empty") {
                    uploadStatus.textContent = 'Player stopped. Playlist is empty, cannot restart playback.';
                    uploadStatus.className = 'success-message';
                }
                else {
                    uploadStatus.textContent = playResponse?.error || 'Failed to restart playback after stopping.';
                    uploadStatus.className = 'error-message';
                }
            } else {
                uploadStatus.textContent = stopResponse?.error || 'Failed to stop MPlayer as part of restart.';
                uploadStatus.className = 'error-message';
            }
            setTimeout(fetchAndRefreshStatus, 1500); // Give MPlayer time to restart before refreshing status
        }
    });

    // Playlist edit/save button event handlers
    editPlaylistButton.addEventListener('click', async () => {
        // First stop the player if it's running
        const response = await fetchAPI('/control/stop', 'POST');
        if (response) {
            uploadStatus.textContent = 'Entered edit mode. Player stopped. After saving, press Play to restart playback.';
            uploadStatus.className = 'success-message';
            enableEditMode();
        }
    });
    
    savePlaylistButton.addEventListener('click', async () => {
        const newOrder = getPlaylistOrder();
        uploadStatus.textContent = 'Saving new playlist order...';
        uploadStatus.className = '';
        
        // Send the new playlist order to the backend
        const response = await fetchAPI('/playlist/reorder', 'POST', { order: newOrder });
        if (response && response.status === "reordered") {
            uploadStatus.textContent = 'Playlist order saved successfully, press play to restart the playaback.';
            uploadStatus.className = 'success-message';
            disableEditMode();
        } else {
            uploadStatus.textContent = response?.error || 'Failed to save playlist order.';
            uploadStatus.className = 'error-message';
        }
    });

    // --- Initial UI Load ---
    fetchAndRefreshStatus();
    
    // Track last known playback state for change detection
    let lastKnownFile = null;
    let lastKnownPlayingState = false;
    
    // Periodic polling for UI state updates
    setInterval(async () => {
        const status = await fetchAPI('/playlist');
        if (!status) return;
        
        // Detect if something important has changed
        const fileChanged = status.currentFile !== lastKnownFile;
        const playStateChanged = status.isPlaying !== lastKnownPlayingState;
        
        // Update UI if there are changes or in playlist mode
        if (fileChanged || playStateChanged || (status.loop_mode === 'playlist' && status.isPlaying)) {
            console.log(`Updating UI due to changes: fileChanged=${fileChanged}, playStateChanged=${playStateChanged}`);
            updateStatusUI(status);
            lastKnownFile = status.currentFile;
            lastKnownPlayingState = status.isPlaying;
        }
    }, 3000); // Poll every 3 seconds for responsiveness

});
