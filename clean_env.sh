#!/bin/bash
# This script cleans the environment by removing log files, playlist files, and uploaded videos.

sudo systemctl stop simple_media_player.service

# Remove log files
rm -f /home/pi/development/simple_pi_media_player/gunicorn_error.log
rm -f /home/pi/development/simple_pi_media_player/gunicorn.log
rm -f /home/pi/development/simple_pi_media_player/mplayer.log
rm -f /home/pi/development/simple_pi_media_player/server.log

# Remove playlist files
rm -f /home/pi/development/simple_pi_media_player/playlist.json
rm -f /home/pi/development/simple_pi_media_player/temp_playlist.txt

# Remove uploaded mp4 files
rm -f /home/pi/development/simple_pi_media_player/app/uploads/*.mp4

echo "Environment cleaned."
