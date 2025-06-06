#!/bin/bash

# transcode_videos.sh
# Description: Transcodes video files using ffmpeg with parameters from .env file.
# 
# Usage: 
#   - Without arguments: Processes all videos in FFMPEG_INPUT_DIR
#   - With file path argument: Processes only the specified file
#
# WARNING: This script OVERWRITES the original video files with transcoded versions.
# Default input/output directory: app/uploads

# Load environment variables from .env file if it exists
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
  # Use 'set -a' to automatically export all variables
  set -a
  source "$ENV_FILE"
  set +a
fi

# --- Configuration ---
# Read from .env or use defaults
INPUT_DIR="${FFMPEG_INPUT_DIR:-app/uploads}"
SCALE="${FFMPEG_SCALE:-240:320}"
FPS="${FFMPEG_FPS:-15}"
VIDEO_BITRATE="${FFMPEG_VIDEO_BITRATE:-300k}"
AUDIO_BITRATE="${FFMPEG_AUDIO_BITRATE:-64k}"
VIDEO_CODEC="${FFMPEG_VIDEO_CODEC:-libx264}"
AUDIO_CODEC="${FFMPEG_AUDIO_CODEC:-aac}"

# --- Function to transcode a single file ---
transcode_file() {
  local f="$1"
  
  # Skip non-video files
  if ! [[ "$f" =~ \.(mp4|mkv|avi|mov|webm)$ ]]; then
    echo "Skipping non-video file: $f"
    return 0
  fi
  
  local filename=$(basename -- "$f")
  # Temporary file will be in the same directory as the original
  local temp_output_file="${f}.__transcoding_temp__.mp4" 

  echo "Processing: $f"
  echo "Transcoding to temporary file: $temp_output_file"

  # Transcode to temporary file
  ffmpeg -i "$f" -vf "scale=$SCALE" -r "$FPS" -b:v "$VIDEO_BITRATE" -c:v "$VIDEO_CODEC" -c:a "$AUDIO_CODEC" -b:a "$AUDIO_BITRATE" "$temp_output_file" -y
  
  if [ $? -eq 0 ]; then
    echo "Successfully transcoded to temporary file."
    echo "Replacing original file: $f"
    # Replace original with transcoded temporary file
    mv "$temp_output_file" "$f"
    if [ $? -eq 0 ]; then
        echo "Successfully replaced $filename."
        return 0
    else
        echo "Error: Failed to replace $filename with $temp_output_file."
        return 1
    fi
  else
    echo "Error: Transcoding failed for $filename. Original file remains unchanged."
    # Remove temporary file if it exists and transcoding failed
    if [ -f "$temp_output_file" ]; then
        rm "$temp_output_file"
    fi
    return 1
  fi
}

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null
then
    echo "ffmpeg could not be found. Please install ffmpeg."
    exit 1
fi

# If a specific file is provided as argument, only process that file
if [ "$1" != "" ]; then
  SPECIFIC_FILE="$1"
  
  if [ -f "$SPECIFIC_FILE" ]; then
    echo "Processing single file: $SPECIFIC_FILE"
    transcode_file "$SPECIFIC_FILE"
    exit $?
  else
    echo "Error: File not found: $SPECIFIC_FILE"
    exit 1
  fi
fi

# Otherwise, continue with directory processing
# Ensure input directory exists
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' not found."
    exit 1
fi

echo "Starting video transcoding (OVERWRITE MODE)..."
echo "WARNING: Original files in '$INPUT_DIR' will be replaced."
echo "Input/Output directory: $INPUT_DIR"
echo "Scale: $SCALE"
echo "FPS: $FPS"
echo "Video Bitrate: $VIDEO_BITRATE"
echo "Audio Bitrate: $AUDIO_BITRATE"
echo "Video Codec: $VIDEO_CODEC"
echo "Audio Codec: $AUDIO_CODEC"
echo "---"
echo "You have 5 seconds to cancel (Ctrl+C)..."
sleep 5

# Find all .mp4 files in the input directory (case-insensitive for extension)
# Use find ... -print0 and while read -d $' ' to handle filenames with spaces or special characters
find "$INPUT_DIR" -type f -iname "*.mp4" -print0 | while IFS= read -r -d $' ' f; do
  filename=$(basename -- "$f")
  # Temporary file will be in the same directory as the original
  temp_output_file="${f}.__transcoding_temp__.mp4" 

  echo "Processing: $f"
  echo "Transcoding to temporary file: $temp_output_file"

  # Transcode to temporary file
  ffmpeg -i "$f" -vf "scale=$SCALE" -r "$FPS" -b:v "$VIDEO_BITRATE" -c:v "$VIDEO_CODEC" -c:a "$AUDIO_CODEC" -b:a "$AUDIO_BITRATE" "$temp_output_file" -y
  
  if [ $? -eq 0 ]; then
    echo "Successfully transcoded to temporary file."
    echo "Replacing original file: $f"
    # Replace original with transcoded temporary file
    mv "$temp_output_file" "$f"
    if [ $? -eq 0 ]; then
        echo "Successfully replaced $filename."
    else
        echo "Error: Failed to replace $filename with $temp_output_file."
        echo "The transcoded temporary file might still exist: $temp_output_file"
        echo "The original file might be: $f (or it might have been moved/deleted if mv started but failed)"
    fi
  else
    echo "Error: Transcoding failed for $filename. Original file remains unchanged."
    # Remove temporary file if it exists and transcoding failed
    if [ -f "$temp_output_file" ]; then
        rm "$temp_output_file"
    fi
  fi
  echo "---"
done

echo "Transcoding complete."
