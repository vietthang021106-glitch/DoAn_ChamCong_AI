(() => {
    const root = document.querySelector('[data-attendance-terminal]');
    if (!root) return;

    const csrfToken = root.dataset.csrf || '';
    const deviceId = root.dataset.deviceId || '';
    const deviceReady = root.dataset.deviceReady === 'true' && /^\d+$/.test(deviceId);
    const clock = root.querySelector('[data-terminal-clock]');
    const date = root.querySelector('[data-terminal-date]');
    const status = root.querySelector('[data-terminal-status]');
    const result = root.querySelector('[data-terminal-result]');
    const hint = root.querySelector('[data-terminal-hint]');
    const defaultHint = hint.textContent;
    const cameraWrap = root.querySelector('[data-terminal-camera-wrap]');
    const camera = root.querySelector('[data-terminal-camera]');
    const resultFrame = root.querySelector('[data-terminal-result-frame]');
    const cameraEmpty = root.querySelector('[data-terminal-camera-empty]');
    const scanRing = root.querySelector('[data-terminal-scan-ring]');
    const enrollmentPanel = root.querySelector('[data-terminal-enrollment]');
    const enrollmentEmployee = root.querySelector('[data-terminal-enrollment-employee]');
    const enrollmentProgress = root.querySelector('[data-terminal-enrollment-progress]');
    const enrollmentPose = root.querySelector('[data-terminal-enrollment-pose]');
    const enrollmentMessage = root.querySelector('[data-terminal-enrollment-message]');
    const enrollmentSteps = [...root.querySelectorAll('[data-terminal-enrollment-steps] [data-pose]')];
    const fullscreenButton = root.querySelector('[data-terminal-fullscreen]');
    const enrollmentUi = window.AI1EnrollmentUI;

    let scanLocked = false;
    let spacePressed = false;
    let cameraAvailable = false;
    let previewEnabled = false;
    let previewBusy = false;
    let previewTimer = null;
    let previewRequest = null;
    let previewObjectUrl = null;
    let resetTimer = null;
    let enrollmentTimer = null;
    let enrollmentBusy = false;
    let enrollmentState = 'IDLE';
    let enrollmentScanLock = false;
    let lastEnrollmentNotice = '';

    const setStatus = (message, state) => {
        status.textContent = message;
        status.dataset.state = state;
    };

    const updateClock = () => {
        const now = new Date();
        clock.textContent = new Intl.DateTimeFormat('vi-VN', {
            timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', second: '2-digit',
            hourCycle: 'h23',
        }).format(now);
        date.textContent = new Intl.DateTimeFormat('vi-VN', {
            timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long', day: '2-digit', month: 'long', year: 'numeric',
        }).format(now);
    };

    fullscreenButton?.addEventListener('click', async () => {
        try {
            if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
            else await document.exitFullscreen();
        } catch {
            setStatus('Trình duyệt không cho phép bật toàn màn hình.', 'error');
        }
    });

    const poseLabels = {
        frontal: 'Nhìn thẳng vào camera',
        left: 'Quay đầu sang trái',
        right: 'Quay đầu sang phải',
        up: 'Ngước đầu lên',
        down: 'Cúi đầu xuống',
    };

    const updateEnrollmentRing = (payload, state) => {
        if (!scanRing) return;
        const active = payload.mode === 'AUTO'
            && (state === 'ENROLLING' || state === 'AWAITING_CONFIRMATION');
        const model = active && enrollmentUi ? enrollmentUi.buildRingModel(payload) : { visible: false };
        if (!model.visible) {
            scanRing.replaceChildren();
            scanRing.hidden = true;
            return;
        }

        const namespace = 'http://www.w3.org/2000/svg';
        scanRing.setAttribute('viewBox', `0 0 ${model.width} ${model.height}`);
        scanRing.setAttribute('preserveAspectRatio', 'xMidYMid meet');
        scanRing.replaceChildren();
        model.segments.forEach((segment) => {
            const track = document.createElementNS(namespace, 'path');
            track.setAttribute('d', enrollmentUi.arcPath(
                model.centerX, model.centerY, model.radiusX, model.radiusY,
                segment.start, segment.trackExtent
            ));
            track.setAttribute('fill', 'none');
            track.setAttribute('stroke', '#d3dadd');
            track.setAttribute('stroke-width', String(model.strokeWidth));
            track.setAttribute('stroke-linecap', 'round');
            scanRing.appendChild(track);

            if (segment.extent <= 0) return;
            const progress = document.createElementNS(namespace, 'path');
            progress.setAttribute('d', enrollmentUi.arcPath(
                model.centerX, model.centerY, model.radiusX, model.radiusY,
                segment.start, segment.extent
            ));
            progress.setAttribute('fill', 'none');
            progress.setAttribute('stroke', segment.state === 'complete' ? '#176a3a'
                : (model.stableCount > 0 ? '#c38a22' : '#536d7a'));
            progress.setAttribute('stroke-width', String(model.strokeWidth + 1));
            progress.setAttribute('stroke-linecap', 'round');
            scanRing.appendChild(progress);
        });
        scanRing.hidden = false;
    };

    const refreshEnrollmentStatus = async () => {
        if (!deviceReady || document.hidden || enrollmentBusy) return;
        enrollmentBusy = true;
        try {
            const response = await fetch(`/?action=kiosk_enrollment_status&device_id=${encodeURIComponent(deviceId)}&ts=${Date.now()}`, {
                credentials: 'same-origin', cache: 'no-store',
            });
            const payload = await readJson(response);
            if (!response.ok || !payload.success) throw new Error(payload.message || 'Không đọc được phiên đăng ký.');
            const state = String(payload.state || 'IDLE');
            if (state === 'IDLE') {
                enrollmentPanel.hidden = true;
                updateEnrollmentRing({}, state);
                if (enrollmentState !== 'IDLE') {
                    enrollmentState = 'IDLE';
                    if (!scanLocked) {
                        setStatus('Vui lòng nhìn vào camera.', 'idle');
                        hint.hidden = false;
                        startPreview();
                    }
                }
                return;
            }

            enrollmentState = state;
            enrollmentPanel.hidden = false;
            hint.hidden = true;
            const captured = Math.max(0, Math.min(5, Number(payload.captured) || 0));
            updateEnrollmentRing(payload, state);
            enrollmentProgress.textContent = `${captured}/5`;
            enrollmentEmployee.textContent = payload.employee_name
                ? `${payload.employee_name} · Mã nhân viên ${payload.employee_id}`
                : (payload.employee_id ? `Mã nhân viên ${payload.employee_id}` : '');
            enrollmentSteps.forEach((step, index) => {
                step.classList.toggle('is-complete', index < captured);
                step.classList.toggle('is-active', index === captured && captured < 5);
            });
            enrollmentPose.textContent = poseLabels[payload.expected_pose] || (
                state === 'AWAITING_CONFIRMATION' ? 'Đã thu đủ năm góc' : 'Đang chuẩn bị'
            );
            enrollmentMessage.textContent = enrollmentUi
                ? enrollmentUi.guidanceFor({ ...payload, state })
                : 'Hãy làm theo hướng dẫn trên màn hình.';

            if (state === 'ENROLLING') {
                enrollmentScanLock = true;
                setStatus('ĐANG ĐĂNG KÝ KHUÔN MẶT', 'processing');
            } else if (state === 'AWAITING_CONFIRMATION') {
                enrollmentScanLock = true;
                enrollmentPose.textContent = 'Đã thu đủ năm góc';
                enrollmentMessage.textContent = enrollmentUi
                    ? enrollmentUi.guidanceFor({ ...payload, state })
                    : 'Đã đủ năm góc. Chờ quản lý kiểm tra và xác nhận lưu.';
                setStatus('ĐĂNG KÝ HOÀN TẤT · CHỜ XÁC NHẬN', 'processing');
            } else if (state === 'MANUAL_FALLBACK') {
                updateEnrollmentRing({}, state);
                enrollmentScanLock = true;
                enrollmentMessage.textContent = enrollmentUi
                    ? enrollmentUi.guidanceFor({ ...payload, state })
                    : 'Phiên tự động đã tạm dừng. Vui lòng báo quản lý để tiếp tục.';
                setStatus('CẦN ADMIN TIẾP TỤC ĐĂNG KÝ', 'error');
            } else if (state === 'OFFLINE' || state === 'FAILED' || state === 'EXPIRED') {
                updateEnrollmentRing({}, state);
                enrollmentMessage.textContent = enrollmentUi
                    ? enrollmentUi.guidanceFor({ ...payload, state })
                    : 'Phiên đăng ký đã dừng. Vui lòng báo quản lý.';
                enrollmentScanLock = true;
                setStatus(state === 'OFFLINE' ? 'AI1 TẠM THỜI KHÔNG KẾT NỐI' : 'PHIÊN ĐĂNG KÝ ĐÃ DỪNG', 'error');
            } else if (state === 'COMPLETED') {
                updateEnrollmentRing({}, state);
                enrollmentScanLock = false;
                enrollmentPanel.hidden = true;
                if (lastEnrollmentNotice !== state) {
                    lastEnrollmentNotice = state;
                    finish('success', 'ĐĂNG KÝ KHUÔN MẶT THÀNH CÔNG', payload.employee_name || '', null);
                }
            } else if (state === 'CANCELLED') {
                updateEnrollmentRing({}, state);
                enrollmentScanLock = false;
                enrollmentPanel.hidden = true;
                if (lastEnrollmentNotice !== state) {
                    lastEnrollmentNotice = state;
                    setStatus('Phiên đăng ký đã được hủy.', 'idle');
                    result.textContent = '';
                    result.hidden = true;
                    hint.hidden = false;
                }
            } else if (state === 'FAILED') {
                enrollmentScanLock = false;
            }
        } catch (error) {
            updateEnrollmentRing({}, 'OFFLINE');
            if (error.message === 'AUTH_REQUIRED') {
                enrollmentPanel.hidden = true;
                if (!scanLocked) setStatus('PHIÊN ĐĂNG NHẬP ĐÃ HẾT HẠN', 'offline');
            }
        } finally {
            enrollmentBusy = false;
            window.clearTimeout(enrollmentTimer);
            enrollmentTimer = window.setTimeout(refreshEnrollmentStatus, 700);
        }
    };

    const schedulePreview = (delay = 180) => {
        window.clearTimeout(previewTimer);
        if (!previewEnabled || document.hidden || previewBusy) return;
        previewTimer = window.setTimeout(loadPreviewFrame, delay);
    };

    const loadPreviewFrame = async () => {
        if (!previewEnabled || document.hidden || previewBusy) return;
        previewBusy = true;
        previewRequest = new AbortController();
        try {
            const response = await fetch(`/?action=face_camera_frame&ts=${Date.now()}`, {
                credentials: 'same-origin', cache: 'no-store', signal: previewRequest.signal,
            });
            const contentType = response.headers.get('content-type') || '';
            if (!response.ok || !contentType.includes('image/jpeg')) {
                if (response.redirected) throw new Error('AUTH_REQUIRED');
                let message = '';
                if (contentType.includes('application/json')) {
                    try {
                        const payload = await response.json();
                        message = payload.message || '';
                    } catch {
                        // Use the local camera diagnostic below.
                    }
                }
                throw new Error(message || 'Không nhận được frame từ camera AI1 (app.py, cổng 5000).');
            }
            const blob = await response.blob();
            if (!previewEnabled) return;
            if (!blob.size) throw new Error('Camera trả về frame rỗng. Kiểm tra app.py và nguồn camera.');
            const nextUrl = URL.createObjectURL(blob);
            const previousUrl = previewObjectUrl;
            await new Promise((resolve) => {
                camera.onload = () => {
                    previewObjectUrl = nextUrl;
                    if (previousUrl) URL.revokeObjectURL(previousUrl);
                    cameraAvailable = true;
                    cameraWrap.style.setProperty('--frame-ratio', String(camera.naturalWidth / camera.naturalHeight));
                    camera.hidden = false;
                    resultFrame.hidden = true;
                    cameraEmpty.hidden = true;
                    hint.textContent = defaultHint;
                    if (!scanLocked && status.dataset.state === 'offline') {
                        setStatus('Vui lòng nhìn vào camera.', 'idle');
                    }
                    resolve();
                };
                camera.onerror = () => {
                    cameraAvailable = false;
                    URL.revokeObjectURL(nextUrl);
                    camera.hidden = true;
                    cameraEmpty.hidden = false;
                    cameraEmpty.textContent = 'Không thể giải mã hình từ camera. Kiểm tra nguồn camera và thử lại.';
                    hint.textContent = 'Chấm công tạm dừng vì camera chưa gửi được hình hợp lệ.';
                    hint.hidden = false;
                    if (!scanLocked) setStatus('CAMERA OFFLINE · FRAME KHÔNG HỢP LỆ', 'offline');
                    resolve();
                };
                camera.src = nextUrl;
            });
        } catch (error) {
            if (error.name !== 'AbortError' && previewEnabled) {
                cameraAvailable = false;
                camera.hidden = true;
                cameraEmpty.hidden = false;
                cameraEmpty.textContent = error.message === 'AUTH_REQUIRED'
                    ? 'Phiên quản trị đã hết hạn. Hãy đăng nhập lại.'
                    : error.message;
                hint.textContent = error.message === 'AUTH_REQUIRED'
                    ? 'Đăng nhập lại để tiếp tục chấm công.'
                    : 'Chấm công đang tạm dừng cho đến khi camera gửi được frame mới.';
                hint.hidden = false;
                if (!scanLocked) setStatus(error.message === 'AUTH_REQUIRED'
                    ? 'PHIÊN ĐĂNG NHẬP ĐÃ HẾT HẠN' : 'CAMERA OFFLINE · CỔNG 5000', 'offline');
            }
        } finally {
            previewBusy = false;
            previewRequest = null;
            schedulePreview(status.dataset.state === 'offline' ? 900 : 180);
        }
    };

    const startPreview = () => {
        if (!deviceReady || document.hidden) return;
        cameraAvailable = false;
        previewEnabled = true;
        camera.hidden = true;
        resultFrame.hidden = true;
        cameraEmpty.hidden = false;
        cameraEmpty.textContent = 'Đang kết nối nguồn camera AI1...';
        schedulePreview(0);
    };

    const stopPreview = () => {
        previewEnabled = false;
        window.clearTimeout(previewTimer);
        previewTimer = null;
        if (previewRequest) previewRequest.abort();
    };

    const drawBestFrame = (payload) => {
        if (!payload || typeof payload.best_frame_jpeg !== 'string') return;
        const image = new Image();
        image.onload = () => {
            const width = Number(payload.frame_width) || image.naturalWidth;
            const height = Number(payload.frame_height) || image.naturalHeight;
            resultFrame.width = width;
            resultFrame.height = height;
            resultFrame.style.width = '100%';
            resultFrame.style.height = '100%';
            resultFrame.getContext('2d').drawImage(image, 0, 0, width, height);
            if (Array.isArray(payload.bbox) && payload.bbox.length === 4) {
                const box = payload.bbox.map(Number);
                if (box.every(Number.isFinite) && box[2] > box[0] && box[3] > box[1]) {
                    const context = resultFrame.getContext('2d');
                    context.strokeStyle = '#27834a';
                    context.lineWidth = Math.max(2, width / 500);
                    context.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
                }
            }
            camera.hidden = true;
            resultFrame.hidden = false;
            cameraEmpty.hidden = true;
            cameraWrap.style.setProperty('--frame-ratio', String(width / height));
        };
        image.src = `data:image/jpeg;base64,${payload.best_frame_jpeg}`;
    };

    const finish = (state, title, details = '', recognitionResult = null) => {
        if (recognitionResult) drawBestFrame(recognitionResult);
        setStatus(title, state);
        result.textContent = details;
        result.hidden = !details;
        hint.hidden = true;
        scanLocked = true;
        stopPreview();
        window.clearTimeout(resetTimer);
        resetTimer = window.setTimeout(() => {
            camera.hidden = false;
            resultFrame.hidden = true;
            result.hidden = true;
            cameraEmpty.hidden = !deviceReady;
            if (deviceReady) {
                cameraEmpty.textContent = 'Đang kết nối camera...';
                setStatus('Vui lòng nhìn vào camera.', 'idle');
                hint.hidden = false;
                scanLocked = false;
                startPreview();
            }
        }, 4000);
    };

    const readJson = async (response) => {
        const contentType = response.headers.get('content-type') || '';
        if (response.redirected || !contentType.includes('application/json')) {
            throw new Error('AUTH_REQUIRED');
        }
        const payload = await response.json();
        if (!response.ok && response.status >= 500) throw new Error('OFFLINE');
        return payload;
    };

    const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

    const pollRecognition = async (sessionId) => {
        const deadline = Date.now() + 12000;
        while (Date.now() < deadline) {
            const response = await fetch(`/?action=face_recognition_status&session_id=${encodeURIComponent(sessionId)}`, {
                credentials: 'same-origin', cache: 'no-store',
            });
            const payload = await readJson(response);
            if (!response.ok || !payload.success) throw new Error('RECOGNITION_UNAVAILABLE');
            if (payload.state === 'COMPLETED' || payload.state === 'ABORTED') return payload;
            setStatus('Đang nhận diện...', 'processing');
            await wait(180);
        }
        throw new Error('RECOGNITION_TIMEOUT');
    };

    const recordAttendance = async (sessionId) => {
        const body = new URLSearchParams({
            _csrf_token: csrfToken,
            session_id: sessionId,
            device_id: deviceId,
        });
        const response = await fetch('/?action=kiosk_record_attendance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
            body,
            credentials: 'same-origin', cache: 'no-store',
        });
        return { response, payload: await readJson(response) };
    };

    const presentAttendance = (payload, recognitionResult) => {
        switch (payload.state) {
            case 'SUCCESS': {
                const isCheckin = payload.action === 'checkin';
                const title = isCheckin ? 'CHẤM CÔNG VÀO THÀNH CÔNG' : 'CHẤM CÔNG RA THÀNH CÔNG';
                const details = `${payload.employee_name || ''}\nMã nhân viên: ${payload.employee_id}\n${payload.time || ''}`;
                finish('success', title, details, recognitionResult);
                break;
            }
            case 'ALREADY_COMPLETED':
                finish('idle', 'Đã hoàn tất chấm công hôm nay.', '', recognitionResult);
                break;
            case 'UNKNOWN':
                finish('unknown', 'Không nhận diện được. Vui lòng thử lại.', '', recognitionResult);
                break;
            case 'OFFLINE':
                finish('offline', payload.code === 'CAMERA_SOURCE_UNAVAILABLE' ? 'CAMERA OFFLINE' : 'Không kết nối được máy chủ.', payload.message || '', recognitionResult);
                break;
            default:
                finish('error', 'CẦN QUÉT LẠI', payload.message || 'Chưa ghi được chấm công. Vui lòng thử lại.', recognitionResult);
        }
    };

    const presentRecognitionFailure = (recognition) => {
        const payload = recognition.result || {};
        if ((payload.reason || '') === 'UNKNOWN') {
            finish('unknown', 'Không nhận diện được. Vui lòng thử lại.', '');
            return;
        }
        const messages = {
            NO_FACE: 'Không thấy khuôn mặt. Hãy nhìn vào camera và thử lại.',
            MULTIPLE_FACES: 'Chỉ để một người trước camera rồi thử lại.',
            BLUR: 'Ảnh chưa rõ. Hãy đứng yên và thử lại.',
            STALE_FRAME: 'Camera chưa gửi được khung hình mới. Vui lòng thử lại.',
            CAMERA_TIMEOUT: 'Không nhận được hình từ camera. Vui lòng thử lại.',
            INCONSISTENT_FACES: 'Ba khung hình chưa nhất quán. Vui lòng thử lại.',
            MODEL_UNAVAILABLE: 'Dịch vụ nhận diện chưa sẵn sàng. Vui lòng báo quản lý.',
            GALLERY_UNAVAILABLE: 'Dữ liệu khuôn mặt chưa sẵn sàng. Vui lòng báo quản lý.',
        };
        finish('error', 'CẦN QUÉT LẠI', messages[payload.retry_reason] || 'Chưa nhận diện được ổn định. Vui lòng thử lại.');
    };

    const runScan = async () => {
        if (!deviceReady || scanLocked || enrollmentScanLock || document.hidden) return;
        if (!cameraAvailable) {
            cameraEmpty.hidden = false;
            cameraEmpty.textContent = 'Camera offline. Hãy chạy app.py và kiểm tra nguồn camera ở cổng 5000.';
            hint.hidden = false;
            hint.textContent = 'Chấm công đang tạm dừng cho đến khi có frame camera hợp lệ.';
            setStatus('CAMERA OFFLINE · CHƯA NHẬN ĐƯỢC FRAME', 'offline');
            return;
        }
        scanLocked = true;
        window.clearTimeout(resetTimer);
        stopPreview();
        camera.hidden = false;
        resultFrame.hidden = true;
        result.hidden = true;
        hint.hidden = true;
        setStatus('Đang nhận diện...', 'processing');
        cameraEmpty.hidden = true;

        try {
            const startResponse = await fetch('/?action=kiosk_recognition_start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
                body: new URLSearchParams({ _csrf_token: csrfToken }),
                credentials: 'same-origin', cache: 'no-store',
            });
            const start = await readJson(startResponse);
            if (!startResponse.ok || !start.success || !/^[a-f0-9]{32}$/.test(start.session_id || '')) {
                if (start.code === 'CAMERA_SOURCE_UNAVAILABLE') throw new Error('CAMERA_SOURCE_UNAVAILABLE');
                if (start.code === 'AI1_UNAVAILABLE' || start.code === 'AI1_MODEL_UNAVAILABLE') {
                    throw new Error('AI1_UNAVAILABLE');
                }
                if (startResponse.status >= 500) throw new Error('SERVER_OFFLINE');
                throw new Error(start.message || 'START_FAILED');
            }

            const recognition = await pollRecognition(start.session_id);
            const recognitionResult = recognition.result || {};
            if (recognition.state !== 'COMPLETED' || recognitionResult.recognized !== true) {
                presentRecognitionFailure(recognition);
                return;
            }

            // MATCH is provisional: keep a processing state until PHP confirms
            // check-in/check-out in the attendance service and database.
            drawBestFrame(recognitionResult);
            setStatus('Đang xác nhận chấm công...', 'processing');
            const { response, payload } = await recordAttendance(start.session_id);
            if (!response.ok && response.status >= 500) {
                presentAttendance({ state: 'OFFLINE', message: 'Không kết nối được máy chủ.' }, recognitionResult);
                return;
            }
            presentAttendance(payload, recognitionResult);
        } catch (error) {
            const authExpired = error.message === 'AUTH_REQUIRED';
            const cameraOffline = error.message === 'CAMERA_SOURCE_UNAVAILABLE';
            const aiOffline = error.message === 'AI1_UNAVAILABLE'
                || error.message === 'SERVER_OFFLINE' || error.message === 'RECOGNITION_UNAVAILABLE';
            const offline = cameraOffline || aiOffline;
            const title = authExpired ? 'PHIÊN ĐĂNG NHẬP ĐÃ HẾT HẠN'
                : cameraOffline ? 'CAMERA OFFLINE'
                    : aiOffline ? 'AI1 OFFLINE' : 'CẦN QUÉT LẠI';
            finish(authExpired || offline ? 'offline' : 'error', title,
                authExpired ? 'Đăng nhập lại để tiếp tục chấm công.'
                    : cameraOffline ? 'Không nhận được frame từ app.py tại 127.0.0.1:5000. Chấm công đã tạm dừng.'
                        : error.message === 'AI1_UNAVAILABLE'
                            ? 'Không kết nối được AI1 tại 127.0.0.1:5001. Hãy chạy python ai_service.py.'
                            : aiOffline ? 'Máy chủ AI1 chưa sẵn sàng. Kiểm tra ai_service.py và model buffalo_l.'
                    : (error.message === 'START_FAILED'
                        ? 'Không thể bắt đầu lượt quét. Vui lòng thử lại.'
                        : error.message));
        }
    };

    document.addEventListener('keydown', (event) => {
        if (event.code !== 'Space' && event.key !== ' ') return;
        if (event.repeat || spacePressed) return;
        if (event.target && (event.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(event.target.tagName || ''))) return;
        event.preventDefault();
        spacePressed = true;
        void runScan();
    });

    document.addEventListener('keyup', (event) => {
        if (event.code === 'Space' || event.key === ' ') spacePressed = false;
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopPreview();
            window.clearTimeout(enrollmentTimer);
        } else if (!scanLocked && deviceReady) {
            startPreview();
            void refreshEnrollmentStatus();
        }
    });
    window.addEventListener('pagehide', () => {
        stopPreview();
        window.clearTimeout(enrollmentTimer);
        enrollmentTimer = null;
    });

    updateClock();
    window.setInterval(updateClock, 1000);
    if (deviceReady) {
        startPreview();
        void refreshEnrollmentStatus();
    }
})();
