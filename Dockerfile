FROM python:3.9-slim

# First step: Set up multiarch support and install Wine
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y \
    build-essential \
    gcc \
    g++ \
    ccache \
    patchelf \
    zip \
    unzip \
    file \
    curl \
    wget \
    lsb-release \
    dos2unix \
    apt-utils \
    xvfb \
    mingw-w64 \
    python3-dev \
    sudo \
    wine \
    wine64 \
    wine32:i386 \
    libwine:i386 \
    cabextract

# Create user with proper permissions
RUN useradd -m -u 1000 user
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Verify Wine installation
RUN which wine && wine --version || echo "Wine is not installed properly"

# Suppress Wine debug output and disable Gecko/Mono installation prompts
ENV WINEDEBUG=-all \
    WINEDLLOVERRIDES="mscoree=d;mshtml=d" \
    DISPLAY=:99 \
    WINEPREFIX=/home/user/.wine \
    WINEARCH=win64

# Create directories for user code
WORKDIR /app
RUN mkdir -p /app/user_code /app/compiled_output
RUN touch /app/icon.ico
COPY *.py /app/
COPY *.sh /app/
RUN chmod +x /app/*.sh
RUN chown -R user:user /app

# Create X11 directory with proper permissions
RUN mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix

# Allow user to use sudo for apt installations
RUN echo "user ALL=(ALL) NOPASSWD: /usr/bin/apt-get" >> /etc/sudoers

# Download Python installer as root for better reliability
RUN wget -q -O /tmp/python-3.9.13-amd64.exe https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe && \
    chmod 644 /tmp/python-3.9.13-amd64.exe && \
    chown user:user /tmp/python-3.9.13-amd64.exe

# Switch to user
USER user

# Initialize Wine prefix (run in background so it doesn't hang)
RUN (Xvfb :99 -screen 0 1024x768x16 & \
    sleep 2 && \
    DISPLAY=:99 WINEPREFIX=/home/user/.wine WINEDEBUG=-all wine wineboot || true) && \
    echo "Wine prefix initialized"

WORKDIR /app

# Run the streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]