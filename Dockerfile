FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /usr/src/app

# Install system dependencies needed for compiling certain C extensions
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install both Flask and the PostgreSQL driver securely
RUN pip install --no-cache-dir psycopg2-binary flask prometheus-client

# Copy the rest of our application code into the container
COPY . .

# (We leave standard CMD blank because docker-compose overrides it explicitly)