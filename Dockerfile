# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables to avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install any needed packages specified in requirements.txt
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc wget ffmpeg htop
    # rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# # Install zsh and oh-my-zsh
RUN apt-get install -y zsh
# Uses "git", "ssh-agent" and "history-substring-search" bundled plugins
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v1.2.1/zsh-in-docker.sh)" -- \
    -p git -p 'history-substring-search' \
    -a 'bindkey "\$terminfo[kcuu1]" history-substring-search-up' \
    -a 'bindkey "\$terminfo[kcud1]" history-substring-search-down'

COPY ./telegram_auto_poster/req.txt requirements

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements

# start bash
CMD ["zsh"]
