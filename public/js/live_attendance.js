(() => {
    const root = document.querySelector('[data-live-attendance]');
    if (!root) return;

    const camera = root.querySelector('[data-live-camera]');
    const cameraStatus = root.querySelector('[data-live-camera-status]');
    const feedStatus = root.querySelector('[data-live-feed-status]');
    const rows = root.querySelector('[data-live-attendance-rows]');

    const addCell = (row, value) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.append(cell);
        return cell;
    };

    const renderRows = (items) => {
        rows.replaceChildren();
        if (!Array.isArray(items) || items.length === 0) {
            const row = document.createElement('tr');
            const cell = addCell(row, 'Chưa có lượt chấm công.');
            cell.colSpan = 5;
            cell.className = 'live-monitor-empty';
            rows.append(row);
            return;
        }

        items.forEach((item) => {
            const row = document.createElement('tr');
            const id = Number.parseInt(item.MaNV, 10);
            addCell(row, Number.isFinite(id) ? `NV${String(id).padStart(3, '0')}` : '—');
            addCell(row, String(item.HoTen ?? ''));

            const eventCell = document.createElement('td');
            const tag = document.createElement('span');
            const isOut = item.PunchType === 'OUT';
            tag.className = `live-punch-tag ${isOut ? 'live-punch-tag--out' : 'live-punch-tag--in'}`;
            tag.textContent = isOut ? 'Check-out' : 'Check-in';
            eventCell.append(tag);
            row.append(eventCell);

            addCell(row, String(item.TenCa ?? '—'));
            addCell(row, String(item.EventTime ?? '—'));
            rows.append(row);
        });
    };

    let isRunning = false;
    let sessionExpired = false;
    let lifecycle = 0;
    let feedTimer = null;
    let cameraTimer = null;
    let redirectTimer = null;
    let feedController = null;
    let cameraController = null;
    let cameraObjectUrl = null;

    const clearTimer = (timer) => {
        if (timer !== null) window.clearTimeout(timer);
    };

    const stopPolling = () => {
        isRunning = false;
        lifecycle += 1;
        clearTimer(feedTimer);
        clearTimer(cameraTimer);
        feedTimer = null;
        cameraTimer = null;

        feedController?.abort();
        cameraController?.abort();
    };

    const handleExpiredSession = () => {
        if (sessionExpired) return;
        sessionExpired = true;
        stopPolling();
        feedStatus.textContent = 'Phiên Admin đã hết hạn. Đang chuyển đến đăng nhập…';
        redirectTimer = window.setTimeout(() => {
            window.location.assign('/?action=login');
        }, 800);
    };

    const isAuthenticationResponse = (response) => response.status === 401
        || response.status === 403
        || response.redirected
        || (typeof response.url === 'string' && response.url.includes('action=login'));

    const scheduleFeed = (delay = 3000) => {
        clearTimer(feedTimer);
        if (!isRunning || document.hidden || sessionExpired) return;
        feedTimer = window.setTimeout(() => {
            feedTimer = null;
            refreshFeed();
        }, delay);
    };

    const scheduleCamera = (delay = 1200) => {
        clearTimer(cameraTimer);
        if (!isRunning || document.hidden || sessionExpired) return;
        cameraTimer = window.setTimeout(() => {
            cameraTimer = null;
            refreshCamera();
        }, delay);
    };

    const refreshFeed = async () => {
        if (!isRunning || document.hidden || sessionExpired || feedController !== null) return;
        const controller = new AbortController();
        const requestLifecycle = lifecycle;
        feedController = controller;
        try {
            const response = await fetch(`/?action=live_attendance_feed&_=${Date.now()}`, {
                credentials: 'same-origin',
                cache: 'no-store',
                headers: { Accept: 'application/json' },
                signal: controller.signal,
            });
            if (feedController !== controller || !isRunning || requestLifecycle !== lifecycle) return;
            if (isAuthenticationResponse(response)) {
                handleExpiredSession();
                return;
            }
            if (!response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
                throw new Error('Unexpected feed response.');
            }
            const payload = await response.json();
            if (feedController !== controller || !isRunning || requestLifecycle !== lifecycle) return;
            if (!response.ok || payload.success !== true) {
                throw new Error('Feed unavailable.');
            }
            renderRows(payload.recent);
            feedStatus.textContent = `Cập nhật lúc ${payload.server_time}`;
        } catch (error) {
            if (error.name !== 'AbortError' && feedController === controller && isRunning && requestLifecycle === lifecycle) {
                feedStatus.textContent = 'Không thể cập nhật lượt chấm công. Đang thử lại…';
            }
        } finally {
            if (feedController === controller) {
                feedController = null;
                if (isRunning && !document.hidden && !sessionExpired) {
                    if (requestLifecycle === lifecycle) scheduleFeed();
                    else refreshFeed();
                }
            }
        }
    };

    const refreshCamera = async () => {
        if (!isRunning || document.hidden || sessionExpired || cameraController !== null) return;
        const controller = new AbortController();
        const requestLifecycle = lifecycle;
        cameraController = controller;
        let nextObjectUrl = null;
        try {
            const response = await fetch(`/?action=face_camera_frame&_=${Date.now()}`, {
                credentials: 'same-origin',
                cache: 'no-store',
                signal: controller.signal,
            });
            if (cameraController !== controller || !isRunning || requestLifecycle !== lifecycle) return;
            if (isAuthenticationResponse(response)) {
                handleExpiredSession();
                return;
            }
            if (!response.ok || !response.headers.get('content-type')?.toLowerCase().includes('image/')) {
                throw new Error('Camera unavailable.');
            }
            const image = await response.blob();
            if (cameraController !== controller || !isRunning || requestLifecycle !== lifecycle) return;

            nextObjectUrl = URL.createObjectURL(image);
            camera.src = nextObjectUrl;
            if (typeof camera.decode === 'function') await camera.decode();
            if (cameraController !== controller || !isRunning || requestLifecycle !== lifecycle) {
                URL.revokeObjectURL(nextObjectUrl);
                nextObjectUrl = null;
                return;
            }
            if (cameraObjectUrl !== null) URL.revokeObjectURL(cameraObjectUrl);
            cameraObjectUrl = nextObjectUrl;
            nextObjectUrl = null;
            cameraStatus.textContent = 'Đang nhận hình';
        } catch (error) {
            if (nextObjectUrl !== null) URL.revokeObjectURL(nextObjectUrl);
            if (error.name !== 'AbortError' && cameraController === controller && isRunning && requestLifecycle === lifecycle) {
                cameraStatus.textContent = 'Camera chưa sẵn sàng';
            }
        } finally {
            if (cameraController === controller) {
                cameraController = null;
                if (isRunning && !document.hidden && !sessionExpired) {
                    if (requestLifecycle === lifecycle) {
                        scheduleCamera(cameraStatus.textContent === 'Đang nhận hình' ? 1200 : 2500);
                    } else {
                        refreshCamera();
                    }
                }
            }
        }
    };

    const startPolling = () => {
        if (isRunning || document.hidden || sessionExpired) return;
        isRunning = true;
        lifecycle += 1;
        refreshFeed();
        refreshCamera();
    };

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) stopPolling();
        else startPolling();
    });
    window.addEventListener('pagehide', () => {
        stopPolling();
        if (cameraObjectUrl !== null) {
            URL.revokeObjectURL(cameraObjectUrl);
            cameraObjectUrl = null;
        }
    });
    window.addEventListener('pageshow', startPolling);

    startPolling();
})();
