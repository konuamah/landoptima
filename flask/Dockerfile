# Use a lightweight Linux image with Python 3.12 installed
FROM python:3.12-slim

# Set the default working directory inside the container to /app
WORKDIR /app

# Install system packages needed by WhiteboxTools AND for building some Python packages
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    build-essential \
    python3-dev \
    python3-pip \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install setuptools + wheel early to prevent build errors for some packages
RUN pip install --upgrade pip setuptools wheel

# Install Python packages - use binary wheels where possible
# First install rasterio from binary to avoid build issues
RUN pip install --only-binary=:all: rasterio numpy

# Install remaining packages
RUN pip install --no-cache-dir Flask==2.3.2 Flask-CORS==4.0.0 whitebox==2.2.0 requests==2.31.0 anthropic python-dotenv==1.0.0 pathlib datetime psycopg2-binary pandas

# Copy the Flask application code and requirements.txt file into the container
COPY app.py requirements.txt /app/
COPY optimization /app/optimization
COPY db /app/db

# Copy the WhiteboxTools Linux folder to /whitebox/WBT inside the container
COPY WBT /whitebox/WBT
RUN chmod +x /whitebox/WBT/whitebox_tools

# Set environment variable so your app knows where WhiteboxTools is located
ENV WHITEBOX_DIR=/whitebox/WBT

# Tell Docker how to run your Flask app when the container starts
CMD ["python", "app.py"]
