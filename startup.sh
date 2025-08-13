#!/usr/bin/env bash
LOCK_FILE="/tmp/startup.lock"
if [ -f "$LOCK_FILE" ]; then
    echo "⚠️ startup.sh already running — exiting."
    exit 0
fi
touch "$LOCK_FILE"
# Headless VNC + Fluxbox + Chrome bootstrap (reliable restart-ready version)

set -u  # keep running even if Chrome fails; we want logs

echo "🚀 Script started"

# ------------------ Config ------------------
export DISPLAY="${DISPLAY:-:1}"
RESOLUTION="${RESOLUTION:-2560x1440}"
GEOMETRY="$RESOLUTION"
USER_DATA_DIR="/app/chrome-profile"
VNC_PASSWORD="${VNC_PASSWORD:-password}"

echo "📡 DISPLAY set to $DISPLAY"
echo "🖥️  Resolution: $GEOMETRY"

# ------------------ Clean up old X locks ------------------
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# ------------------ Fix TigerVNC migration bug ------------------
rm -rf /root/.vnc /root/.config/tigervnc
mkdir -p /root/.vnc /root/.config/tigervnc

# ------------------ VNC password (non-interactive) ------------------
echo "$VNC_PASSWORD" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

# ------------------ Start VNC (TigerVNC) ------------------
echo "🎯 Launching VNC with built-in xterm session"
vncserver "$DISPLAY" \
  -geometry "$GEOMETRY" \
  -depth 24 \
  -xstartup /usr/bin/xterm \
  -rfbauth /root/.vnc/passwd \
  >/root/vncserver.log 2>&1 &

# ------------------ Wait for X ------------------
echo "⏳ Waiting for X server to become available..."
for i in $(seq 1 20); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    echo "✅ X is ready"
    break
  fi
  echo "  ... still waiting ($i) ..."
  sleep 1
done

if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
  echo "❌ X server failed to start. Tail of /root/vncserver.log:"
  tail -n 200 /root/vncserver.log || true
fi

# ------------------ Window manager ------------------
fluxbox >/root/fluxbox.log 2>&1 &
echo "🎨 Fluxbox launched"

# ------------------ Fix machine-id & D-Bus ------------------
rm -f /run/dbus/pid
mkdir -p /run/dbus
if [ ! -s /etc/machine-id ]; then
  if command -v dbus-uuidgen >/dev/null 2>&1; then
    dbus-uuidgen > /etc/machine-id
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-32 > /etc/machine-id
  fi
fi
[ -e /var/lib/dbus/machine-id ] || ln -sf /etc/machine-id /var/lib/dbus/machine-id
command -v dbus-daemon >/dev/null 2>&1 && dbus-daemon --system --fork >/dev/null 2>&1 || true

# Allow local root to connect to the X server
export XAUTHORITY=/root/.Xauthority
xhost +local:root >/dev/null 2>&1 || true

# ------------------ Chrome ------------------
CHROME_BIN="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser || true)"
echo "🧭 Chrome binary is: ${CHROME_BIN:-<none>}"
echo "📂 Using persistent profile: $USER_DATA_DIR"
mkdir -p "$USER_DATA_DIR"

echo "🛑 Killing any existing Chrome processes"
pkill chrome || true
echo "🔓 Cleaning Chrome profile lock files..."
find "$USER_DATA_DIR" \( -name "Singleton*" -o -name "*.pid" \) -print -delete 2>/dev/null || true

if [ -n "${CHROME_BIN:-}" ]; then
  echo "🚀 Launching Chrome..."
  "$CHROME_BIN" \
    --no-sandbox \
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
    --disable-gpu \
    --ozone-platform=x11 \
    --user-data-dir="$USER_DATA_DIR" \
    --window-position=0,0 \
    https://chatgpt.com \
    > /root/chrome.log 2>&1 &
  sleep 2
  if pgrep -f "$CHROME_BIN" >/dev/null 2>&1; then
    echo "✅ Chrome launched with persistent profile"
  else
    echo "❌ Chrome failed to start. First 200 lines of /root/chrome.log:"
    sed -n '1,200p' /root/chrome.log || true
  fi
else
  echo "❌ Chrome binary not found or not executable"
fi

# ------------------ Your automation ------------------
python3 -m agent.main >/root/agent.log 2>&1 &
echo "🤖 agent/main.py started"

# ------------------ noVNC proxy ------------------
echo "🌐 Starting noVNC on http://localhost:6080"
nohup /opt/novnc/utils/novnc_proxy --vnc localhost:5901 --listen 6080 >/root/novnc.log 2>&1 &

# ------------------ Keep container alive ------------------
echo "🛡️ Keeping container alive"
tail -f /dev/null