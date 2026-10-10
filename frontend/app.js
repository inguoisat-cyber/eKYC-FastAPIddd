document.addEventListener('DOMContentLoaded', () => {
    const statusSpan = document.querySelector('.status');
    const appDiv = document.getElementById('app');
    
    let currentSessionId = null;

    async function initSession() {
        try {
            statusSpan.textContent = 'Đang khởi tạo phiên KYC...';
            const response = await fetch('/api/kyc/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            
            if (response.ok) {
                currentSessionId = data.id;
                statusSpan.textContent = `Session ID: ${currentSessionId}`;
                renderConsentStep();
            } else {
                statusSpan.textContent = `Lỗi: ${data.detail}`;
            }
        } catch (error) {
            statusSpan.textContent = `Lỗi kết nối: ${error.message}`;
        }
    }

    function renderConsentStep() {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step';
        stepDiv.innerHTML = `
            <h3>Bước: Đồng ý điều khoản</h3>
            <p>Hệ thống cần thu thập hình ảnh giấy tờ và khuôn mặt của bạn để xác minh. Bạn có đồng ý?</p>
            <button id="btn-consent">Đồng ý</button>
        `;
        appDiv.appendChild(stepDiv);

        document.getElementById('btn-consent').addEventListener('click', async () => {
            try {
                const res = await fetch(`/api/kyc/${currentSessionId}/consent`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ consent: true })
                });
                if (res.ok) {
                    document.getElementById('btn-consent').disabled = true;
                    stepDiv.innerHTML += `<p class="status">Đã đồng ý (CONSENTED)</p>`;
                    renderDocumentFrontStep();
                } else {
                    const data = await res.json();
                    alert(`Lỗi: ${data.detail}`);
                }
            } catch (error) {
                alert(`Lỗi: ${error.message}`);
            }
        });
    }

    function renderDocumentFrontStep() {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step';
        stepDiv.innerHTML = `
            <h3>Bước 1: Chụp mặt trước Giấy tờ</h3>
            <p>Vui lòng đưa mặt trước CCCD gắn chip hoặc thẻ Căn cước vào khung hình.</p>
            <div style="margin-bottom: 10px;">
                <video id="camera-preview" autoplay playsinline style="width: 100%; max-width: 400px; border: 1px solid #ccc;"></video>
            </div>
            <button id="btn-capture-front">Chụp ảnh</button>
            <button id="btn-retry-front" style="display: none; background-color: #f44336;">Chụp lại</button>
            <button id="btn-next-front" style="display: none; background-color: #4CAF50;">Tiếp tục</button>
            <p id="front-upload-status"></p>
        `;
        appDiv.appendChild(stepDiv);

        const video = document.getElementById('camera-preview');
        const btnCapture = document.getElementById('btn-capture-front');
        const btnRetry = document.getElementById('btn-retry-front');
        const btnNext = document.getElementById('btn-next-front');
        
        let localStream = null;

        // Khởi động camera
        function startCamera() {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
                .then(stream => { 
                    localStream = stream;
                    video.srcObject = stream; 
                    video.play();
                })
                .catch(err => {
                    document.getElementById('front-upload-status').textContent = `Lỗi Camera: ${err.message}`;
                });
        }
        
        startCamera();

        btnRetry.addEventListener('click', () => {
            btnRetry.style.display = 'none';
            btnNext.style.display = 'none';
            btnCapture.style.display = 'inline-block';
            btnCapture.disabled = false;
            document.getElementById('front-upload-status').textContent = '';
            startCamera();
        });

        btnNext.addEventListener('click', () => {
            if(localStream) localStream.getTracks().forEach(track => track.stop());
            renderDocumentBackStep();
        });

        btnCapture.addEventListener('click', () => {
            const MAX_WIDTH = 1280;
            let vw = video.videoWidth;
            let vh = video.videoHeight;
            if (vw > MAX_WIDTH) {
                vh = Math.floor(vh * (MAX_WIDTH / vw));
                vw = MAX_WIDTH;
            }
            const canvas = document.createElement('canvas');
            canvas.width = vw;
            canvas.height = vh;
            canvas.getContext('2d').drawImage(video, 0, 0, vw, vh);
            
            canvas.toBlob(async (blob) => {
                const formData = new FormData();
                formData.append('file', blob, 'front.jpg');
                
                try {
                    document.getElementById('front-upload-status').textContent = 'Đang tải lên...';
                    const res = await fetch(`/api/kyc/document/front?session_id=${currentSessionId}`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (res.ok) {
                        document.getElementById('front-upload-status').textContent = 'Đã lưu ảnh mặt trước.';
                        btnCapture.style.display = 'none';
                        btnRetry.style.display = 'inline-block';
                        btnNext.style.display = 'inline-block';
                        video.pause(); // Pause video to show captured frame
                    } else {
                        document.getElementById('front-upload-status').textContent = `Lỗi: ${data.detail}`;
                    }
                } catch(error) {
                    document.getElementById('front-upload-status').textContent = `Lỗi kết nối: ${error.message}`;
                }
            }, 'image/jpeg', 0.9);
        });
    }

    function renderDocumentBackStep() {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step';
        stepDiv.innerHTML = `
            <h3>Bước 2: Chụp mặt sau Giấy tờ</h3>
            <p>Vui lòng lật thẻ và đưa mặt sau CCCD/Căn cước vào khung hình.</p>
            <div style="margin-bottom: 10px;">
                <video id="camera-preview-back" autoplay playsinline style="width: 100%; max-width: 400px; border: 1px solid #ccc;"></video>
            </div>
            <button id="btn-capture-back">Chụp mặt sau</button>
            <button id="btn-retry-back" style="display: none; background-color: #f44336;">Chụp lại</button>
            <button id="btn-next-back" style="display: none; background-color: #4CAF50;">Tiếp tục (OCR)</button>
            <p id="back-upload-status"></p>
        `;
        appDiv.appendChild(stepDiv);

        const video = document.getElementById('camera-preview-back');
        const btnCapture = document.getElementById('btn-capture-back');
        const btnRetry = document.getElementById('btn-retry-back');
        const btnNext = document.getElementById('btn-next-back');
        
        let localStream = null;

        function startCamera() {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
                .then(stream => { 
                    localStream = stream;
                    video.srcObject = stream; 
                    video.play();
                })
                .catch(err => {
                    document.getElementById('back-upload-status').textContent = `Lỗi Camera: ${err.message}`;
                });
        }
        
        startCamera();

        btnRetry.addEventListener('click', () => {
            btnRetry.style.display = 'none';
            btnNext.style.display = 'none';
            btnCapture.style.display = 'inline-block';
            btnCapture.disabled = false;
            document.getElementById('back-upload-status').textContent = '';
            startCamera();
        });

        btnCapture.addEventListener('click', () => {
            const MAX_WIDTH = 1280;
            let vw = video.videoWidth;
            let vh = video.videoHeight;
            if (vw > MAX_WIDTH) {
                vh = Math.floor(vh * (MAX_WIDTH / vw));
                vw = MAX_WIDTH;
            }
            const canvas = document.createElement('canvas');
            canvas.width = vw;
            canvas.height = vh;
            canvas.getContext('2d').drawImage(video, 0, 0, vw, vh);
            
            canvas.toBlob(async (blob) => {
                const formData = new FormData();
                formData.append('file', blob, 'back.jpg');
                
                try {
                    document.getElementById('back-upload-status').textContent = 'Đang tải lên...';
                    const res = await fetch(`/api/kyc/document/back?session_id=${currentSessionId}`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (res.ok) {
                        document.getElementById('back-upload-status').textContent = 'Đã lưu mặt sau.';
                        btnCapture.style.display = 'none';
                        btnRetry.style.display = 'inline-block';
                        btnNext.style.display = 'inline-block';
                        video.pause();
                    } else {
                        document.getElementById('back-upload-status').textContent = `Lỗi: ${data.detail}`;
                    }
                } catch(error) {
                    document.getElementById('back-upload-status').textContent = `Lỗi kết nối: ${error.message}`;
                }
            }, 'image/jpeg', 0.9);
        });

        btnNext.addEventListener('click', async () => {
            btnRetry.disabled = true;
            btnNext.disabled = true;
            if(localStream) localStream.getTracks().forEach(track => track.stop());
            
            // Ở bước sau sẽ gọi API Processing OCR
            const nextStepDiv = document.createElement('div');
            nextStepDiv.innerHTML = `<br><p class="status" id="ocr-status">⚡ Đang xử lý AI (Trích xuất OCR, Đọc mã QR, Cắt khuôn mặt)...</p>
            <div id="ocr-result" style="background:#eee; padding:10px; border-radius:4px; font-family:monospace; margin-top:10px; display:none;"></div>`;
            appDiv.appendChild(nextStepDiv);

            // Gọi API OCR, QR, Face sequentially with early exits on error
            try {
                const ocrRes = await fetch(`/api/kyc/ocr?session_id=${currentSessionId}`, { method: 'POST' });
                if (!ocrRes.ok) {
                    const err = await ocrRes.json();
                    throw new Error(`OCR Failed: ${err.detail}`);
                }
                const ocrData = await ocrRes.json();
                
                const qrRes = await fetch(`/api/kyc/qr?session_id=${currentSessionId}`, { method: 'POST' });
                if (!qrRes.ok) {
                    const err = await qrRes.json();
                    throw new Error(`QR Failed: ${err.detail}`);
                }
                const qrData = await qrRes.json();
                
                const faceRes = await fetch(`/api/kyc/face/extract?session_id=${currentSessionId}`, { method: 'POST' });
                if (!faceRes.ok) {
                    const err = await faceRes.json();
                    throw new Error(`Face Extract Failed: ${err.detail}`);
                }
                const faceData = await faceRes.json();
                
                document.getElementById('ocr-status').textContent = '✅ Xử lý AI thành công (Trạng thái: SELFIE_CHALLENGE_ISSUED)';
                document.getElementById('ocr-status').style.color = 'green';
                const resultDiv = document.getElementById('ocr-result');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = `
                    <strong>Số thẻ:</strong> ${ocrData.data.id_number.value || 'N/A'} (Conf: ${ocrData.data.id_number.confidence.toFixed(2)})<br>
                    <strong>Họ tên:</strong> ${ocrData.data.full_name.value || 'N/A'} (Conf: ${ocrData.data.full_name.confidence.toFixed(2)})<br>
                    <strong>Dữ liệu QR:</strong> ${qrData.qr_detected ? 'Hợp lệ' : 'Không tìm thấy'}<br>
                `;
                
                if (!faceData.extracted) {
                    throw new Error(faceData.message);
                }

                renderLivenessChallengeStep();

            } catch(error) {
                document.getElementById('ocr-status').textContent = `❌ Lỗi xử lý AI: ${error.message}. Hình ảnh giấy tờ có thể không hợp lệ.`;
                document.getElementById('ocr-status').style.color = 'red';
                
                // Hiển thị nút làm lại từ đầu
                const restartBtn = document.createElement('button');
                restartBtn.textContent = "Làm lại từ đầu";
                restartBtn.style.marginTop = "10px";
                restartBtn.style.backgroundColor = "#f44336";
                restartBtn.onclick = () => location.reload();
                
                const resultDiv = document.getElementById('ocr-result');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = "";
                resultDiv.appendChild(restartBtn);
            }
        });
    }

    async function renderLivenessChallengeStep() {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step';
        stepDiv.innerHTML = `<h3>Bước 3: Xác thực Liveness (Người thật)</h3><p id="liveness-desc">Đang sinh yêu cầu thử thách...</p>`;
        appDiv.appendChild(stepDiv);
        
        try {
            const res = await fetch(`/api/kyc/liveness/challenge?session_id=${currentSessionId}`);
            const data = await res.json();
            
            if(res.ok) {
                const actionMap = {
                    "look_straight": "NHÌN THẲNG",
                    "turn_left": "QUAY MẶT SANG TRÁI",
                    "turn_right": "QUAY MẶT SANG PHẢI",
                    "look_up": "NGƯỚC MẶT LÊN TRÊN"
                };
                
                stepDiv.innerHTML = `
                    <h3>Bước 3: Thử thách Liveness</h3>
                    <p style="font-size: 16px;">Vui lòng đưa khuôn mặt vào trong khung hình oval và thực hiện theo yêu cầu:</p>
                    <div class="camera-container" style="margin-bottom: 10px;">
                        <video id="camera-liveness" autoplay playsinline style="transform: scaleX(-1);"></video>
                        <div class="oval-overlay" id="liveness-oval"></div>
                        <div class="overlay-instruction" id="liveness-instruction">
                            <span style="font-size: 20px; color: #fff;">${actionMap[data.challenge_type] || data.challenge_type}</span>
                        </div>
                    </div>
                    <button id="btn-capture-liveness">Chụp Selfie xác nhận</button>
                    <button id="btn-retry-liveness" style="display: none; background-color: #f44336;">Thử lại</button>
                    <p id="liveness-status"></p>
                `;
                
                const video = document.getElementById('camera-liveness');
                const btnRetry = document.getElementById('btn-retry-liveness');
                const btnCapture = document.getElementById('btn-capture-liveness');
                
                let localStream = null;
                
                function startCameraAndAutoCapture() {
                    btnRetry.style.display = 'none';
                    btnCapture.style.display = 'none';
                    document.getElementById('liveness-oval').style.borderColor = '#00ff00';
                    document.getElementById('liveness-status').innerHTML = '';
                    
                    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
                        .then(stream => { 
                            localStream = stream;
                            video.srcObject = stream; 
                            
                            // Đợi 2 giây đầu tiên để người dùng kịp đọc hướng dẫn
                            setTimeout(() => {
                                window.livenessInterval = setInterval(() => {
                                    if (!btnCapture.disabled) {
                                        document.getElementById('liveness-status').innerHTML = '<span style="color:blue">📸 Đang tự động kiểm tra...</span>';
                                        btnCapture.click();
                                    }
                                }, 1000); // Rút ngắn thời gian chụp liên tục xuống 1 giây cho nhạy hơn 
                            }, 1500);
                        })
                        .catch(err => { document.getElementById('liveness-status').textContent = `Lỗi Camera: ${err.message}`; });
                }
                
                startCameraAndAutoCapture();
                
                btnRetry.addEventListener('click', () => {
                    // Start over liveness challenge step to get a new challenge
                    if (localStream) localStream.getTracks().forEach(track => track.stop());
                    if (window.livenessInterval) clearInterval(window.livenessInterval);
                    stepDiv.remove();
                    renderLivenessChallengeStep();
                });
                    
                btnCapture.addEventListener('click', () => {
                    if(!localStream) return;
                    
                    const MAX_WIDTH = 800;
                    let vw = video.videoWidth || video.clientWidth || 640;
                    let vh = video.videoHeight || video.clientHeight || 480;
                    if (vw > MAX_WIDTH) {
                        vh = Math.floor(vh * (MAX_WIDTH / vw));
                        vw = MAX_WIDTH;
                    }

                    const canvas = document.createElement('canvas');
                    canvas.width = vw;
                    canvas.height = vh;
                    const ctx = canvas.getContext('2d');
                    ctx.translate(canvas.width, 0);
                    ctx.scale(-1, 1); // Lật ảnh giống hiệu ứng gương
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                    
                    canvas.toBlob(async (blob) => {
                        document.getElementById('liveness-oval').style.borderColor = 'yellow';
                        btnCapture.disabled = true;
                        
                        const formData = new FormData();
                        formData.append('session_id', currentSessionId);
                        formData.append('challenge_id', data.challenge_id);
                        formData.append('image', blob, 'selfie.jpg');

                        try {
                            const verifyRes = await fetch('/api/kyc/liveness/verify', {
                                method: 'POST',
                                body: formData
                            });
                            const verifyData = await verifyRes.json();
                            
                            if (verifyRes.ok && verifyData.success && verifyData.session_status !== 'FAILED_RETRY') {
                                if (window.livenessInterval) clearInterval(window.livenessInterval);
                                if(localStream) localStream.getTracks().forEach(track => track.stop());
                                document.getElementById('liveness-oval').style.borderColor = '#00ff00';

                                document.getElementById('liveness-status').innerHTML = `
                                    <h3 style="color: ${verifyData.session_status === 'COMPLETED' || verifyData.session_status === 'DECIDED' ? 'green' : 'red'};">HOÀN TẤT eKYC!</h3>
                                    <p>Liveness: <strong>PASS</strong></p>
                                    <p>Face Match: <strong>${verifyData.face_match_passed ? "KHỚP" : "KHÔNG KHỚP"}</strong> (Tỷ lệ: ${(verifyData.similarity_score * 100).toFixed(2)}%)</p>
                                    <hr>
                                    <h4>Đánh giá Gian Lận (Decision Engine):</h4>
                                    <p>Điểm rủi ro: <strong>${verifyData.decision.risk_score}</strong></p>
                                    <p>Lý do: <strong>${verifyData.decision.fraud_reasons.join(', ') || 'Không có'}</strong></p>
                                    <p>Quyết định cuối cùng: <strong style="font-size: 20px">${verifyData.decision.final_status}</strong></p>
                                    <p>Trạng thái Phiên: <strong>${verifyData.session_status}</strong></p>
                                `;
                            } else {
                                let errorMsg = verifyData.message || verifyData.detail || "Không hợp lệ";
                                
                                // Nếu chỉ là liveness failed (chưa quay đủ góc), KHÔNG DỪNG CAMERA, cho auto-capture thử tiếp
                                if (verifyRes.ok && verifyData.success === false && verifyData.liveness_passed === false) {
                                    document.getElementById('liveness-oval').style.borderColor = 'orange';
                                    document.getElementById('liveness-status').innerHTML = `
                                        <span style="color:orange; font-weight:bold;">Gợi ý: ${errorMsg}</span>
                                    `;
                                    btnCapture.disabled = false; // Mở lại nút để interval lần sau bấm được
                                } else {
                                    // Nếu lỗi nghiêm trọng (face mismatch, API error, expired...) thì dừng camera
                                    if (window.livenessInterval) clearInterval(window.livenessInterval);
                                    if(localStream) localStream.getTracks().forEach(track => track.stop());
                                    
                                    document.getElementById('liveness-oval').style.borderColor = 'red';
                                    btnCapture.disabled = false;
                                    btnRetry.style.display = 'inline-block';
                                    
                                    if (verifyData.session_status === 'FAILED_RETRY') {
                                        errorMsg = "Khuôn mặt không khớp hoặc rủi ro cao. Vui lòng thử lại.";
                                    }
                                    
                                    document.getElementById('liveness-status').innerHTML = `
                                        <span style="color:red; font-weight:bold;">Thất bại: ${errorMsg}</span>
                                    `;
                                }
                            }
                        } catch (err) {
                            if (window.livenessInterval) clearInterval(window.livenessInterval);
                            btnCapture.disabled = false;
                            btnRetry.style.display = 'inline-block';
                            document.getElementById('liveness-status').innerHTML = `<span style="color:red">Lỗi mạng: ${err.message}</span>`;
                        }
                    }, 'image/jpeg', 0.8);
                });

            } else {
                stepDiv.innerHTML += `<p style="color:red">Lỗi: ${data.detail}</p>`;
            }
        } catch(e) {
            stepDiv.innerHTML += `<p style="color:red">Lỗi: ${e.message}</p>`;
        }
    }

    // Start
    initSession();
});
