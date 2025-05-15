#!/bin/bash

# Improved restart script for the media player application with focus on image auto-advance fix

echo "Stopping any existing media player application..."
pkill -f "python3 app/main.py" || true

# Wait for processes to stop
sleep 2

# Remove socket file if it exists (sometimes it causes issues on restart)
if [ -S "/home/luque/Documents/work/fiver/kanga2/mpvsocket" ]; then
    echo "Removing stale MPV socket file..."
    rm -f /home/luque/Documents/work/fiver/kanga2/mpvsocket
fi

echo "Restarting media player application..."
cd /home/luque/Documents/work/fiver/kanga2/
python3 app/main.py
