# 🛡️ Hệ Thống eKYC (Xác Minh Danh Tính Điện Tử)

Hệ thống xác minh danh tính điện tử eKYC tự động, tối ưu hóa để triển khai trên môi trường máy chủ cục bộ (On-premise / Local). Dự án áp dụng trí tuệ nhân tạo (Computer Vision & Deep Learning) tập trung chuyên sâu vào **nhận diện khuôn mặt (Face Recognition)** và **kiểm tra người thật (Liveness Detection)**, đồng thời trích xuất thông tin Căn cước công dân (CCCD) ở mức độ linh hoạt, giảm thiểu tỷ lệ từ chối sai.

---

## 📌 Điểm Nổi Bật Của Hệ Thống

1. **Nhận diện khuôn mặt chuyên sâu (InsightFace - ArcFace)**:
   - **Tiền xử lý ảnh thích ứng (Image Preprocessing)**: Cân bằng ánh sáng tự động (CLAHE) và khử nhiễu (Denoising), giúp phát hiện khuôn mặt sắc nét ngay cả khi ảnh thẻ CCCD mờ hoặc bị lóa sáng.
   - **Multi-scale Detection**: Tự động tinh chỉnh tỉ lệ (1.5x - 2.0x) để bắt trọn khuôn mặt nhỏ trên thẻ căn cước chụp từ xa.
   - **Đối sánh khuôn mặt kép (Dual-metric Verification)**: Kết hợp cả **Cosine Similarity** và **Euclidean Distance** để đảm bảo độ chính xác cao nhất khi so sánh ảnh selfie và ảnh trên giấy tờ.

2. **Kiểm tra thực thể sống (Liveness Detection & Anti-Spoofing)**:
   - Thử thách ngẫu nhiên theo thời gian thực (nhìn thẳng, quay trái, quay phải, ngước lên) dựa trên tính toán góc xoay khuôn mặt 3D (**Pose Estimation: Yaw, Pitch, Roll**).
   - Kiểm tra chất lượng khuôn mặt tức thì: Đo độ mờ (Laplacian blur score), độ sáng và độ tương phản nhằm loại bỏ ảnh chụp lại từ màn hình hoặc ảnh in kém chất lượng.

3. **Trích xuất CCCD đại khái & linh hoạt (Relaxed OCR)**:
   - Sử dụng EasyOCR / Heuristic Regex để trích xuất số CCCD, họ tên, ngày sinh.
   - Cơ chế nới lỏng: Không chặn luồng nếu giấy tờ thiếu từ khóa chuẩn hoặc mờ nhẹ; hệ thống chuyển trọng số quyết định sang độ khớp của khuôn mặt.

4. **Động cơ phân tích rủi ro thông minh (Decision Engine)**:
   - Đánh giá gian lận đa tầng: Ưu tiên 80% - 90% kết quả từ Face Match & Liveness, chỉ coi OCR/QR là yếu tố tham khảo phụ, giúp tối ưu tỷ lệ hoàn thành luồng eKYC (Pass rate).

---

## 🏗️ Kiến Trúc Hệ Thống

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/), Python 3.12+
- **AI Engines**:
  - `FaceEngine`: InsightFace (`buffalo_l`), OpenCV, ONNX Runtime
  - `OCREngine`: EasyOCR (Việt - Anh)
  - `QRDetector`: PyZBar / OpenCV QRCodeDetector
  - `DecisionEngine`: Thuật toán tính điểm rủi ro và phân loại kết quả (ACCEPTED / MANUAL_REVIEW / REJECTED)
- **Frontend**: Single Page Web App (HTML5, Modern CSS, Vanilla JS, WebRTC MediaStream API)
- **Cơ sở dữ liệu**: SQLite (SQLAlchemy ORM)
- **Lưu trữ**: Local File Storage có mã hóa phân cấp

---

## 📂 Cấu Trúc Thư Mục

```text
├── backend/
│   ├── app/
│   │   ├── ai/               # Các mô hình & engine AI (Face, OCR, QR, Decision)
│   │   ├── api/routers/      # API endpoints (Session, Document, OCR, QR, Liveness)
│   │   ├── core/             # Cấu hình hệ thống (Settings, Config)
│   │   ├── db/               # Khởi tạo Database & Schema Models
│   │   ├── schemas/          # Pydantic Schemas
│   │   ├── storage/          # Module quản lý lưu trữ tệp tin
│   │   └── main.py           # Entry point của ứng dụng FastAPI
│   └── storage/              # Thư mục lưu trữ ảnh tải lên (được tạo tự động)
├── frontend/
│   ├── index.html            # Giao diện người dùng
│   └── app.js                # Luồng điều khiển eKYC (Camera, Upload, Liveness loop)
├── models/                   # Trọng số các mô hình AI (InsightFace, EasyOCR)
├── .env.example              # Mẫu biến môi trường
├── download_models.py        # Kịch bản tải trước trọng số mô hình AI
├── pyproject.toml            # Khai báo dependencies dự án
└── README.md                 # Tài liệu hướng dẫn
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Hệ Thống

### 1. Yêu cầu hệ thống
- Hệ điều hành: Windows 10/11, Ubuntu 20.04+, hoặc macOS
- Python: `3.12` trở lên
- Camera / Webcam hoạt động tốt để thực hiện Liveness

### 2. Thiết lập môi trường ảo
Mở terminal tại thư mục gốc của dự án:

```bash
# Tạo môi trường ảo
python -m venv venv

# Kích hoạt môi trường:
# - Trên Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# - Trên Windows (CMD):
.\venv\Scripts\activate.bat
# - Trên Linux / macOS:
source venv/bin/activate
```

### 3. Cài đặt các thư viện phụ thuộc
```bash
pip install --upgrade pip
pip install -e .
```

### 4. Tải trước mô hình AI (Khuyên dùng)
Để tránh bị chậm trong lần chạy đầu tiên:
```bash
python download_models.py
```

### 5. Cấu hình biến môi trường
Tạo file `.env` từ file mẫu:
```bash
cp .env.example .env
```

### 6. Khởi chạy ứng dụng
Chạy server FastAPI:
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🖥️ Trải Nghiệm Sử Dụng

1. Mở trình duyệt web và truy cập: **`http://localhost:8000`**
2. **Bước 1**: Đồng ý điều khoản thu thập dữ liệu xác thực danh tính.
3. **Bước 2**: Chụp mặt trước và mặt sau thẻ Căn cước công dân (CCCD).
4. **Bước 3**: Hệ thống tự động trích xuất thông tin giấy tờ và cắt ảnh chân dung.
5. **Bước 4**: Bật camera selfie, làm theo thử thách Liveness (xoay mặt hoặc nhìn thẳng) trong khung Oval.
6. **Bước 5**: Nhận kết quả xác thực eKYC ngay lập tức (Tỷ lệ khớp khuôn mặt, Điểm rủi ro, Trạng thái phê duyệt).

---

## 📑 Tài Liệu API (Swagger UI)
Khi server đang chạy, bạn có thể kiểm tra và test nhanh toàn bộ API tại:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
