
# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
# 🔴 REQUIRED for torch==2.1.2+cpu
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy the entire project
COPY . .

# Verify ChromaDB files are present
# RUN echo "=== Verifying ChromaDB Installation ===" && \
#     ls -lah /app/chroma_db/ && \
#     if [ -f "/app/chroma_db/chroma.sqlite3" ]; then \
#         echo "✅ ChromaDB database found ($(du -h /app/chroma_db/chroma.sqlite3 | cut -f1))"; \
#         echo "✅ Total ChromaDB size: $(du -sh /app/chroma_db | cut -f1)"; \
#     else \
#         echo "❌ ERROR: chroma.sqlite3 NOT found!"; \
#         echo "Check that .dockerignore doesn't exclude *.sqlite3"; \
#         exit 1; \
#     fi
# Verify Python dependencies
RUN echo "=== Verifying Installation ===" && \
    python -c "import psycopg2; print('✅ psycopg2 installed')" && \
    python -c "import sentence_transformers; print('✅ sentence-transformers installed')" && \
    echo "✅ Dependencies verified"

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
