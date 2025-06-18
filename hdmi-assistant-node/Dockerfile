# File: Dockerfile
# Description: Dockerfile for HDMI Assistant Node.
# Author: Chuffnugget

FROM python:3.11-slim

# Install ddcutil + i2c-tools and build tools
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ddcutil \
      i2c-tools \
      libusb-1.0-0 \
      build-essential \
      python3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run the HDMI Assistant Node process
ENTRYPOINT ["python3", "app/hdmi_assistant_node.py"]    # ← updated script name
