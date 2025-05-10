# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install any needed packages specified in requirements.txt
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

COPY ./telegram_auto_poster/req.txt requirements

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements

# start bash
CMD ["bash"]
