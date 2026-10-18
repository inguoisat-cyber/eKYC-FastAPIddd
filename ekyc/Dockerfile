FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# libgl1/libglib2.0-0: OpenCV · libgomp1: ONNX Runtime · libzbar0: đọc QR (không cần build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 libzbar0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Thứ tự layer: dependency -> model -> code (đổi code không phải tải lại model/thư viện)
COPY pyproject.toml .
RUN pip install ".[ocr]"
COPY download_models.py .
RUN python download_models.py --ocr

COPY backend backend
COPY frontend frontend
RUN useradd -m app && mkdir -p data && chown app data
USER app
VOLUME /app/data
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health')"
# 1 worker + threadpool: ONNX Runtime đã đa luồng, thêm worker chỉ tốn RAM (mỗi worker nạp lại model)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
