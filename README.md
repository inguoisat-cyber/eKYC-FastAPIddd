# Hệ thống eKYC

Đây là đồ án hệ thống xác minh danh tính điện tử (eKYC) chạy trên local.

## Kiến trúc
- Backend: FastAPI, Python 3.12+
- AI Models: PaddleOCR, OpenCV, ONNX Runtime (InsightFace)
- Frontend: HTML/CSS/JS thuần
- Database: SQLite

## Cài đặt (Local)

1. **Cài đặt Python 3.12+**
2. **Tạo virtual environment và kích hoạt:**
   ```bash
   cd ekyc
   python -m venv venv
   # Windows: venv\Scripts\activate
   # macOS/Linux: source venv/bin/activate
   ```
3. **Cài đặt thư viện:**
   ```bash
   pip install -e .
   ```
4. **Cấu hình biến môi trường:**
   Copy file `.env.example` thành `.env`
5. **Chạy server:**
   ```bash
   cd backend
   uvicorn app.main:app --reload
   ```
6. **Mở trình duyệt:** Truy cập http://localhost:8000
