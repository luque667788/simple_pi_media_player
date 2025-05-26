#!/bin/bash

set -e  # Exit on any error
set -o pipefail

echo "📦 Updating and upgrading system..."
apt update && apt full-upgrade -y

echo "🧰 Installing required tools..."
apt install -y git curl raspi-config

echo "🔐 Enabling SSH..."
raspi-config nonint do_ssh 0

echo "📡 Enabling SPI and I2C..."
raspi-config nonint do_spi 0
raspi-config nonint do_i2c 0

echo "🖼️ Configuring display settings in /boot/firmware/config.txt..."
BOOT_CONFIG="/boot/firmware/config.txt"

# Add framebuffer overlay for ST7789V display
CONFIG_LINE_FBTFT='dtoverlay=fbtft,spi0-0,st7789v,reset_pin=27,dc_pin=25,led_pin=18,speed=64000000,rotate=0'
if ! grep -qF "$CONFIG_LINE_FBTFT" "$BOOT_CONFIG"; then
    echo "$CONFIG_LINE_FBTFT" >> "$BOOT_CONFIG"
    echo "Added framebuffer overlay to $BOOT_CONFIG."
else
    echo "Framebuffer overlay already present in $BOOT_CONFIG."
fi

# Disable HDMI output to save power and resources
CONFIG_LINE_HDMI_BLANKING='hdmi_blanking=2'
if ! grep -qF "$CONFIG_LINE_HDMI_BLANKING" "$BOOT_CONFIG"; then
    echo "$CONFIG_LINE_HDMI_BLANKING" >> "$BOOT_CONFIG"
    echo "Added HDMI blanking to $BOOT_CONFIG."
else
    echo "HDMI blanking setting already present in $BOOT_CONFIG."
fi

echo "📁 Verifying framebuffer /dev/fb1 exists..."
FRAMEBUFFER_PATH="/dev/fb1"
if [ -e "$FRAMEBUFFER_PATH" ]; then
    echo "✅ Framebuffer $FRAMEBUFFER_PATH exists."
else
    echo "⚠️ Framebuffer $FRAMEBUFFER_PATH not found. It might become available after a reboot."
fi

echo "🌐 Installing RaspAP (Manual Step Required)..."
echo "👉 Please install RaspAP by running the following command in your terminal:"
echo "   curl -sL https://install.raspap.com | bash"
# The original script intentionally commented this out, requiring manual execution.
# curl -sL https://install.raspap.com | bash

echo "🧾 Updating /boot/firmware/cmdline.txt..."
CMDLINE="/boot/firmware/cmdline.txt"
NEW_CMDLINE='console=serial0,115200 root=PARTUUID=59a43f33-02 rootfstype=ext4 fsck.repair=yes rootwait cfg80211.ieee80211_regdom=DE fbcon=map:2'
echo "$NEW_CMDLINE" > "$CMDLINE"

echo "📂 Creating development folder and cloning media player repo..."
mkdir -p /home/pi/development
cd /home/pi/development
git clone https://github.com/luque667788/simple_pi_media_player.git

echo "🔧 Running install script from the media player repo..."
cd /home/pi/development/simple_pi_media_player
chmod +x /home/pi/development/simple_pi_media_player/install.sh
/home/pi/development/simple_pi_media_player/install.sh

echo "🛠️ Setting up systemd service..."
SERVICE_FILE="/etc/systemd/system/simple_media_player.service"

cat <<EOF > "$SERVICE_FILE"
# 

[Unit]
Description=Simple Media Player Service
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash /home/pi/development/simple_pi_media_player/run_prod.sh
ExecStop=/bin/bash /home/pi/development/simple_pi_media_player/stop_app.sh
ExecReload=/bin/bash /home/pi/development/simple_pi_media_player/restart_app.sh
WorkingDirectory=/home/pi/development/simple_pi_media_player
Restart=on-failure
RestartSec=5
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Reloading systemd and enabling service..."
systemctl daemon-reload
systemctl enable simple_media_player.service
systemctl start simple_media_player.service

echo "✅ Setup complete. You may want to reboot to ensure all changes take effect."
