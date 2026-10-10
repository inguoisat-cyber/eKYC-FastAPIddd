FROM python:3.10-slim

WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết cho OpenCV, thư viện C++, thư viện xử lý ảnh
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements (nếu có) hoặc tạo môi trường từ pyproject.toml
# Ở đây ta giả sử copy toàn bộ source code (hoặc tạo file requirements.txt tạm)
COPY pyproject.toml ./

# Cài đặt pip, setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools

# Cài đặt các thư viện nặng (sử dụng phiên bản CPU để nhẹ image)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings sqlalchemy cryptography python-multipart easyocr insightface onnxruntime opencv-python

# Copy toàn bộ code frontend và backend vào container
# Cấu trúc: 
# /app/backend
# /app/frontend
COPY backend /app/backend
COPY frontend /app/frontend

# Chuyển working dir vào backend để chạy uvicorn
WORKDIR /app/backend

# Mở port 8000
EXPOSE 8000

# Khởi động server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
