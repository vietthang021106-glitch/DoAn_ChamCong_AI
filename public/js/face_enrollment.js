(() => {
    const root = document.querySelector('[data-face-enrollment]');
    if (!root) return;

    const employeeId = root.dataset.employeeId;
    const csrfToken = root.dataset.csrf;
    const sampleCount = Number(root.dataset.faceCount || 0);
    const section = root.closest('.face-management');
    const startButton = section.querySelector('[data-face-start]');
    const deleteButton = section.querySelector('[data-face-delete]');
    const deviceSelect = section.querySelector('[data-face-device]');
    const modeSelect = section.querySelector('[data-face-mode]');
    const cancelButton = root.querySelector('[data-face-cancel]');
    const completeButton = root.querySelector('[data-face-complete]');
    const captureButton = root.querySelector('[data-face-capture]');
    const manualFallbackButton = root.querySelector('[data-face-manual-fallback]');
    const terminalLink = root.querySelector('[data-face-terminal-link]');
    const camera = root.querySelector('[data-face-camera]');
    const cameraEmpty = root.querySelector('[data-face-camera-empty]');
    const stepLabel = root.querySelector('[data-face-step]');
    const feedback = root.querySelector('[data-face-feedback]');
    const poseList = root.querySelector('[data-face-pose-list]');
    const guide = root.querySelector('[data-face-guide]');
    const thumbnails = [...root.querySelectorAll('[data-pose-thumb]')];
    const enrollmentUi = window.AI1EnrollmentUI;
    const result = section.querySelector('[data-face-result]');
    const poses = [
        { key: 'frontal', label: 'Chính diện' },
        { key: 'left', label: 'Nghiêng trái' },
        { key: 'right', label: 'Nghiêng phải' },
        { key: 'up', label: 'Ngẩng nhẹ' },
        { key: 'down', label: 'Cúi nhẹ' },
    ];
    const poseName = (key) => poses.find((pose) => pose.key === key)?.label || ({
        no_face: 'Không có khuôn mặt',
        multiple_faces: 'Có nhiều khuôn mặt',
        unknown: 'Chưa xác định',
        between: 'Chưa đúng hướng',
    }[key] || key || 'Chưa xác định');

    let captured = 0;
    let running = false;
    let busy = false;
    let poseTimer = null;
    let frameTimer = null;
    let activeMode = 'AUTO';
    let duplicateCheckStatus = null;

    const post = async (action, values = {}) => {
        const body = new URLSearchParams({ _csrf_token: csrfToken, ...values });
        const response = await fetch(`/?action=${action}&id=${encodeURIComponent(employeeId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
            body,
            credentials: 'same-origin',
            cache: 'no-store',
        });
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new Error('Phản hồi từ máy chủ không hợp lệ.');
        }
        if (!response.ok && !payload.message) {
            throw new Error('Không thể hoàn tất yêu cầu.');
        }
        return { response, payload };
    };

    const showResult = (message, kind = 'info') => {
        result.textContent = message;
        result.className = `notice face-enrollment-result notice--${kind}`;
        result.hidden = false;
    };

    const duplicateUnavailableReason = (reason) => ({
        THRESHOLD_NOT_CALIBRATED: 'chưa có ngưỡng chống trùng được hiệu chỉnh.',
        INCOMPLETE_GALLERY: 'gallery của nhân viên khác không có đúng 5 mẫu chuẩn để đối chiếu.',
        GALLERY_UNAVAILABLE: 'không đọc được gallery hiện tại.',
        GALLERY_ENROLLMENT_LOCK_UNAVAILABLE: 'không khóa được gallery trong lúc lưu.',
        INVALID_OR_UNREADABLE_EMBEDDING: 'có embedding không hợp lệ trong gallery.',
    }[reason] || '');

    const renderDuplicateCheck = (check) => {
        duplicateCheckStatus = check?.status || 'CHECK_UNAVAILABLE';
        completeButton.disabled = duplicateCheckStatus !== 'CLEAR';

        if (duplicateCheckStatus === 'CLEAR') {
            guide.dataset.state = 'ready';
            feedback.textContent = 'Kiểm tra trùng: CLEAR · chưa phát hiện bằng chứng trùng. Có thể lưu 5 mẫu.';
            return;
        }

        if (duplicateCheckStatus === 'SUSPECTED_DUPLICATE') {
            const candidateId = Number(check.candidate_id);
            const employeeCode = Number.isInteger(candidateId) && candidateId > 0
                ? 'NV' + String(candidateId).padStart(3, '0')
                : 'nhân viên khác';
            const candidateName = check.candidate_name ? ' · ' + check.candidate_name : '';
            guide.dataset.state = 'fail';
            feedback.textContent = 'Phát hiện khuôn mặt có khả năng trùng với nhân viên '
                + employeeCode + candidateName + '. Vui lòng kiểm tra trước khi đăng ký; lưu đang bị chặn.';
            return;
        }

        const detail = duplicateUnavailableReason(check?.reason);
        guide.dataset.state = 'fail';
        feedback.textContent = 'Chưa thể kiểm tra trùng khuôn mặt. Vui lòng thử lại.'
            + (detail ? ' Nguyên nhân: ' + detail : '') + ' Lưu đang bị chặn.';
    };

    const renderStep = () => {
        const step = poses[captured];
        stepLabel.textContent = step
            ? `Bước ${captured + 1}/5 · ${step.label}`
            : 'Đã hoàn tất 5/5 góc';
        [...poseList.children].forEach((item, index) => {
            item.classList.toggle('is-complete', index < captured);
            item.classList.toggle('is-active', index === captured && captured < poses.length);
        });
        thumbnails.forEach((figure, index) => {
            const image = figure.querySelector('img');
            figure.classList.toggle('is-complete', index < captured);
            if (index >= captured) image.removeAttribute('src');
        });
    };

    const showCapturedThumbnail = (index) => {
        const figure = thumbnails[index];
        const image = figure?.querySelector('img');
        if (!image) return;
        image.src = `/?action=face_enrollment_preview&id=${encodeURIComponent(employeeId)}&index=${index}&ts=${Date.now()}`;
        figure.classList.add('is-complete');
    };

    const showCapturedThumbnails = (previous, current, complete = false) => {
        const indexes = enrollmentUi
            ? enrollmentUi.thumbnailIndexesToLoad(previous, current, activeMode, complete)
            : (complete ? Array.from({ length: Math.max(0, Math.min(5, current)) }, (_value, index) => index) : []);
        indexes.forEach(showCapturedThumbnail);
    };

    const setCamera = (enabled) => {
        camera.hidden = !enabled;
        cameraEmpty.hidden = enabled;
        if (!enabled) {
            camera.removeAttribute('src');
            clearInterval(frameTimer);
            frameTimer = null;
            return;
        }
        const refreshFrame = () => {
            camera.src = `/?action=face_camera_frame&ts=${Date.now()}`;
        };
        refreshFrame();
        clearInterval(frameTimer);
        frameTimer = setInterval(refreshFrame, 400);
    };

    const stopPosePolling = () => {
        clearInterval(poseTimer);
        poseTimer = null;
        running = false;
    };

    camera.addEventListener('error', () => {
        camera.hidden = true;
        cameraEmpty.hidden = false;
        cameraEmpty.textContent = 'Không kết nối được camera relay. Kiểm tra camera singleton và thử lại.';
    });

    camera.addEventListener('load', () => {
        if (camera.naturalWidth > 0) {
            camera.hidden = false;
            cameraEmpty.hidden = true;
        }
    });

    const inspectPose = async () => {
        if (!running || busy) return;
        busy = true;
        try {
            const { response, payload } = await post('face_enrollment_pose');
            if (!response.ok || !payload.success) {
                guide.dataset.state = 'fail';
                const stable = Number(payload.stable_frame_count || 0);
                const required = Number(payload.stable_frames_required || (activeMode === 'AUTO' ? 5 : 8));
                const detected = poseName(payload.current_pose);
                const quality = payload.quality_ok === false ? 'Quality: FAIL' : 'Quality: kiểm tra';
                feedback.textContent = `${payload.state || 'Chưa sẵn sàng'} · pose cần ${poses[captured]?.label || '—'} · phát hiện ${detected} · ${quality} · ${payload.reason || payload.message || 'Không đọc được trạng thái AI1.'}`;
                return;
            }
            const newCaptured = Number(payload.captured ?? captured);
            if (newCaptured !== captured) {
                const previous = captured;
                captured = newCaptured;
                renderStep();
                showCapturedThumbnails(previous, newCaptured, false);
            }

            if (payload.state === 'MANUAL_FALLBACK') {
                stopPosePolling();
                guide.dataset.state = 'fail';
                captureButton.hidden = true;
                manualFallbackButton.hidden = false;
                completeButton.hidden = true;
                feedback.textContent = `${payload.reason || 'AUTO tạm dừng.'} Bạn có thể tiếp tục bằng MANUAL.`;
                return;
            }

            if (payload.complete || payload.state === 'AWAITING_CONFIRMATION' || captured >= poses.length) {
                // AUTO samples are copied from the AI worker into the PHP session
                // only after all five have passed validation. Reload every indexed
                // image now that hydrateAutoSamples() has completed.
                showCapturedThumbnails(captured, captured, true);
                stopPosePolling();
                guide.dataset.state = 'ready';
                captureButton.hidden = true;
                manualFallbackButton.hidden = true;
                completeButton.hidden = false;
                cancelButton.hidden = false;
                renderDuplicateCheck(payload.duplicate_check);
                return;
            }

            if (payload.auto_captured) {
                guide.dataset.state = 'ready';
                feedback.textContent = `${payload.instruction || 'Đã tự động chụp.'} Bước ${captured + 1}/5 · ${poses[captured].label}`;
                return;
            }

            const stable = Number(payload.stable_frame_count || 0);
            const required = Number(payload.stable_frames_required || (activeMode === 'AUTO' ? 5 : 8));
            const instruction = payload.instruction || 'Đang kiểm tra hướng khuôn mặt.';
            const expected = poses[captured]?.label || 'Hoàn tất 5 góc';
            const detected = poseName(payload.current_pose);
            const quality = activeMode === 'MANUAL'
                ? (payload.ready ? 'Quality: GOOD' : 'Quality: chưa đạt')
                : (Number.isFinite(Number(payload.inference_fps))
                    ? `AI1 AUTO · ${Number(payload.inference_fps).toFixed(1)} FPS` : 'AI1 AUTO');
            guide.dataset.state = payload.ready ? 'ready' : 'adjust';
            if (activeMode === 'MANUAL') {
                captureButton.hidden = !(payload.ready && stable >= required);
                feedback.textContent = `${payload.ready ? 'Sẵn sàng chụp' : 'Chưa sẵn sàng'} · cần ${expected} · phát hiện ${detected} · ${quality} · ${instruction} · ổn định ${stable}/${required}`;
            } else {
                captureButton.hidden = true;
                feedback.textContent = `${expected} · ${quality} · ${instruction || 'Đang thu mẫu tự động.'} · mẫu ${captured}/5`;
            }
        } catch (error) {
            guide.dataset.state = 'fail';
            feedback.textContent = `Chưa sẵn sàng · ${error.message}`;
        } finally {
            busy = false;
        }
    };

    const beginEnrollment = async (mode, terminalWindow = null) => {
        activeMode = mode;
        const deviceId = root.dataset.deviceId || deviceSelect?.value || '';
        const { response, payload } = await post('face_enrollment_start', {
            mode,
            device_id: deviceId,
        });
        if (!response.ok || !payload.success) throw new Error(payload.message || 'Không thể bắt đầu đăng ký.');
        terminalLink.href = `/?action=man-hinh-cham-cong&device_id=${encodeURIComponent(deviceId)}`;
        terminalLink.hidden = false;
        if (terminalWindow && !terminalWindow.closed) {
            terminalWindow.location = terminalLink.href;
        }
        captured = 0;
        duplicateCheckStatus = null;
        renderStep();
        guide.dataset.state = 'adjust';
        root.hidden = false;
        result.hidden = true;
        setCamera(mode === 'MANUAL');
        cancelButton.hidden = false;
        captureButton.hidden = true;
        manualFallbackButton.hidden = true;
        completeButton.hidden = true;
        completeButton.disabled = true;
        feedback.textContent = mode === 'AUTO'
            ? 'Màn hình chấm công sẽ hiển thị phiên này. AI1 tự thu năm hướng; không cần nhấn phím.'
            : 'Chọn đúng từng hướng. Khi đủ quality và ổn định 8 frame, nhấn “Chụp pose hiện tại”.';
        running = true;
        poseTimer = setInterval(inspectPose, mode === 'AUTO' ? 350 : 150);
    };

    startButton.addEventListener('click', async () => {
        if (sampleCount > 0 && !window.confirm('Mẫu khuôn mặt cũ sẽ được giữ nguyên cho đến khi đủ 5 mẫu mới và lưu thành công. Bắt đầu đăng ký lại?')) {
            return;
        }
        startButton.disabled = true;
        const selectedMode = modeSelect?.value || 'AUTO';
        const terminalWindow = window.open('about:blank', `attendance-terminal-${root.dataset.deviceId || 'device'}`);
        try {
            await beginEnrollment(selectedMode, terminalWindow);
        } catch (error) {
            if (terminalWindow && !terminalWindow.closed) terminalWindow.close();
            showResult(error.message, 'error');
        } finally {
            startButton.disabled = false;
        }
    });

    captureButton.addEventListener('click', async () => {
        if (activeMode !== 'MANUAL' || busy || !running) return;
        captureButton.disabled = true;
        try {
            const { response, payload } = await post('face_enrollment_capture');
            if (!response.ok || !payload.success) throw new Error(payload.reason || payload.message || 'Không thể chụp pose.');
            const previous = captured;
            captured = Number(payload.captured ?? captured);
            renderStep();
            showCapturedThumbnails(previous, captured, Boolean(payload.complete));
            captureButton.hidden = true;
            if (payload.complete || captured >= poses.length) {
                stopPosePolling();
                completeButton.hidden = false;
                renderDuplicateCheck(payload.duplicate_check);
            } else {
                feedback.textContent = `Đã chụp ${captured}/5 · Pose tiếp theo: ${poses[captured].label}`;
            }
        } catch (error) {
            feedback.textContent = error.message;
        } finally {
            captureButton.disabled = false;
        }
    });

    manualFallbackButton.addEventListener('click', async () => {
        manualFallbackButton.disabled = true;
        try {
            await post('face_enrollment_cancel');
            modeSelect.value = 'MANUAL';
            await beginEnrollment('MANUAL');
        } catch (error) {
            showResult(error.message, 'error');
        } finally {
            manualFallbackButton.disabled = false;
        }
    });

    completeButton.addEventListener('click', async () => {
        completeButton.disabled = true;
        try {
            const { response, payload } = await post('face_enrollment_complete');
            if (!response.ok || !payload.success) {
                if (payload.duplicate_check) renderDuplicateCheck(payload.duplicate_check);
                const error = new Error(payload.message || 'Không thể lưu batch.');
                error.duplicateCheck = payload.duplicate_check;
                throw error;
            }
            showResult(payload.gallery_updated
                ? 'Đã lưu 5 mẫu khuôn mặt và làm mới gallery AI.'
                : 'Đã lưu 5 mẫu, nhưng gallery AI1 chưa đồng bộ. Nhận diện sẽ tạm dừng cho đến khi đồng bộ thành công.',
                payload.gallery_updated ? 'success' : 'warning');
            setTimeout(() => window.location.reload(), 900);
        } catch (error) {
            if (error.duplicateCheck) {
                renderDuplicateCheck(error.duplicateCheck);
            } else {
                completeButton.disabled = duplicateCheckStatus !== 'CLEAR';
            }
            showResult(error.message, 'error');
        }
    });

    cancelButton.addEventListener('click', async () => {
        stopPosePolling();
        try {
            await post('face_enrollment_cancel');
        } catch {
            // The PHP session expires automatically if cancellation cannot reach the server.
        }
        root.hidden = true;
        setCamera(false);
        guide.dataset.state = 'adjust';
        thumbnails.forEach((figure) => figure.querySelector('img')?.removeAttribute('src'));
        thumbnails.forEach((figure) => figure.classList.remove('is-complete'));
        showResult('Đã hủy phiên. Chưa có mẫu nào được lưu.', 'info');
    });

    if (deleteButton) {
        deleteButton.addEventListener('click', async () => {
            if (!window.confirm('Xóa toàn bộ mẫu khuôn mặt của nhân viên này? Hồ sơ, tài khoản và lịch sử chấm công sẽ được giữ nguyên.')) return;
            deleteButton.disabled = true;
            try {
                const { response, payload } = await post('face_registration_delete');
                if (!response.ok || !payload.success) throw new Error(payload.message || 'Không thể xóa đăng ký.');
                showResult('Đã xóa toàn bộ mẫu khuôn mặt.', 'success');
                setTimeout(() => window.location.reload(), 700);
            } catch (error) {
                deleteButton.disabled = false;
                showResult(error.message, 'error');
            }
        });
    }

    const dialog = document.querySelector('[data-face-lightbox]');
    const dialogImage = dialog.querySelector('[data-face-lightbox-image]');
    const dialogTitle = dialog.querySelector('[data-face-lightbox-title]');
    section.querySelectorAll('[data-face-preview]').forEach((button) => {
        button.addEventListener('click', () => {
            dialogImage.src = button.dataset.facePreview;
            dialogTitle.textContent = button.getAttribute('aria-label') || 'Ảnh mẫu khuôn mặt';
            dialog.showModal();
        });
    });
    dialog.querySelector('[data-face-lightbox-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
        dialogImage.removeAttribute('src');
    });
})();
