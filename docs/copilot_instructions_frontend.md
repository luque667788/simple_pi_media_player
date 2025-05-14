# Frontend Specifications

## 1. Overview

The frontend will be a simple, single-page web application built with Vanilla JavaScript, HTML, and CSS. It will provide the user interface for controlling the media playback.

## 2. Pages and UI Elements

### 2.1. Main Control Page (`index.html`)

This will be the only page of the application.

**Layout:**

*   The interface should be clean and simple, with large, easy-to-press buttons suitable for any device accessing the web UI (the 2-inch screen is for MPV output, not this control UI).

**UI Elements:**

1.  **Media Upload Section:**
    *   A file input button: `<input type="file" id="mediaUpload" accept="image/*,video/*" multiple>`
    *   An "Upload" button to submit selected files.
    *   A visual indicator for upload progress (optional, for simplicity might be omitted initially).

2.  **Playback Controls Section:**
    *   **Play Button**: Initiates playback of the current or first item in the queue.
    *   **Pause Button**: Pauses the currently playing media.
    *   **Stop (Black Screen) Button**: Stops playback and displays a black screen via MPV.
    *   **Next Button**: Skips to the next media item in the queue.
    *   **Previous Button**: Goes back to the previous media item in the queue.

3.  **Media Queue/Selection Section:**
    *   A list displaying uploaded media items (filenames).
    *   Each item in the list should be clickable to select it as the *next* item to play.
    *   A visual indication of the currently playing item (e.g., highlighting).
    *   A "Clear Queue" button (optional, for simplicity might be omitted).

4.  **Loop Toggle:**
    *   A checkbox or toggle switch: "Loop Playlist". When enabled, the playlist will restart from the beginning after the last item.

5.  **Transition Selection (Optional - for simplicity, this might be a fixed setting or cycled through):
    *   Dropdown or radio buttons to select transition type: Fade, Dissolve, Slide.
    *   (Design decision: This could also be a backend setting to keep the frontend simpler).

## 3. JavaScript Logic (`main.js`)

*   **Event Handling:**
    *   Handle clicks on all buttons (Upload, Play, Pause, Stop, Next, Previous, media items, Loop toggle).
    *   Handle file selection from the upload input.
*   **API Communication:**
    *   Send requests to the Flask backend API endpoints for all actions (upload, play, pause, etc.).
    *   Fetch the current media queue/playlist from the backend to display it.
    *   Update the UI based on responses from the backend (e.g., update current playing item, show errors).
*   **Dynamic UI Updates:**
    *   Dynamically populate the media queue list.
    *   Update button states (e.g., disable Play if nothing is in the queue, toggle Play/Pause button text/icon).

## 4. Styling (`style.css`)

*   Simple and clean design.
*   Clear visual feedback for button presses and active states.
*   Responsive enough to be usable on various screen sizes (for the control interface, not the 2-inch display).

## 5. Workflow Example

1.  User opens the web page.
2.  User clicks the file input, selects one or more image/video files.
3.  User clicks "Upload". Files are sent to the backend.
4.  The media queue list on the page updates with the uploaded filenames.
5.  User clicks "Play". The first item in the queue starts playing on the Raspberry Pi's 2-inch screen via MPV.
6.  User uses Next/Previous to navigate.
7.  User clicks on a specific media item in the list; it becomes the next item to play after the current one finishes (or immediately if specified).
8.  User clicks "Stop". MPV shows a black screen.

## 6. Simplification Notes

*   To keep it extremely simple, the "select next item" feature could be simplified to just reordering the queue or simply playing the selected item next if playback is stopped.
*   Transition selection on the frontend adds complexity; it might be better to have a default or a backend-configured cycle of transitions.
