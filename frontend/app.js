document.addEventListener('DOMContentLoaded', () => {
    const statusSpan = document.querySelector('.status');
    const appDiv = document.getElementById('app');

    // Helper: parse JSON an toàn từ response, tránh lỗi nếu server trả về non-JSON (HTML/Text lỗi)
    async function safeJson(response) {
        const text = await response.text();
        try {
            return JSON.parse(text);
        } catch (e) {
            return { detail: text || `HTTP ${response.status}` };
        }
    }
    
    let currentSessionId = null;

    // ─── 0. Khởi tạo phiên KYC ─────────────────────────────────────────
    async function initSession() {
        try {
            statusSpan.textContent = 'Đang khởi tạo phiên KYC...';
            statusSpan.style.color = '#0066cc';
            
            const response = await fetch('/api/kyc/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await safeJson(response);
            
            if (response.ok && data.id) {
                currentSessionId = data.id;
                statusSpan.textContent = `Session: ${currentSessionId}`;
                renderConsentStep();
            } else {
                showInitError(data.detail || 'Không thể tạo phiên làm việc.');
            }
        } catch (error) {
            showInitError(`Lỗi kết nối máy chủ: ${error.message}`);
        }
    }

    function showInitError(errMsg) {
        statusSpan.textContent = `Lỗi: ${errMsg}`;
        statusSpan.style.color = '#f44336';
        
        let retryBtn = document.getElementById('btn-retry-init');
        if (!retryBtn) {
            retryBtn = document.createElement('button');
            retryBtn.id = 'btn-retry-init';
            retryBtn.textContent = '🔄 Thử lại kết nối';
            retryBtn.style.marginTop = '10px';
            retryBtn.style.backgroundColor = '#f44336';
            retryBtn.onclick = () => {
                retryBtn.remove();
                initSession();
            };
            const initDiv = document.getElementById('step-init');
            if (initDiv) initDiv.appendChild(retryBtn);
        }
    }

    // ─── 1. Bước Đồng ý Điều Khoản ──────────────────────────────────────
    function renderConsentStep() {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step';
        stepDiv.id = 'step-consent';
        stepDiv.innerHTML = `
            <h3>Bước: Đồng ý điều khoản</h3>
            <p>Hệ thống cần thu thập hình ảnh CCCD và khuôn mặt để xác minh danh tính. Bạn có đồng ý?</p>
            <button id="btn-consent">Đồng ý</button>
            <p id="consent-status" style="margin-top: 10px;"></p>
        `;
        appDiv.appendChild(stepDiv);

        const btnConsent = document.getElementById('btn-consent');
        const statusP = document.getElementById('consent-status');

        btnConsent.addEventListener('click', async () => {
            btnConsent.disabled = true;
            statusP.textContent = 'Đang gửi xác nhận...';
            statusP.style.color = '#0066cc';
            
            try {
                const res = await fetch(`/api/kyc/${currentSessionId}/consent`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ consent: true })
                });
                const data = await safeJson(res);
                
                if (res.ok) {
                    statusP.textContent = '✅ Đã đồng ý điều khoản (CONSENTED)';
                    statusP.style.color = 'green';
                    renderDocumentFrontStep();
                } else {
                    btnConsent.disabled = false;
                    statusP.textContent = `❌ Lỗi: ${data.detail || 'Không thể xác nhận điều khoản'}`;
                    statusP.style.color = 'red';
                }
            } catch (error) {
                btnConsent.disabled = false;
                statusP.textContent = `❌ Lỗi kết nối: ${error.message}`;
                statusP.style.color = 'red';
            }
        });
    }

    // ─── 2. Bước Chụp Mặt Trước CCCD ───────────────────────────────────
    function renderDocumentFrontStep() {
        let stepDiv = document.getElementById('step-front');
        if (!stepDiv) {
            stepDiv = document.createElement('div');
            stepDiv.className = 'step';
            stepDiv.id = 'step-front';
            appDiv.appendChild(stepDiv);
        }
        
        stepDiv.innerHTML = `
            <h3>Bước 1: Chụp mặt trước Giấy tờ</h3>
            <p>Vui lòng đưa <strong>mặt trước CCCD / Căn cước</strong> vào khung hình (rõ nét, không lóa sáng).</p>
            <div style="margin-bottom: 10px;">
                <video id="camera-preview" autoplay playsinline style="width: 100%; max-width: 440px; border: 1px solid #ccc; border-radius: 6px;"></video>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button id="btn-capture-front">📸 Chụp ảnh</button>
                <button id="btn-retry-front" style="display: none; background-color: #f44336;">🔄 Chụp lại</button>
                <button id="btn-next-front" style="display: none; background-color: #4CAF50;">Tiếp tục sang mặt sau ➡️</button>
            </div>
            <p id="front-upload-status" style="margin-top: 10px; font-weight: 500;"></p>
        `;

        const video = document.getElementById('camera-preview');
        const btnCapture = document.getElementById('btn-capture-front');
        const btnRetry = document.getElementById('btn-retry-front');
        const btnNext = document.getElementById('btn-next-front');
        const statusText = document.getElementById('front-upload-status');
        
        let localStream = null;

        function startCamera() {
            statusText.textContent = 'Đang khởi động camera...';
            statusText.style.color = '#555';
            
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } } })
                .then(stream => { 
                    localStream = stream;
                    video.srcObject = stream; 
                    video.play();
                    statusText.textContent = 'Camera đã sẵn sàng. Hãy canh chỉnh thẻ vào khung hình rồi bấm Chụp.';
                    statusText.style.color = '#333';
                })
                .catch(err => {
                    statusText.innerHTML = `<span style="color:red">❌ Lỗi Camera: ${err.message}. Vui lòng cấp quyền camera và thử lại.</span>`;
                    btnCapture.style.display = 'none';
                    btnRetry.style.display = 'inline-block';
                    btnRetry.textContent = '🔄 Thử lại Camera';
                });
        }
        
        startCamera();

        btnRetry.addEventListener('click', () => {
            btnRetry.style.display = 'none';
            btnNext.style.display = 'none';
            btnCapture.style.display = 'inline-block';
            btnCapture.disabled = false;
            statusText.textContent = '';
            startCamera();
        });

        btnNext.addEventListener('click', () => {
            if (localStream) localStream.getTracks().forEach(track => track.stop());
            renderDocumentBackStep();
        });

        btnCapture.addEventListener('click', () => {
            if (!localStream) return;
            
            const MAX_WIDTH = 1280;
            let vw = video.videoWidth || 1280;
            let vh = video.videoHeight || 720;
            if (vw > MAX_WIDTH) {
                vh = Math.floor(vh * (MAX_WIDTH / vw));
                vw = MAX_WIDTH;
            }
            
            const canvas = document.createElement('canvas');
            canvas.width = vw;
            canvas.height = vh;
            canvas.getContext('2d').drawImage(video, 0, 0, vw, vh);
            
            btnCapture.disabled = true;
            statusText.textContent = '⏳ Đang tải ảnh mặt trước lên...';
            statusText.style.color = '#0066cc';
            
            canvas.toBlob(async (blob) => {
                if (!blob) {
                    statusText.textContent = '❌ Lỗi khi chụp ảnh từ camera. Vui lòng bấm Chụp lại.';
                    statusText.style.color = 'red';
                    btnCapture.disabled = false;
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', blob, 'front.jpg');
                
                try {
                    const res = await fetch(`/api/kyc/document/front?session_id=${currentSessionId}`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await safeJson(res);
                    if (res.ok) {
                        statusText.textContent = '✅ Đã lưu ảnh mặt trước thành công.';
                        statusText.style.color = 'green';
                        btnCapture.style.display = 'none';
                        btnRetry.style.display = 'inline-block';
                        btnRetry.textContent = '🔄 Chụp lại';
                        btnNext.style.display = 'inline-block';
                        video.pause();
                    } else {
                        statusText.textContent = `❌ Lỗi tải lên: ${data.detail || 'Không thể lưu ảnh'}`;
                        statusText.style.color = 'red';
                        btnCapture.disabled = false;
                        btnRetry.style.display = 'inline-block';
                        btnRetry.textContent = '🔄 Chụp lại';
                    }
                } catch(error) {
                    statusText.textContent = `❌ Lỗi kết nối: ${error.message}`;
                    statusText.style.color = 'red';
                    btnCapture.disabled = false;
                    btnRetry.style.display = 'inline-block';
                    btnRetry.textContent = '🔄 Thử lại';
                }
            }, 'image/jpeg', 0.9);
        });
    }

    // ─── 3. Bước Chụp Mặt Sau CCCD ────────────────────────────────────
    function renderDocumentBackStep() {
        let stepDiv = document.getElementById('step-back');
        if (!stepDiv) {
            stepDiv = document.createElement('div');
            stepDiv.className = 'step';
            stepDiv.id = 'step-back';
            appDiv.appendChild(stepDiv);
        }
        
        stepDiv.innerHTML = `
            <h3>Bước 2: Chụp mặt sau Giấy tờ</h3>
            <p>Vui lòng lật thẻ và đưa <strong>mặt sau CCCD / Căn cước</strong> vào khung hình.</p>
            <div style="margin-bottom: 10px;">
                <video id="camera-preview-back" autoplay playsinline style="width: 100%; max-width: 440px; border: 1px solid #ccc; border-radius: 6px;"></video>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button id="btn-capture-back">📸 Chụp mặt sau</button>
                <button id="btn-retry-back" style="display: none; background-color: #f44336;">🔄 Chụp lại</button>
                <button id="btn-next-back" style="display: none; background-color: #4CAF50;">Bắt đầu phân tích AI ⚡</button>
            </div>
            <p id="back-upload-status" style="margin-top: 10px; font-weight: 500;"></p>
        `;

        const video = document.getElementById('camera-preview-back');
        const btnCapture = document.getElementById('btn-capture-back');
        const btnRetry = document.getElementById('btn-retry-back');
        const btnNext = document.getElementById('btn-next-back');
        const statusText = document.getElementById('back-upload-status');
        
        let localStream = null;

        function startCamera() {
            statusText.textContent = 'Đang bật camera...';
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } } })
                .then(stream => { 
                    localStream = stream;
                    video.srcObject = stream; 
                    video.play();
                    statusText.textContent = 'Camera đã sẵn sàng. Hãy canh mặt sau thẻ rồi bấm Chụp.';
                    statusText.style.color = '#333';
                })
                .catch(err => {
                    statusText.innerHTML = `<span style="color:red">❌ Lỗi Camera: ${err.message}.</span>`;
                    btnCapture.style.display = 'none';
                    btnRetry.style.display = 'inline-block';
                    btnRetry.textContent = '🔄 Thử lại Camera';
                });
        }
        
        startCamera();

        btnRetry.addEventListener('click', () => {
            btnRetry.style.display = 'none';
            btnNext.style.display = 'none';
            btnCapture.style.display = 'inline-block';
            btnCapture.disabled = false;
            statusText.textContent = '';
            startCamera();
        });

        btnCapture.addEventListener('click', () => {
            if (!localStream) return;
            
            const MAX_WIDTH = 1280;
            let vw = video.videoWidth || 1280;
            let vh = video.videoHeight || 720;
            if (vw > MAX_WIDTH) {
                vh = Math.floor(vh * (MAX_WIDTH / vw));
                vw = MAX_WIDTH;
            }
            const canvas = document.createElement('canvas');
            canvas.width = vw;
            canvas.height = vh;
            canvas.getContext('2d').drawImage(video, 0, 0, vw, vh);
            
            btnCapture.disabled = true;
            statusText.textContent = '⏳ Đang tải ảnh mặt sau lên...';
            statusText.style.color = '#0066cc';
            
            canvas.toBlob(async (blob) => {
                if (!blob) {
                    statusText.textContent = '❌ Không thể chụp ảnh. Vui lòng bấm Chụp lại.';
                    statusText.style.color = 'red';
                    btnCapture.disabled = false;
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', blob, 'back.jpg');
                
                try {
                    const res = await fetch(`/api/kyc/document/back?session_id=${currentSessionId}`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await safeJson(res);
                    if (res.ok) {
                        statusText.textContent = '✅ Đã lưu mặt sau thành công.';
                        statusText.style.color = 'green';
                        btnCapture.style.display = 'none';
                        btnRetry.style.display = 'inline-block';
                        btnRetry.textContent = '🔄 Chụp lại';
                        btnNext.style.display = 'inline-block';
                        video.pause();
                    } else {
                        statusText.textContent = `❌ Lỗi: ${data.detail || 'Không thể lưu ảnh'}`;
                        statusText.style.color = 'red';
                        btnCapture.disabled = false;
                        btnRetry.style.display = 'inline-block';
                    }
                } catch(error) {
                    statusText.textContent = `❌ Lỗi kết nối: ${error.message}`;
                    statusText.style.color = 'red';
                    btnCapture.disabled = false;
                    btnRetry.style.display = 'inline-block';
                }
            }, 'image/jpeg', 0.9);
        });

        // ─── 4. Phân tích AI CCCD (OCR + QR + Trích xuất khuôn mặt) ────
        btnNext.addEventListener('click', async () => {
            btnRetry.disabled = true;
            btnNext.disabled = true;
            if (localStream) localStream.getTracks().forEach(track => track.stop());
            
            runAiProcessingStep();
        });
    }

    async function runAiProcessingStep() {
        let aiStepDiv = document.getElementById('step-ai-processing');
        if (!aiStepDiv) {
            aiStepDiv = document.createElement('div');
            aiStepDiv.className = 'step';
            aiStepDiv.id = 'step-ai-processing';
            appDiv.appendChild(aiStepDiv);
        }
        
        aiStepDiv.innerHTML = `
            <h3>Phân tích dữ liệu thẻ CCCD</h3>
            <p class="status" id="ocr-status">⚡ Đang xử lý AI (Trích xuất OCR, Đọc mã QR, Cắt khuôn mặt)...</p>
            <div id="ocr-result" style="background:#f9f9f9; border: 1px solid #e0e0e0; padding:15px; border-radius:6px; font-family:inherit; margin-top:10px; display:none;"></div>
            <div id="ocr-actions" style="margin-top: 15px; display: none;"></div>
        `;

        const statusEl = document.getElementById('ocr-status');
        const resultDiv = document.getElementById('ocr-result');
        const actionsDiv = document.getElementById('ocr-actions');

        try {
            // 1. Chạy OCR
            statusEl.textContent = '⚡ [1/3] Đang đọc thông tin CCCD (OCR)...';
            const ocrRes = await fetch(`/api/kyc/ocr?session_id=${currentSessionId}`, { method: 'POST' });
            const ocrData = await safeJson(ocrRes);
            if (!ocrRes.ok) {
                throw new Error(ocrData.detail || 'Lỗi khi trích xuất OCR');
            }
            
            // 2. Chạy QR Code
            statusEl.textContent = '⚡ [2/3] Đang quét mã QR trên CCCD...';
            const qrRes = await fetch(`/api/kyc/qr?session_id=${currentSessionId}`, { method: 'POST' });
            const qrData = await safeJson(qrRes);
            if (!qrRes.ok) {
                throw new Error(qrData.detail || 'Lỗi khi quét mã QR');
            }
            
            // 3. Trích xuất khuôn mặt từ thẻ
            statusEl.textContent = '⚡ [3/3] Đang phát hiện & cắt ảnh chân dung từ CCCD...';
            const faceRes = await fetch(`/api/kyc/face/extract?session_id=${currentSessionId}`, { method: 'POST' });
            const faceData = await safeJson(faceRes);
            if (!faceRes.ok) {
                throw new Error(faceData.detail || 'Lỗi khi trích xuất khuôn mặt thẻ');
            }
            
            if (!faceData.extracted) {
                throw new Error(faceData.message || 'Không tìm thấy khuôn mặt hợp lệ trên ảnh thẻ CCCD');
            }

            statusEl.textContent = '✅ Xử lý AI thành công!';
            statusEl.style.color = 'green';
            resultDiv.style.display = 'block';
            
            const idVal = (ocrData.data && ocrData.data.id_number && ocrData.data.id_number.value) ? ocrData.data.id_number.value : 'N/A';
            const nameVal = (ocrData.data && ocrData.data.full_name && ocrData.data.full_name.value) ? ocrData.data.full_name.value : 'N/A';
            const qrStatus = qrData.qr_detected ? '✅ Hợp lệ' : '⚠️ Không tìm thấy (vẫn tiếp tục)';
            
            resultDiv.innerHTML = `
                <p><strong>Số thẻ CCCD:</strong> ${idVal}</p>
                <p><strong>Họ và tên:</strong> ${nameVal}</p>
                <p><strong>Mã QR CCCD:</strong> ${qrStatus}</p>
                <p><strong>Ảnh chân dung CCCD:</strong> ✅ Đã trích xuất đặc trưng</p>
            `;
            
            // Chuyển sang bước Liveness
            setTimeout(() => {
                renderLivenessChallengeStep();
            }, 600);

        } catch(error) {
            statusEl.innerHTML = `<span style="color:red">❌ Lỗi xử lý AI: ${error.message}</span>`;
            actionsDiv.style.display = 'flex';
            actionsDiv.style.gap = '10px';
            actionsDiv.innerHTML = `
                <button id="btn-re-ocr" style="background-color: #0066cc;">🔄 Thử phân tích lại</button>
                <button id="btn-recapture-doc" style="background-color: #f44336;">📸 Chụp lại ảnh CCCD</button>
            `;
            
            document.getElementById('btn-re-ocr').onclick = () => {
                actionsDiv.style.display = 'none';
                runAiProcessingStep();
            };
            
            document.getElementById('btn-recapture-doc').onclick = () => {
                aiStepDiv.remove();
                const backStep = document.getElementById('step-back');
                if (backStep) backStep.remove();
                renderDocumentFrontStep();
            };
        }
    }

    // ─── 5. Bước Xác Thực Liveness & Đối Soát Khuôn Mặt ────────────────
    async function renderLivenessChallengeStep() {
        let stepDiv = document.getElementById('step-liveness');
        if (!stepDiv) {
            stepDiv = document.createElement('div');
            stepDiv.className = 'step';
            stepDiv.id = 'step-liveness';
            appDiv.appendChild(stepDiv);
        }
        
        stepDiv.innerHTML = `
            <h3>Bước 3: Xác thực khuôn mặt (Liveness & Face Match)</h3>
            <p id="liveness-desc">⏳ Đang lấy yêu cầu thử thách chuyển động...</p>
        `;
        
        try {
            const res = await fetch(`/api/kyc/liveness/challenge?session_id=${currentSessionId}`);
            const data = await safeJson(res);
            
            if (!res.ok) {
                showLivenessInitError(data.detail || 'Không thể tạo thử thách Liveness.');
                return;
            }

            const actionMap = {
                "look_straight": "NHÌN THẲNG VÀO CAMERA",
                "turn_left_gentle": "NGHIÊNG NHẸ SANG TRÁI 👈",
                "turn_right_gentle": "NGHIÊNG NHẸ SANG PHẢI 👉",
                "turn_left": "NGHIÊNG NHẸ SANG TRÁI 👈",
                "turn_right": "NGHIÊNG NHẸ SANG PHẢI 👉"
            };
            
            const instructionText = actionMap[data.challenge_type] || "NHÌN THẲNG VÀO CAMERA";
            
            stepDiv.innerHTML = `
                <h3>Bước 3: Xác thực khuôn mặt (Liveness & Face Match)</h3>
                <p style="font-size: 15px;">Vui lòng giữ khuôn mặt trong khung oval và thực hiện theo yêu cầu:</p>
                <div class="camera-container" style="margin-bottom: 12px;">
                    <video id="camera-liveness" autoplay playsinline style="transform: scaleX(-1);"></video>
                    <div class="oval-overlay" id="liveness-oval"></div>
                    <div class="overlay-instruction" id="liveness-instruction">
                        <span style="font-size: 18px; color: #fff;">${instructionText}</span>
                    </div>
                </div>
                <div id="liveness-controls" style="margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
                    <button id="btn-manual-capture" style="display: none;">Chụp thủ công</button>
                    <button id="btn-retry-liveness" style="display: none; background-color: #f44336;">🔄 Thử lại Selfie</button>
                    <button id="btn-restart-all" style="display: none; background-color: #555;">📋 Chụp lại từ đầu</button>
                </div>
                <div id="liveness-status" style="margin-top: 10px; font-weight: 500;"></div>
            `;
            
            const video = document.getElementById('camera-liveness');
            const ovalOverlay = document.getElementById('liveness-oval');
            const statusDiv = document.getElementById('liveness-status');
            const btnRetry = document.getElementById('btn-retry-liveness');
            const btnRestart = document.getElementById('btn-restart-all');
            
            let localStream = null;
            let isLoopRunning = false;
            let isBusy = false;

            btnRetry.addEventListener('click', () => {
                if (localStream) localStream.getTracks().forEach(track => track.stop());
                isLoopRunning = false;
                stepDiv.remove();
                renderLivenessChallengeStep();
            });

            btnRestart.addEventListener('click', () => {
                if (localStream) localStream.getTracks().forEach(track => track.stop());
                isLoopRunning = false;
                location.reload();
            });

            // Khởi động Camera và Vòng lặp tự động chụp (Tối ưu non-blocking)
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } } })
                .then(stream => { 
                    localStream = stream;
                    video.srcObject = stream;
                    video.play();
                    
                    statusDiv.innerHTML = '<span style="color:#0066cc;">📸 Đang tự động kiểm tra chuyển động khuôn mặt...</span>';
                    ovalOverlay.style.borderColor = '#00ff00';
                    isLoopRunning = true;
                    
                    // Bắt đầu vòng lặp sau 1 giây chuẩn bị
                    setTimeout(() => {
                        triggerNextVerificationFrame();
                    }, 1000);
                })
                .catch(err => {
                    statusDiv.innerHTML = `<span style="color:red">❌ Không thể bật camera trước: ${err.message}.</span>`;
                    btnRetry.style.display = 'inline-block';
                    btnRetry.textContent = '🔄 Thử lại Camera';
                });

            // Hàm gửi frame kiểm tra (Không bị chồng chéo request, phản hồi nhạy)
            async function triggerNextVerificationFrame() {
                if (!isLoopRunning || isBusy || !localStream) return;
                
                isBusy = true;
                
                const targetWidth = 640;
                let vw = video.videoWidth || 640;
                let vh = video.videoHeight || 480;
                let scale = targetWidth / vw;
                let finalW = targetWidth;
                let finalH = Math.floor(vh * scale);

                const canvas = document.createElement('canvas');
                canvas.width = finalW;
                canvas.height = finalH;
                const ctx = canvas.getContext('2d');
                ctx.translate(canvas.width, 0);
                ctx.scale(-1, 1);
                ctx.drawImage(video, 0, 0, finalW, finalH);

                canvas.toBlob(async (blob) => {
                    if (!blob || !isLoopRunning) {
                        isBusy = false;
                        if (isLoopRunning) setTimeout(triggerNextVerificationFrame, 350);
                        return;
                    }

                    const formData = new FormData();
                    formData.append('session_id', currentSessionId);
                    formData.append('challenge_id', data.challenge_id);
                    formData.append('image', blob, 'selfie.jpg');

                    try {
                        const verifyRes = await fetch('/api/kyc/liveness/verify', {
                            method: 'POST',
                            body: formData
                        });
                        const verifyData = await safeJson(verifyRes);

                        if (!isLoopRunning) return; // Nếu user đã bấm nút khác

                        if (verifyRes.ok && verifyData.success) {
                            // THÀNH CÔNG RỰC RỠ!
                            isLoopRunning = false;
                            if (localStream) localStream.getTracks().forEach(track => track.stop());
                            ovalOverlay.style.borderColor = '#00ff00';

                            statusDiv.innerHTML = `
                                <div style="background: #e8f5e9; border: 1px solid #4caf50; border-radius: 6px; padding: 15px; margin-top: 10px;">
                                    <h3 style="color: #2e7d32; margin-top: 0;">🎉 XÁC THỰC eKYC THÀNH CÔNG!</h3>
                                    <p>✔️ Liveness: <strong>PASS (Người thật)</strong></p>
                                    <p>✔️ So khớp khuôn mặt: <strong>KHỚP (${(verifyData.similarity_score * 100).toFixed(1)}%)</strong></p>
                                    <p>✔️ Đánh giá rủi ro: <strong>${verifyData.decision.risk_score} điểm (${verifyData.decision.final_status})</strong></p>
                                    <p style="color: #2e7d32; font-weight: bold;">Hồ sơ định danh của bạn đã được phê duyệt.</p>
                                </div>
                            `;
                            return;
                        } 
                        
                        if (verifyRes.ok && verifyData.liveness_passed === false) {
                            // Chưa đạt góc liveness: Hiện gợi ý và tiếp tục vòng lặp
                            ovalOverlay.style.borderColor = '#ff9800';
                            statusDiv.innerHTML = `
                                <span style="color:#e65100; font-weight:bold;">👉 Gợi ý: ${verifyData.message || 'Làm theo hướng dẫn'}</span>
                            `;
                            isBusy = false;
                            setTimeout(triggerNextVerificationFrame, 350); // Nhịp 350ms vừa nhạy vừa nhẹ máy
                            return;
                        }

                        // LỖI XÁC THỰC: Không khớp mặt hoặc rủi ro cao hoặc hết hạn
                        isLoopRunning = false;
                        if (localStream) localStream.getTracks().forEach(track => track.stop());
                        ovalOverlay.style.borderColor = '#f44336';
                        
                        let failReason = verifyData.message || verifyData.detail || 'Xác thực không thành công.';
                        statusDiv.innerHTML = `
                            <div style="background: #ffebee; border: 1px solid #ef5350; border-radius: 6px; padding: 15px; margin-top: 10px;">
                                <h4 style="color: #c62828; margin-top: 0;">❌ XÁC THỰC THẤT BẠI</h4>
                                <p style="color: #c62828;">${failReason}</p>
                                <p style="font-size: 13px; color: #555;">Đừng lo lắng, bạn có thể thực hiện lại thử thách khuôn mặt hoặc chụp lại CCCD nếu ảnh thẻ bị mờ.</p>
                            </div>
                        `;
                        btnRetry.style.display = 'inline-block';
                        btnRestart.style.display = 'inline-block';

                    } catch (err) {
                        isLoopRunning = false;
                        if (localStream) localStream.getTracks().forEach(track => track.stop());
                        ovalOverlay.style.borderColor = '#f44336';
                        statusDiv.innerHTML = `<span style="color:red">❌ Lỗi kết nối kiểm tra: ${err.message}</span>`;
                        btnRetry.style.display = 'inline-block';
                        btnRestart.style.display = 'inline-block';
                    }
                }, 'image/jpeg', 0.82);
            }

        } catch (e) {
            showLivenessInitError(`Lỗi kết nối thử thách: ${e.message}`);
        }
    }

    function showLivenessInitError(msg) {
        const stepDiv = document.getElementById('step-liveness') || appDiv;
        stepDiv.innerHTML = `
            <h3>Bước 3: Xác thực khuôn mặt</h3>
            <div style="background: #ffebee; padding: 12px; border-radius: 6px; border: 1px solid #ef9a9a;">
                <p style="color: red; margin: 0 0 10px 0;">❌ ${msg}</p>
                <button id="btn-re-challenge" style="background-color: #f44336;">🔄 Lấy lại thử thách</button>
            </div>
        `;
        document.getElementById('btn-re-challenge').onclick = () => renderLivenessChallengeStep();
    }

    // Khởi chạy
    initSession();
});
