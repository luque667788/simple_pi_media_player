#!/bin/bash

# Navigate to the application directory (adjust if your script is not in the root)
APP_DIR=$(pwd)

# Update package list and install python3-venv and mplayer
sudo apt-get update
sudo apt-get install -y python3-venv mplayer ffmpeg # Added ffmpeg

# Create a virtual environment named 'videoplayer' (if it doesn't exist)
if [ ! -d "videoplayer" ]; then
  python3 -m venv videoplayer
  echo "Virtual environment 'videoplayer' created."
else
  echo "Virtual environment 'videoplayer' already exists."
fi

# Activate the virtual environment
source videoplayer/bin/activate

# Install dependencies from requirements.txt
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
  echo "Dependencies installed."
else
  echo "requirements.txt not found. Please ensure it's in the application directory."
  exit 1
fi

# Deactivate (optional, as the script ends here, but good practice)
deactivate

# Make other scripts executable
chmod +x run_prod.sh stop_app.sh restart_app.sh transcode_videos.sh # Added transcode_videos.sh

echo "Installation complete."
echo "To activate the environment, run: source videoplayer/bin/activate"
