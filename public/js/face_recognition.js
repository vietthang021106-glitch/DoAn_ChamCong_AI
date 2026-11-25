(() => {
    const root = document.querySelector('[data-ai1-recognition]');
    if (!root) return;

    const csrfToken = root.dataset.csrf;
    const startButton = root.querySelector('[data-ai1-recognition-start]');
    const status = root.querySelector('[data-ai1-recognition-status]');
    const result = root.querySelector('[data-ai1-recognition-result]');
    const camera = root.querySelector('[data-ai1-recognition-camera]');
    const canvas = root.querySelector('[data-ai1-recognition-canvas]');
    const empty = root.querySelector('[data-ai1-recognition-empty]');
    let previewTimer = null;
    let sessionRunning = false;
    let previewEnabled = false;

    const reasonLabels = {
        NO_FACE: 'Không thấy khuôn mặt.',
        MULTIPLE_FACES: 'Chỉ để một người trong khung hình.',
        INVALID_EMBEDDING: 'Embedding khuôn mặt không hợp lệ.',
        BLUR: 'Ảnh quá mờ. Hãy giữ yên và kiểm tra ánh sáng.',
        STALE_FRAME: 'Khung hình camera đã cũ. Hãy thử lại.',
        CAMERA_TIMEOUT: 'Camera chưa gửi đủ ba khung hình mới.',
        INCONSISTENT_FACES: 'Ba ảnh không nhất quán cùng một khuôn mặt.',
        MODEL_UNAVAILABLE: 'Model nhận diện chưa sẵn sàng.',
        GALLERY_UNAVAILABLE: 'Gallery khuôn mặt chưa sẵn sàng.',
    };

    const setStatus = (message, state) => {
        status.textContent = message;
        status.dataset.state = state;
    };

    const refreshPreview = () => {
        if (!previewEnabled) return;
        camera.src = `/?action=face_camera_frame&ts=${Date.now()}`;
    };

    const startPreview = () => {
        previewEnabled = true;
        camera.hidden = false;
        canvas.hidden = true;
        empty.hidden = true;
        refreshPreview();
        clearInterval(previewTimer);
        previewTimer = setInterval(refreshPreview, 450);
    };

    const stopPreview = () => {
        previewEnabled = false;
        clearInterval(previewTimer);
        previewTimer = null;
    };

    const drawBestFrame = (payload) => {
        if (!payload.best_frame_jpeg || !Array.isArray(payload.bbox)) return;
        const image = new Image();
        image.onload = () => {
            canvas.width = Number(payload.frame_width) || image.naturalWidth;
            canvas.height = Number(payload.frame_height) || image.naturalHeight;
            const context = canvas.getContext('2d');
            context.drawImage(image, 0, 0, canvas.width, canvas.height);
            const [x1, y1, x2, y2] = payload.bbox.map(Number);
            context.lineWidth = Math.max(3, canvas.width / 240);
            context.strokeStyle = payload.recognized ? '#12b76a' : '#f04438';
            context.strokeRect(x1, y1, x2 - x1, y2 - y1);
            const label = payload.recognized
                ? `NV${payload.ma_nv} · ${payload.ho_ten || ''}`
                : 'UNKNOWN';
            context.font = `bold ${Math.max(18, canvas.width / 32)}px sans-serif`;
            const textWidth = context.measureText(label).width;
            const labelY = Math.max(28, y1 - 8);
            context.fillStyle = payload.recognized ? '#067647' : '#b42318';
            context.fillRect(x1, labelY - Math.max(24, canvas.width / 48), textWidth + 16, Math.max(30, canvas.width / 38));
            context.fillStyle = '#ffffff';
            context.fillText(label, x1 + 8, labelY);
            camera.hidden = true;
            canvas.hidden = false;
            empty.hidden = true;
        };
        image.src = `data:image/jpeg;base64,${payload.best_frame_jpeg}`;
    };

    const renderTerminalResult = (session) => {
        const payload = session.result || {};
        drawBestFrame(payload);
        result.hidden = false;
        if (payload.recognized) {
            setStatus('✓ NHẬN DIỆN THÀNH CÔNG', 'match');
            result.textContent = `Mã NV: ${payload.ma_nv} · ${payload.ho_ten || ''} | Similarity: ${Number(payload.score).toFixed(3)} · Threshold: ${Number(payload.threshold).toFixed(2)} | Độ nét: ${Number(payload.best_sharpness).toFixed(1)} | ${Number(payload.latency_ms).toFixed(0)} ms`;
        } else if (payload.reason === 'UNKNOWN') {
            setStatus('UNKNOWN · KHÔNG XÁC ĐỊNH KHUÔN MẶT', 'unknown');
            result.textContent = `Không có nhân viên nào vượt threshold. Similarity tốt nhất: ${Number(payload.score).toFixed(3)} · Threshold: ${Number(payload.threshold).toFixed(2)} | ${Number(payload.latency_ms).toFixed(0)} ms`;
        } else {
            setStatus('THỬ LẠI', 'retry');
            result.textContent = reasonLabels[payload.retry_reason] || 'Phiên nhận diện chưa hoàn tất. Không ghi chấm công.';
        }
        startButton.disabled = false;
        sessionRunning = false;
        stopPreview();
        window.setTimeout(() => {
            canvas.hidden = true;
            result.hidden = true;
            startPreview();
            setStatus('Sẵn sàng', 'idle');
        }, 4000);
    };

    const pollSession = async (sessionId) => {
        while (sessionRunning) {
            const response = await fetch(`/?action=face_recognition_status&session_id=${encodeURIComponent(sessionId)}`, {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) throw new Error(payload.message || 'Không đọc được tiến độ nhận diện.');
            if (payload.state === 'CAPTURING') {
                setStatus(`ĐANG QUÉT KHUÔN MẶT · ${Number(payload.captured_frames)}/3`, 'capturing');
            } else if (payload.state === 'PROCESSING') {
                setStatus('ĐANG XỬ LÝ...', 'processing');
            } else if (payload.state === 'COMPLETED' || payload.state === 'ABORTED') {
                renderTerminalResult(payload);
                return;
            }
            await new Promise((resolve) => window.setTimeout(resolve, 160));
        }
    };

    camera.addEventListener('load', () => {
        if (camera.naturalWidth > 0) {
            camera.hidden = false;
            empty.hidden = true;
        }
    });
    camera.addEventListener('error', () => {
        if (!previewEnabled) return;
        camera.hidden = true;
        empty.hidden = false;
        empty.textContent = 'Camera hiện không có frame mới. Kiểm tra camera hoặc thử lại.';
    });

    startButton.addEventListener('click', async () => {
        if (sessionRunning) return;
        startButton.disabled = true;
        result.hidden = true;
        startPreview();
        setStatus('ĐANG KHỞI TẠO PHIÊN...', 'processing');
        try {
            const body = new URLSearchParams({ _csrf_token: csrfToken });
            const response = await fetch('/?action=face_recognition_start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
                body,
                credentials: 'same-origin',
                cache: 'no-store',
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) throw new Error(payload.message || 'Không thể bắt đầu quét.');
            sessionRunning = true;
            setStatus('ĐANG QUÉT KHUÔN MẶT · 0/3', 'capturing');
            await pollSession(payload.session_id);
        } catch (error) {
            sessionRunning = false;
            startButton.disabled = false;
            setStatus('THỬ LẠI', 'retry');
            result.hidden = false;
            result.textContent = error.message;
        }
    });
})();
