#!/bin/bash

echo "🚀 Script started"

export DISPLAY=:1
export GEOMETRY=2560x1440
USER_DATA_DIR="/app/chrome-profile"

# Set up VNC password
mkdir -p /root/.vnc
echo "password" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

echo "🎯 Launching VNC with built-in xterm session"
vncserver :1 -geometry $GEOMETRY -depth 24 -xstartup /usr/bin/xterm &

# Wait until X display is available
echo "⏳ Waiting for X server to become available..."
for i in {1..10}; do
    xdpyinfo -display :1 > /dev/null 2>&1 && break
    echo "  ... still waiting ..."
    sleep 1
done

echo "✅ X is ready"

# Launch Fluxbox
fluxbox > /root/fluxbox.log 2>&1 &
echo "🎨 Fluxbox launched"

# Detect Chrome binary
CHROME_BIN=$(which google-chrome || which google-chrome-stable || which chromium || which chromium-browser)

echo "🧭 Chrome binary is: $CHROME_BIN"
echo "📂 Using persistent profile: $USER_DATA_DIR"

if [ ! -x "$CHROME_BIN" ]; then
    echo "❌ Chrome binary not found or not executable"
    exit 1
fi

# Kill any zombie Chrome processes
echo "🛑 Killing any existing Chrome processes"
pkill chrome || true

# Remove stale lock files from previous crashes
echo "🔓 Cleaning Chrome profile lock files..."
echo "🔍 Files to remove:"
find "$USER_DATA_DIR" \( -name "Singleton*" -o -name "*.pid" \)
find "$USER_DATA_DIR" \( -name "Singleton*" -o -name "*.pid" \) -exec rm -f {} \;

# Launch Chrome
"$CHROME_BIN" \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --disable-extensions \
  --disable-background-networking \
  --disable-sync \
  --metrics-recording-only \
  --disable-default-apps \
  --no-first-run \
  --no-default-browser-check \
  --disable-popup-blocking \
  --disable-translate \
  --user-data-dir="$USER_DATA_DIR" \
  --force-dark-mode \
   --start-maximized \
  https://chatgpt.com \
  > /root/chrome.log 2>&1 &
  #--window-size=2560,1440 \
  #--start-fullscreen \
sleep 2

# Confirm Chrome started successfully
if ! pgrep -f "$CHROME_BIN" > /dev/null; then
    echo "❌ Chrome failed to start. Log output:"
    cat /root/chrome.log
    exit 1
fi

echo "✅ Chrome launched with persistent profile"

# Start your automation script
python3 -m agent.main &
echo "🤖 agent/main.py started"

# Start noVNC
echo "🌐 Starting noVNC on http://localhost:6080"
nohup /opt/novnc/utils/novnc_proxy --vnc localhost:5901 --listen 6080 > /dev/null 2>&1 &

# Keep container alive
tail -f /dev/null
echo "🛡️ Keeping container alive"