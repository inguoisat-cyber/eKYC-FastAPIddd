# eKYC — xác minh danh tính CCCD + khuôn mặt

Người dùng chụp 2 mặt CCCD → hệ thống đọc **mã QR** (số CCCD, họ tên, ngày sinh, địa chỉ), cắt chân dung trên thẻ → người dùng làm thử thách liveness bằng camera → so khớp selfie với ảnh thẻ (InsightFace/ArcFace).

## Chạy

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .                                        # thêm ".[ocr]" nếu cần OCR dự phòng, ".[dev]" để chạy test
sudo apt install libzbar0                               # Linux (không bắt buộc: thiếu thì dùng OpenCV đọc QR)
python download_models.py                               # tải trước model (~280MB), tuỳ chọn
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mở `http://localhost:8000`. Camera trình duyệt chỉ chạy trên `localhost` hoặc **HTTPS**; thiết bị khác trong LAN cần đặt sau reverse proxy HTTPS.
Docker: `docker build -t ekyc . && docker run -p 8000:8000 -v ekyc-data:/app/data ekyc`.

Cấu hình (biến môi trường hoặc file `.env`, xem `.env.example`): ngưỡng khớp mặt, độ nét tối thiểu, số lần thử, `FACE_MODEL`, `OCR_FALLBACK`…

## Luồng xử lý & API

| Bước | Request | Server làm gì |
|---|---|---|
| Đồng ý | `POST /api/kyc/session {consent:true}` | Tạo phiên (TTL 30 phút) |
| Chụp thẻ | `POST /api/kyc/document/{front\|back}?session_id=` | Lưu ảnh (mã hoá Fernet) |
| Đọc thẻ | `POST /api/kyc/document/process?session_id=` | Trích embedding mặt trên thẻ → đọc QR (OCR chỉ khi bật và QR hỏng) |
| Liveness | `POST /api/kyc/liveness/challenge?session_id=` | Chọn ngẫu nhiên: nhìn thẳng / nghiêng trái / nghiêng phải |
| Xác thực | `POST /api/kyc/liveness/verify` (form: `session_id`, `image`) | Mỗi khung: detect@320 → chất lượng vùng mặt → góc mặt; **chỉ khi đạt góc** mới tính embedding và so khớp |

Swagger: `/docs`. Kết quả cuối: `ACCEPTED` khi `cosine ≥ MATCH_THRESHOLD`, ngược lại `REJECTED`; thiếu QR chỉ là ghi chú tham khảo (+10 điểm rủi ro), không chặn.

## Cấu trúc

```
backend/app/  main.py (khởi động, static) · api.py (toàn bộ endpoint) · face.py (InsightFace)
              docs.py (QR + OCR dự phòng) · db.py · storage.py (mã hoá file) · config.py
frontend/     index.html · app.js (không dependency)
tests/        E2E bằng model thật:  pip install -e ".[dev]" && pytest
```

## Lưu ý vận hành

- **Đây không phải chống giả mạo (anti-spoofing) thực thụ.** Liveness chỉ kiểm tra góc mặt trên 1 khung hình; ảnh/video phát lại có thể qua. Dùng cho đồ án/demo; sản phẩm thật cần model PAD chuyên dụng.
- `data/fernet.key` (hoặc `ENCRYPTION_KEY`) là chìa giải mã toàn bộ ảnh: backup riêng, không commit.
- Phiên dở dang quá hạn được xoá tự động (kèm ảnh). Phiên thành công (`DECIDED`) được giữ lại, hãy đặt chính sách lưu trữ/xoá theo quy định của bạn.
- SQLite chạy ổn cho một tiến trình; nhiều máy chủ thì chuyển sang PostgreSQL.
