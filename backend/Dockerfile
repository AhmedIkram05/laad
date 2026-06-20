# =============================================================================
# Stage 1: Builder — install Python dependencies
# =============================================================================
FROM python:3.10-slim AS builder

WORKDIR /app

# Install git (needed for some pip packages that fetch from VCS)
RUN apt-get update && apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest and install all packages
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2: Runtime — minimal production image
# =============================================================================
FROM python:3.10-slim

# Install curl (needed for ECS health checks)
RUN apt-get update && apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user with uid/gid 1000
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --create-home --shell /bin/bash appuser

# Copy installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy only the application source code (not the build layer)
COPY . ./backend/

# Ensure the working directory is owned by the non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
