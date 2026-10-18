import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="ekyc_test_"))  # phải đặt trước khi import app
