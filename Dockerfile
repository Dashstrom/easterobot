# Install uv
FROM python:3.12-slim

# Metadata for clarity and documentation
LABEL maintainer="your_email@example.com"
LABEL description="Docker image for easterobot using uv for dependency management"

# Add the UV binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Add non-root user
RUN useradd --create-home easterobot

# Create directory
RUN mkdir /data

# Make it read-only
RUN chown easterobot:easterobot /data

# Use non-root user for security
USER easterobot

# Change the working directory to the `src` directory
WORKDIR /src

# Copy only project definition files (improves caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project

# Copy the project into the image
COPY . .

# Sync the project
RUN uv sync --frozen

# Make script executable
RUN chmod /src/entrypoint.sh

# Default command (use exec form for signal handling)
CMD ["/src/entrypoint.sh"]
