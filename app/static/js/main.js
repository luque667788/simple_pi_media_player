document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
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

    const playlistUl = document.getElementById('playlistUl');

    const currentFileSpan = document.getElementById('currentFile');
    const playerStateSpan = document.getElementById('playerState');
    const mpvProcessStatusSpan = document.getElementById('mpvProcessStatus');
    const refreshStatusButton = document.getElementById('refreshStatusButton');
    const restartMpvButton = document.getElementById('restartMpvButton');

    // --- API Helper ---
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

    // --- UI Update Functions ---
    function updatePlaylistUI(playlist = [], currentFile = null, loop_mode = 'none') {
        playlistUl.innerHTML = '';
        if (!Array.isArray(playlist)) {
            console.error("Playlist data is not an array:", playlist);
            playlist = [];
        }
        playlist.forEach((item, index) => {
            const li = document.createElement('li');

            // Play button/text
            const playSpan = document.createElement('span');
            playSpan.textContent = item;
            playSpan.className = 'play-title';
            if (item === currentFile) {
                li.classList.add('playing');
            }
            playSpan.addEventListener('click', () => playSpecificFile(item));

            // Set-next button
            const nextButton = document.createElement('button');
            nextButton.textContent = 'Play Next';
            nextButton.className = 'play-next-btn';
            nextButton.addEventListener('click', (e) => {
                e.stopPropagation();
                setNextTrack(item);
            });
            // Show/hide Play Next button based on loop_mode
            if (loop_mode === 'playlist') {
                nextButton.style.display = '';
            } else {
                nextButton.style.display = 'none';
            }

            // Add delete button
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Delete';
            deleteButton.className = 'delete-btn';
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

            li.dataset.filename = item;
            li.appendChild(playSpan);
            li.appendChild(nextButton);
            li.appendChild(deleteButton); // Add the delete button
            playlistUl.appendChild(li);
        });
    }

    function updateStatusUI(data) {
        if (!data) return;
        currentFileSpan.textContent = data.currentFile || 'None';
        playerStateSpan.textContent = data.isPlaying ? 'Playing' : 'Paused/Idle';
        if(data.status === "playlist_empty") playerStateSpan.textContent = "Playlist Empty";
        if(data.status === "playlist_ended") playerStateSpan.textContent = "Playlist Ended";
        if(data.status === "stopped") playerStateSpan.textContent = "Stopped (Black Screen)";
        
        // Update loop mode dropdown
        if (data.loop_mode) {
            loopModeSelect.value = data.loop_mode;
        }
        mpvProcessStatusSpan.textContent = data.mpv_is_running ? "Running" : "Not Running/Error";
        // Update playlist UI, passing loop_mode
        updatePlaylistUI(data.playlist, data.currentFile, data.loop_mode);
        // Show/hide global next/prev buttons based on loop_mode
        if (data.loop_mode === 'playlist') {
            prevButton.style.display = '';
            nextButton.style.display = '';
        } else {
            prevButton.style.display = 'none';
            nextButton.style.display = 'none';
        }
    }

    // --- Event Handlers & API Calls ---
    async function fetchAndRefreshStatus() {
        const data = await fetchAPI('/playlist');
        if (data) {
            updateStatusUI(data);
        }
    }

    uploadButton.addEventListener('click', async () => {
        if (mediaUploadInput.files.length === 0) {
            uploadStatus.textContent = 'Please select files to upload.';
            uploadStatus.className = 'error-message';
            return;
        }
        const formData = new FormData();
        for (const file of mediaUploadInput.files) {
            formData.append('mediaFiles', file);
        }
        uploadStatus.textContent = 'Uploading...';
        uploadStatus.className = '';
        const response = await fetchAPI('/upload', 'POST', formData);
        if (response) {
            uploadStatus.textContent = response.message || 'Upload processed.';
            if (response.errors && response.errors.length > 0) {
                uploadStatus.textContent += ` Errors: ${response.errors.join(', ')}`;
                uploadStatus.className = 'error-message';
            } else {
                uploadStatus.className = 'success-message';
            }
            mediaUploadInput.value = ''; // Clear file input
            fetchAndRefreshStatus(); // Refresh playlist and status
        }
    });

    async function playSpecificFile(filename) {
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
        const response = await fetchAPI('/control/stop', 'POST');
        if (response) updateStatusUI(response);
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
        // First, restart MPV process
        uploadStatus.textContent = 'Restarting MPV process for mode change...';
        uploadStatus.className = '';
        const restartResp = await fetchAPI('/mpv/restart', 'POST');
        if (!restartResp || restartResp.status !== 'mpv_restarted') {
            uploadStatus.textContent = restartResp?.error || 'Failed to restart MPV for mode change.';
            uploadStatus.className = 'error-message';
            return;
        }
        // Wait a moment to ensure MPV is up
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
        if(confirm("Are you sure you want to restart the MPV process? This might interrupt playback.")){
            uploadStatus.textContent = 'Restarting MPV process...';
            uploadStatus.className = '';
            const response = await fetchAPI('/mpv/restart', 'POST');
            if (response && response.status === "mpv_restarted"){
                uploadStatus.textContent = 'MPV process restart initiated.';
                uploadStatus.className = 'success-message';
            } else {
                uploadStatus.textContent = response.error || 'Failed to initiate MPV restart.';
                uploadStatus.className = 'error-message';
            }
            setTimeout(fetchAndRefreshStatus, 1500); // Give MPV time to restart before refreshing status
        }
    });

    // --- Initial Load ---
    fetchAndRefreshStatus();
    setInterval(fetchAndRefreshStatus, 10000); // Periodically refresh status every 10 seconds

});
