@'
#!/usr/bin/env bash
# Headless GUI: Xvfb + x11vnc + Fluxbox + Chrome + noVNC + agent
set -u

echo "🚀 Script started"

export DISPLAY="${DISPLAY:-:1}"
RESOLUTION="${RESOLUTION:-2560x1440}"
SCREEN="${RESOLUTION}x24"
VNC_PASSWORD="${VNC_PASSWORD:-password}"
USER_DATA_DIR="/app/chrome-profile"

echo "📡 DISPLAY: $DISPLAY"
echo "🖥️  Resolution: $RESOLUTION"

mkdir -p /root/.vnc
if [ ! -s /root/.vnc/passwd ]; then
  echo "🔐 Creating VNC password file"
  x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd >/dev/null 2>&1
  chmod 600 /root/.vnc/passwd
fi

echo "🎯 Starting Xvfb at $DISPLAY ($SCREEN)"
Xvfb "$DISPLAY" -screen 0 "$SCREEN" -ac +extension GLX +extension RANDR +render -noreset \
  >/root/xvfb.log 2>&1 &

echo "⏳ Waiting for X server to become available..."
for i in $(seq 1 30); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    echo "✅ X is ready"
    break
  fi
  echo "  ... still waiting ($i) ..."
  sleep 1
done

if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
  echo "❌ X server failed to start. Last lines of /root/xvfb.log:"
  tail -n 200 /root/xvfb.log || true
fi

echo "🎨 Launching Fluxbox"
fluxbox >/root/fluxbox.log 2>&1 &

echo "🧩 Starting x11vnc (VNC server) on :5901"
x11vnc -display "$DISPLAY" \
       -rfbport 5901 \
       -rfbauth /root/.vnc/passwd \
       -forever -shared -localhost \
       -o /root/x11vnc.log \
       -bg >/dev/null 2>&1 || echo "⚠️ x11vnc background start returned non-zero"

echo "🌐 Starting noVNC on http://localhost:6080 -> vnc localhost:5901"
nohup /opt/novnc/utils/novnc_proxy --vnc localhost:5901 --listen 6080 \
  >/root/novnc.log 2>&1 &

mkdir -p /run/dbus
if [ ! -s /etc/machine-id ]; then
  dbus-uuidgen > /etc/machine-id
fi
[ -e /var/lib/dbus/machine-id ] || ln -sf /etc/machine-id /var/lib/dbus/machine-id
dbus-daemon --system --fork >/dev/null 2>&1 || true

export XAUTHORITY=/root/.Xauthority
xhost +local:root >/dev/null 2>&1 || true

CHROME_BIN="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser || true)"
echo "🧭 Chrome binary is: ${CHROME_BIN:-<none>}"
echo "📂 Chrome profile dir: $USER_DATA_DIR"
mkdir -p "$USER_DATA_DIR"
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
  echo "❌ Chrome binary not found"
fi

echo "🤖 Starting agent (python -m agent.main)"
python3 -m agent.main >/root/agent.log 2>&1 &
disown || true

echo "🛡️  Keeping container alive (tail -f /dev/null)"
tail -f /dev/null
'@ | Set-Content -Path .\startup_xvfb.sh -Encoding UTF8
