# Use a lightweight Python image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    build-essential \
    wget \
    unzip \
    curl \
    file \
    && rm -rf /var/lib/apt/lists/*

# Set required environment variables for GDAL compatibility
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Copy Flask folder contents into container
COPY flask/ .

# Install Python dependencies with setuptools pinned to avoid warnings
RUN pip install --upgrade pip "setuptools<81" wheel
RUN pip install -r requirements.txt

# Create WhiteboxTools directories
RUN mkdir -p /opt/whitebox_tools && \
    mkdir -p /usr/local/lib/python3.12/site-packages/whitebox/WBT

# Download and install WhiteboxTools with better error handling
RUN cd /tmp && \
    echo "Downloading WhiteboxTools..." && \
    wget -O whitebox_tools.zip https://www.whiteboxgeo.com/WBT_Linux/WhiteboxTools_linux_amd64.zip && \
    echo "Download completed. File info:" && \
    file whitebox_tools.zip && \
    ls -la whitebox_tools.zip && \
    echo "Extracting..." && \
    unzip -v whitebox_tools.zip && \
    ls -la && \
    echo "Installing WhiteboxTools..." && \
    cp -r WhiteboxTools_linux_amd64/WBT/* /usr/local/lib/python3.12/site-packages/whitebox/WBT/ && \
    cp -r WhiteboxTools_linux_amd64/WBT/* /opt/whitebox_tools/ && \
    echo "Setting permissions..." && \
    chmod +x /usr/local/lib/python3.12/site-packages/whitebox/WBT/whitebox_tools && \
    chmod +x /opt/whitebox_tools/whitebox_tools && \
    echo "Creating directories..." && \
    mkdir -p /usr/local/lib/python3.12/site-packages/whitebox/WBT/img && \
    mkdir -p /opt/whitebox_tools/img && \
    echo "Verifying installation..." && \
    ls -la /usr/local/lib/python3.12/site-packages/whitebox/WBT/ && \
    ls -la /opt/whitebox_tools/ && \
    file /usr/local/lib/python3.12/site-packages/whitebox/WBT/whitebox_tools && \
    echo "Cleaning up..." && \
    rm -rf /tmp/whitebox_tools.zip /tmp/WhiteboxTools_linux_amd64

# Create user directory structure for WhiteboxTools
RUN mkdir -p /root/.local/share/whitebox_tools && \
    ln -sf /usr/local/lib/python3.12/site-packages/whitebox/WBT /root/.local/share/whitebox_tools/WBT

# Set WhiteboxTools environment variables
ENV WBT_PATH=/usr/local/lib/python3.12/site-packages/whitebox/WBT/whitebox_tools
ENV PATH="${PATH}:/usr/local/lib/python3.12/site-packages/whitebox/WBT"

# Copy test script
COPY test_whitebox.py /app/test_whitebox.py

# Test WhiteboxTools installation with detailed output
RUN echo "Testing WhiteboxTools installation..." && \
    python test_whitebox.py && \
    echo "WhiteboxTools test completed successfully!"

# Alternative test using the whitebox module directly
RUN python -c "\
import whitebox; \
import os; \
print('=== WhiteboxTools Test ==='); \
wbt = whitebox.WhiteboxTools(); \
print(f'Version: {wbt.version()}'); \
print(f'Executable path: {wbt.exe_path}'); \
print(f'Executable exists: {os.path.exists(wbt.exe_path) if wbt.exe_path else False}'); \
print(f'Executable is executable: {os.access(wbt.exe_path, os.X_OK) if wbt.exe_path else False}'); \
print(f'Working directory: {wbt.work_dir}'); \
print(f'Available tools: {len(wbt.list_tools())}'); \
print('WhiteboxTools is ready!'); \
"

# Create a simple test endpoint script for runtime testing
RUN echo '#!/usr/bin/env python3\n\
import sys\n\
sys.path.append("/app")\n\
from app import app\n\
import requests\n\
import time\n\
import threading\n\
\ndef test_server():\n\
    time.sleep(2)\n\
    try:\n\
        response = requests.get("http://localhost:5000/test-whitebox")\n\
        print("=== WhiteboxTools Runtime Test ===")\n\
        print(f"Status Code: {response.status_code}")\n\
        print(f"Response: {response.json()}")\n\
        if response.status_code == 200:\n\
            print("✓ WhiteboxTools is working in runtime!")\n\
        else:\n\
            print("✗ WhiteboxTools test failed in runtime!")\n\
    except Exception as e:\n\
        print(f"✗ Runtime test error: {e}")\n\
\n\
if __name__ == "__main__":\n\
    test_thread = threading.Thread(target=test_server)\n\
    test_thread.daemon = True\n\
    test_thread.start()\n\
    app.run(host="0.0.0.0", port=5000, debug=False)\n' \
> /app/test_runtime.py && chmod +x /app/test_runtime.py

# Expose port 5000
EXPOSE 5000

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/test-dependencies || exit 1

# Start Flask app
CMD ["python", "app.py"]
