"""E2E với model thật. Ảnh thẻ được tạo giả: chân dung (skimage) + mã QR đúng định dạng CCCD."""
import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
import qrcode
from fastapi.testclient import TestClient
from skimage import data

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import api  # noqa: E402
from app.main import app  # noqa: E402

QR = "012345678901|123456789|NGUYEN VAN A|01011990|Nam|Ha Noi|01012021"


def jpg(img, q=90):
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()


def card(portrait, qr=None):
    c = np.full((800, 1280, 3), 235, np.uint8)
    cv2.putText(c, "CAN CUOC CONG DAN", (420, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (30, 30, 160), 3)
    c[220:220 + 360, 60:60 + 360] = cv2.resize(portrait, (360, 360))
    if qr:
        q = np.array(qrcode.make(qr, box_size=6, border=2).convert("RGB"))[:, :, ::-1]
        c[500:500 + q.shape[0], 900:900 + q.shape[1]] = q
    return c


ASTRO = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
OTHER = cv2.cvtColor(cv2.cvtColor(data.camera(), cv2.COLOR_GRAY2RGB), cv2.COLOR_RGB2BGR)[:, :, :]
SELFIE = cv2.resize(ASTRO[35:204, 112:337], (480, 360), interpolation=cv2.INTER_CUBIC)  # mặt chiếm ~40% bề ngang như selfie thật


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def files(b):
    return {"file": ("x.jpg", io.BytesIO(b), "image/jpeg")}


def start(client, front, back):
    sid = client.post("/api/kyc/session", json={"consent": True}).json()["id"]
    assert client.post(f"/api/kyc/document/front?session_id={sid}", files=files(front)).status_code == 200
    assert client.post(f"/api/kyc/document/back?session_id={sid}", files=files(back)).status_code == 200
    return sid


def verify(client, sid, selfie=SELFIE):
    return client.post("/api/kyc/liveness/verify", data={"session_id": sid}, files={"image": ("s.jpg", io.BytesIO(jpg(selfie)), "image/jpeg")})


def test_happy_path(client, monkeypatch):
    monkeypatch.setattr(api.random, "choice", lambda _: "look_straight")
    sid = start(client, jpg(card(ASTRO, QR)), jpg(np.full((800, 1280, 3), 230, np.uint8)))
    r = client.post(f"/api/kyc/document/process?session_id={sid}")
    assert r.status_code == 200, r.text
    assert r.json()["info"]["id_number"] == "012345678901" and r.json()["info"]["dob"] == "01/01/1990"
    assert client.post(f"/api/kyc/liveness/challenge?session_id={sid}").json()["type"] == "look_straight"
    r = verify(client, sid).json()
    assert r["done"] and r["success"] and r["similarity"] > 0.5, r
    assert verify(client, sid).status_code == 409  # DECIDED là trạng thái cuối


def test_qr_on_back_and_no_qr(client):
    sid = start(client, jpg(card(ASTRO)), jpg(card(OTHER, QR)))
    assert client.post(f"/api/kyc/document/process?session_id={sid}").json()["info"]["full_name"] == "NGUYEN VAN A"
    sid = start(client, jpg(card(ASTRO)), jpg(card(OTHER)))
    assert client.post(f"/api/kyc/document/process?session_id={sid}").json()["info"] is None  # vẫn cho đi tiếp


def test_no_face_on_card(client):
    sid = start(client, jpg(np.full((800, 1280, 3), 200, np.uint8)), jpg(card(ASTRO)))
    r = client.post(f"/api/kyc/document/process?session_id={sid}")
    assert r.status_code == 422 and "khuôn mặt" in r.json()["detail"]


def test_wrong_person_rejected_and_attempt_limit(client, monkeypatch):
    monkeypatch.setattr(api.random, "choice", lambda _: "look_straight")
    sid = start(client, jpg(card(OTHER, QR)), jpg(card(OTHER)))
    assert client.post(f"/api/kyc/document/process?session_id={sid}").status_code == 200
    for _ in range(5):
        client.post(f"/api/kyc/liveness/challenge?session_id={sid}")
        r = verify(client, sid).json()
        assert r["done"] and not r["success"] and r["decision"]["final_status"] == "REJECTED", r
    assert client.post(f"/api/kyc/liveness/challenge?session_id={sid}").status_code == 429


def test_guards(client):
    sid = client.post("/api/kyc/session", json={"consent": True}).json()["id"]
    assert client.post("/api/kyc/session", json={"consent": False}).status_code == 400
    assert client.post(f"/api/kyc/document/back?session_id={sid}", files=files(b"\xff\xd8x")).status_code == 409
    assert client.post(f"/api/kyc/document/front?session_id={sid}", files=files(b"GIF89a")).status_code == 415
    assert client.post(f"/api/kyc/document/front?session_id={sid}", files=files(b"\xff\xd8" + b"0" * 6_000_000)).status_code == 413
    assert client.post(f"/api/kyc/liveness/challenge?session_id={sid}").status_code == 409
    assert client.post("/api/kyc/document/process?session_id=nope").status_code == 404


def test_hints_and_expiry(client, monkeypatch):
    sid = start(client, jpg(card(ASTRO, QR)), jpg(card(OTHER)))
    client.post(f"/api/kyc/document/process?session_id={sid}")
    monkeypatch.setattr(api.random, "choice", lambda _: "turn_left_gentle")
    client.post(f"/api/kyc/liveness/challenge?session_id={sid}")
    assert "TRÁI" in verify(client, sid).json()["message"]                              # mặt thẳng, yêu cầu quay trái
    assert "mờ" in verify(client, sid, cv2.GaussianBlur(SELFIE, (0, 0), 6)).json()["message"]
    assert "tối" in verify(client, sid, (SELFIE * 0.15).astype(np.uint8)).json()["message"]
    assert "oval" in verify(client, sid, np.full((360, 480, 3), 128, np.uint8)).json()["message"]  # không có mặt
    from app.db import SessionLocal, KYCSession, utcnow
    from datetime import timedelta
    with SessionLocal() as db:
        db.get(KYCSession, sid).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert verify(client, sid).status_code == 410


def test_parsers():
    from app import docs
    assert docs.parse_qr("hello world") is None and docs.parse_qr("abc|1|2|3|4|5") is None  # QR không phải CCCD
    assert docs.parse_qr(QR)["issue_date"] == "01/01/2021"
    lines = ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "CĂN CƯỚC CÔNG DÂN", "0I2 345 678 9O1", "Họ và tên / Full name:", "NGUYỄN VĂN A",
             "Ngày sinh / Date of birth: 01/01/1990", "Có giá trị đến: 01/01/2030"]
    o = docs.parse_ocr(lines)
    assert (o["id_number"], o["full_name"], o["dob"]) == ("012345678901", "NGUYỄN VĂN A", "01/01/1990")  # bản cũ lấy nhầm ngày hết hạn
    assert docs.parse_ocr(["Họ và tên", "Full name:", "TRẦN THỊ B"])["full_name"] == "TRẦN THỊ B"
    assert docs.parse_ocr(["blah"]) is None
    assert docs.parse_ocr(["CAN CUOC CONG DAN"]) is None
    qr_info = docs.parse_qr(QR)
    ocr_info = {"id_number": "012345678991", "full_name": "NGUYEN VAN A", "dob": "01/01/1990"}
    assert docs.compare_qr_ocr(qr_info, ocr_info)["valid"]  # tolerate one OCR digit error
    ocr_info["id_number"] = "999999999999"
    assert not docs.compare_qr_ocr(qr_info, ocr_info)["valid"]
