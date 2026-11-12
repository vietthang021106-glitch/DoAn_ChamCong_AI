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

    let feedTimer = null;
    let feedInFlight = false;
    const refreshFeed = async () => {
        if (feedInFlight) return;
        feedInFlight = true;
        if (document.hidden) {
            feedInFlight = false;
            feedTimer = window.setTimeout(refreshFeed, 3000);
            return;
        }
        try {
            const response = await fetch(`/?action=live_attendance_feed&_=${Date.now()}`, {
                credentials: 'same-origin',
                cache: 'no-store',
                headers: { Accept: 'application/json' },
            });
            const payload = await response.json();
            if (!response.ok || payload.success !== true) {
                throw new Error(payload.message || 'Không thể cập nhật dữ liệu.');
            }
            renderRows(payload.recent);
            feedStatus.textContent = `Cập nhật lúc ${payload.server_time}`;
        } catch (error) {
            feedStatus.textContent = error.message || 'Không thể cập nhật dữ liệu chấm công.';
        } finally {
            feedInFlight = false;
            feedTimer = window.setTimeout(refreshFeed, 3000);
        }
    };

    let cameraTimer = null;
    const refreshCamera = () => {
        if (document.hidden) {
            cameraTimer = window.setTimeout(refreshCamera, 1200);
            return;
        }
        camera.onload = () => {
            cameraStatus.textContent = 'Đang nhận hình';
            cameraTimer = window.setTimeout(refreshCamera, 1200);
        };
        camera.onerror = () => {
            cameraStatus.textContent = 'Camera chưa sẵn sàng';
            cameraTimer = window.setTimeout(refreshCamera, 2500);
        };
        camera.src = `/?action=face_camera_frame&_=${Date.now()}`;
    };

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            if (cameraTimer !== null) window.clearTimeout(cameraTimer);
            if (feedTimer !== null) window.clearTimeout(feedTimer);
            refreshCamera();
            refreshFeed();
        }
    });

    refreshCamera();
    refreshFeed();
})();
