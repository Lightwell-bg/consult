FROM python:3.11-slim

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and prompts
COPY src/ ./src/
COPY prompts/ ./prompts/

# Runtime dirs are mounted as volumes — create placeholders
RUN mkdir -p data credentials

CMD ["python", "-m", "src.main"]
