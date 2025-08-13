FROM python:3.10-slim

# ------------------ Install System Dependencies ------------------
RUN apt-get update && apt-get install -y \
    curl gnupg git python3-tk python3-dev \
    libx11-6 libxext6 libsm6 libxrender1 libgl1 \
    libglib2.0-0 libgtk2.0-dev libnss3 libasound2 \
    libxcomposite1 libxdamage1 x11-utils x11-xserver-utils \
    x11vnc xvfb fluxbox scrot unclutter xclip wget fonts-dejavu \
    novnc websockify tigervnc-standalone-server xterm \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ------------------ Install Google Chrome ------------------
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# ------------------ Environment Variables ------------------
ENV DISPLAY=:1
ENV RESOLUTION=2560x1440

# ------------------ Create noVNC Link ------------------
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc && \
    ln -s /opt/novnc/vnc.html /opt/novnc/index.html

# ------------------ Working Directory & App ------------------
WORKDIR /app
COPY requirements.txt . 
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# ------------------ Startup Script ------------------
COPY startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# ------------------ Ports for VNC and noVNC ------------------
EXPOSE 5901 6080

# ------------------ Start Everything ------------------
ENTRYPOINT ["/app/startup.sh"]

