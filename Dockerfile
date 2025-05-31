# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install any needed system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    wget \
    ffmpeg \
    htop \
    git \
    curl

# Set the working directory in the container
WORKDIR /app

# Install zsh and oh-my-zsh (optional, for better developer experience)
RUN apt-get install -y zsh
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v1.2.1/zsh-in-docker.sh)" -- \
    -p git -p 'history-substring-search' \
    -a 'bindkey "\$terminfo[kcuu1]" history-substring-search-up' \
    -a 'bindkey "\$terminfo[kcud1]" history-substring-search-down'

# Copy requirements file
COPY ./requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/photos /app/videos /app/tmp

# Make the startup script executable
COPY ./run_bg.sh /app/run_bg.sh
RUN chmod +x /app/run_bg.sh

# Default command uses zsh for interactive sessions
CMD ["zsh"]
