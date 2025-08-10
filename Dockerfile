# Install uv
FROM python:3.13-slim-bookworm

# Metadata for clarity and documentation
LABEL maintainer="dashstrom.pro@gmail.com"
LABEL description="Docker image for easterobot, a discord bot for easter events"

# The installer requires curl (and certificates) to download the release archive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    libjpeg-dev zlib1g-dev libtiff-dev libfreetype6-dev \
    liblcms2-dev libwebp-dev tcl-dev tk-dev \
    libopenjp2-7-dev libimagequant-dev \
    libxcb1-dev libavif-dev \
    libharfbuzz-dev libfribidi-dev libraqm-dev \
    curl

# INstall UV
RUN curl -LsSf https://astral.sh/uv/0.8.7/install.sh | env UV_INSTALL_DIR="/bin" sh

# Add non-root user
RUN useradd --create-home easterobot

# Create directory
RUN mkdir /data && chown easterobot:easterobot /data

# Change the working directory to the `src` directory
WORKDIR /src

# Copy only project definition files (improves caching)
COPY pyproject.toml ./

# Install dependencies
RUN uv sync --no-install-project

# Copy the project into the image
COPY . .

# Fix permissions
RUN find /src -type d -exec chmod 755 {} \; \
 && find /src -type f -exec chmod 644 {} \; \
 && chmod +x /src/entrypoint.sh

# Sync the project
RUN uv sync --frozen

# Use non-root user for security
USER easterobot

# Default command (use exec form for signal handling)
CMD ["/src/entrypoint.sh"]
