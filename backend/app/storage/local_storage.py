import os

class LocalStorage:
    def __init__(self, upload_dir: str = "uploads"):
        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    def save_file(self, file_bytes: bytes, filename: str) -> str:
        """Lưu bytes vào file local và trả về đường dẫn"""
        import uuid
        if filename.startswith("."):
            filename = f"{uuid.uuid4()}{filename}"
        file_path = os.path.join(self.upload_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        return file_path

    def read_file(self, file_path_or_name: str) -> bytes:
        """Đọc nội dung file dưới dạng bytes (khắc phục lỗi thiếu read_file)"""
        # Nếu chỉ truyền tên file, tự động nối với thư mục upload_dir
        if not os.path.isabs(file_path_or_name) and not file_path_or_name.startswith(self.upload_dir):
            path = os.path.join(self.upload_dir, file_path_or_name)
        else:
            path = file_path_or_name

        if not os.path.exists(path):
            raise FileNotFoundError(f"Không tìm thấy file tại đường dẫn: {path}")

        with open(path, "rb") as f:
            return f.read()

# Khởi tạo instance dùng chung
storage_backend = LocalStorage()