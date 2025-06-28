# Use a lightweight Linux image with Python 3.12 installed
FROM python:3.12-slim

# Set the default working directory inside the container to /app
WORKDIR /app

# Install system packages needed by WhiteboxTools AND for building some Python packages
# - gdal-bin, libgdal-dev: for working with raster data
# - build-essential: tools like gcc/g++ needed to compile packages like numpy
# - python3-dev: Python headers required for native extensions
# - wget, unzip: for file handling
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    build-essential \
    python3-dev \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install setuptools + wheel early to prevent build errors for some packages
RUN pip install --upgrade pip setuptools wheel

# Copy the Flask application code and requirements.txt file into the container
COPY app.py requirements.txt /app/

# Copy the WhiteboxTools Linux folder to /whitebox/WBT inside the container
COPY WBT /whitebox/WBT

# Install Python packages listed in requirements.txt without using pip's cache
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable so your app knows where WhiteboxTools is located
ENV WHITEBOX_DIR=/whitebox/WBT

# Tell Docker how to run your Flask app when the container starts
CMD ["python", "app.py"]
