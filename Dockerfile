FROM python:3.10-slim

# ------------------ System Deps ------------------
RUN apt-get update && apt-get install -y \
    curl gnupg git python3-tk python3-dev \
    libx11-6 libxext6 libsm6 libxrender1 libgl1 \
    libglib2.0-0 libgtk2.0-dev libnss3 libasound2 \
    libxcomposite1 libxdamage1 x11-utils x11-xserver-utils \
    x11vnc xvfb fluxbox scrot unclutter xclip wget fonts-dejavu \
    novnc websockify tigervnc-standalone-server xterm \
    # --- extra bits Chrome needs in an X/VNC container ---
    dbus dbus-x11 xauth libgbm1 libxkbcommon0 libxrandr2 libxfixes3 libxshmfence1 libdrm2 \
 && (apt-get install -y libgtk-3-0 || apt-get install -y libgtk-3-0t64) \
 && apt-get clean && rm -rf /var/lib/apt/lists/*



# ------------------ Google Chrome ------------------
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# ------------------ Env ------------------
ENV DISPLAY=:1 \
    RESOLUTION=2560x1440 \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface/transformers \
    TOKENIZERS_PARALLELISM=false \
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:256,expandable_segments:true

# ------------------ Python deps ------------------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    # CUDA 12.1 wheels for PyTorch (GPU). Compose must run with --gpus all
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu121 \
        torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0

# ------------------ App ------------------
COPY . .
COPY startup.sh /app/startup.sh
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/startup.sh /app/entrypoint.sh

EXPOSE 5901 6080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gui"]
