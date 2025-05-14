# Project Overview

## 1. Introduction

This document outlines the plan for a simple web application designed to display slideshows and videos using MPV media player. The application will run on a Raspberry Pi 4 Model B and will be controlled via a web interface. The primary goal is simplicity and robustness.

## 2. Goals

*   Display images and videos in a sequence (slideshow).
*   Support basic transitions: fade, dissolve, slide.
*   Allow users to upload media files.
*   Provide controls for play, pause, skip next, skip previous, and stop (black screen).
*   Allow users to select the next media item to play.
*   Support looping of the media queue.
*   Ensure the display is optimized for a 2-inch screen (240x320 resolution).
*   Log server activity to files for later inspection.
*   Provide a simple installation script for Raspberry Pi.

## 3. Technology Stack

*   **Frontend**: Vanilla JavaScript, HTML, CSS
*   **Backend**: Flask (Python)
*   **Media Player**: MPV
*   **Database**: SQLite (for media metadata, if absolutely necessary, otherwise filesystem-based)
*   **Operating System**: Raspberry Pi OS (Debian-based Linux)

## 4. Project Structure (Tentative)

```
/project_root
|-- /app
|   |-- /static
|   |   |-- /css
|   |   |   |-- style.css
|   |   |-- /js
|   |   |   |-- main.js
|   |-- /templates
|   |   |-- index.html
|   |-- /uploads
|   |   |-- (media files will be stored here)
|   |-- main.py         # Flask application
|   |-- mpv_controller.py # Module to control MPV
|   |-- database.py     # SQLite interaction (if needed)
|-- install.sh        # Installation script for Raspberry Pi
|-- copilot_instructions_overview.md
|-- copilot_instructions_frontend.md
|-- copilot_instructions_backend.md
|-- copilot_instructions_mpv_integration.md
|-- copilot_instructions_raspberry_pi_setup.md
|-- copilot_instructions_logging.md
|-- server.log        # Server logs
|-- mpv.log           # MPV logs
```

## 5. Core Principles

*   **Simplicity**: Keep the codebase and features minimal and easy to understand.
*   **Robustness**: Ensure the application is stable and can run for extended periods without crashing.
*   **User-Friendliness**: The web interface should be intuitive, especially considering the small screen size for the output display (not the control interface).
*   **Raspberry Pi Optimization**: All components should be lightweight and performant enough for the Raspberry Pi 4.
