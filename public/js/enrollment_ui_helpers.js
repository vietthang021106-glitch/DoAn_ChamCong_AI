(function (root, factory) {
    const helpers = factory();
    if (typeof module === 'object' && module.exports) module.exports = helpers;
    root.AI1EnrollmentUI = helpers;
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    const POSES = ['frontal', 'left', 'right', 'up', 'down'];
    const POSE_ACTIONS = {
        frontal: 'Nhìn thẳng vào camera.',
        left: 'Quay sang trái một chút.',
        right: 'Quay sang phải một chút.',
        up: 'Ngẩng lên một chút.',
        down: 'Cúi xuống một chút.',
    };
    const QUALITY_MESSAGES = {
        'NO FACE': 'Không nhận thấy khuôn mặt. Hãy nhìn vào camera.',
        'MULTIPLE FACES': 'Vui lòng chỉ một người đứng trước camera.',
        'LOW DETECTION SCORE': 'Hãy nhìn rõ khuôn mặt vào camera.',
        'FACE TOO SMALL': 'Đến gần camera một chút.',
        'FACE TOO LARGE': 'Lùi ra xa camera một chút.',
        'FACE CROPPED': 'Lùi ra xa camera để thấy trọn khuôn mặt.',
        'FACE TOO CLOSE TO EDGE': 'Đưa khuôn mặt vào giữa khung hình.',
        'FACE POSITION': 'Đưa khuôn mặt vào giữa camera.',
        'BAD LIGHTING': 'Vui lòng điều chỉnh ánh sáng.',
        'TOO BLURRY': 'Ảnh chưa rõ. Hãy giữ đầu ổn định.',
        'INVALID EMBEDDING': 'Khuôn mặt chưa được ghi nhận ổn định. Vui lòng thử lại.',
        'POSE UNRELIABLE': 'Giữ đầu ổn định và nhìn rõ camera.',
        'SAME PERSON': 'Khuôn mặt chưa nhất quán. Vui lòng đứng một mình và thử lại.',
    };

    function integer(value, fallback = 0) {
        const number = Number(value);
        return Number.isFinite(number) ? Math.trunc(number) : fallback;
    }

    function guidanceFor(payload = {}) {
        const state = String(payload.state || '').toUpperCase();
        const expected = String(payload.expected_pose || '').toLowerCase();
        const detected = String(payload.detected_pose || payload.current_pose || '').toLowerCase();
        const code = String(payload.feedback_code || '').trim().toUpperCase();
        const qualityCode = String(payload.quality_code || '').trim().toUpperCase();
        const stableCount = Math.max(0, integer(payload.stable_frame_count));

        if (state === 'AWAITING_CONFIRMATION') {
            return 'Đã đủ năm góc. Chờ quản lý kiểm tra và xác nhận lưu.';
        }
        if (state === 'MANUAL_FALLBACK') {
            return 'Phiên tự động đã tạm dừng. Vui lòng báo quản lý để tiếp tục.';
        }
        if (state === 'OFFLINE') {
            return 'Không kết nối được camera hoặc máy chủ. Vui lòng báo quản lý.';
        }
        if (state === 'EXPIRED' || state === 'FAILED') {
            return 'Phiên đăng ký đã dừng. Vui lòng báo quản lý.';
        }

        if (QUALITY_MESSAGES[qualityCode]) return QUALITY_MESSAGES[qualityCode];
        if (QUALITY_MESSAGES[code]) return QUALITY_MESSAGES[code];
        if (code === 'NO_FRAME') {
            return 'Không nhận được hình ảnh mới từ camera. Vui lòng báo quản lý.';
        }
        if (code === 'STALE_FRAME') {
            return 'Đang chờ hình ảnh mới từ camera. Vui lòng giữ nguyên tư thế.';
        }
        if (code === 'LOW_FPS') {
            return 'Máy đang xử lý hình ảnh chậm. Vui lòng giữ tư thế tự nhiên.';
        }
        if (code === 'IDENTITY_MISMATCH') {
            return 'Khuôn mặt chưa nhất quán. Vui lòng chỉ một người trước camera và thử lại.';
        }
        if (code === 'POSE_UNRELIABLE' || code === 'POSE_NOT_READY') {
            return expected === 'frontal'
                ? 'Nhìn thẳng vào camera và giữ đầu ổn định.'
                : (POSE_ACTIONS[expected] || 'Giữ đầu ổn định và nhìn rõ camera.');
        }
        if (code === 'WRONG_POSE') {
            return POSE_ACTIONS[expected] || 'Hãy điều chỉnh khuôn mặt theo hướng dẫn.';
        }
        if ((detected === expected && stableCount > 0)
                || code === 'STABILIZING' || code === 'CAPTURE_PENDING') {
            return 'Giữ yên một chút.';
        }
        if (code === 'CAPTURE_READY' || code === 'CAPTURED') {
            return 'Đã ghi nhận khuôn mặt. Tiếp tục hướng tiếp theo.';
        }

        // Pose labels are already the calibrated user-facing directions from AI1.
        // If the estimate cannot distinguish under-turn from over-turn, guide
        // toward the requested direction without claiming that the user went too far.
        return POSE_ACTIONS[expected] || 'Hãy nhìn vào camera.';
    }

    function buildRingModel(payload = {}) {
        const width = integer(payload.frame_width);
        const height = integer(payload.frame_height);
        const bbox = payload.face_bbox;
        if (width <= 0 || height <= 0 || !Array.isArray(bbox) || bbox.length !== 4) {
            return { visible: false, segments: [] };
        }

        const box = bbox.map(Number);
        if (!box.every(Number.isFinite)) return { visible: false, segments: [] };
        const x1 = Math.max(0, Math.min(width, box[0]));
        const y1 = Math.max(0, Math.min(height, box[1]));
        const x2 = Math.max(0, Math.min(width, box[2]));
        const y2 = Math.max(0, Math.min(height, box[3]));
        const faceWidth = x2 - x1;
        const faceHeight = y2 - y1;
        if (faceWidth <= 1 || faceHeight <= 1) return { visible: false, segments: [] };

        const captured = Math.max(0, Math.min(POSES.length, integer(payload.captured)));
        const stableRequired = Math.max(1, integer(payload.stable_frames_required, 5));
        const stableCount = Math.max(0, Math.min(stableRequired, integer(payload.stable_frame_count)));
        const activeIndex = captured < POSES.length ? captured : -1;
        const activeExtent = stableCount > 0 ? 58 * stableCount / stableRequired : 8;

        return {
            visible: true,
            width,
            height,
            centerX: (x1 + x2) / 2,
            centerY: (y1 + y2) / 2,
            radiusX: Math.max(28, faceWidth * 0.68),
            radiusY: Math.max(32, faceHeight * 0.66),
            strokeWidth: Math.max(3, Math.min(8, Math.min(faceWidth, faceHeight) * 0.018)),
            activeIndex,
            stableCount,
            stableRequired,
            segments: POSES.map((_pose, index) => ({
                pose: POSES[index],
                start: -90 + index * 72,
                trackExtent: 58,
                extent: index < captured ? 58 : (index === activeIndex ? activeExtent : 0),
                state: index < captured ? 'complete' : (index === activeIndex ? 'active' : 'upcoming'),
            })),
        };
    }

    function arcPath(centerX, centerY, radiusX, radiusY, startDegrees, extentDegrees) {
        const extent = Math.max(0, Math.min(359.99, Number(extentDegrees) || 0));
        if (extent <= 0) return '';
        const start = Number(startDegrees) * Math.PI / 180;
        const end = (Number(startDegrees) + extent) * Math.PI / 180;
        const x1 = centerX + radiusX * Math.cos(start);
        const y1 = centerY + radiusY * Math.sin(start);
        const x2 = centerX + radiusX * Math.cos(end);
        const y2 = centerY + radiusY * Math.sin(end);
        const largeArc = extent > 180 ? 1 : 0;
        return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${radiusX.toFixed(2)} ${radiusY.toFixed(2)} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
    }

    function thumbnailIndexesToLoad(previous, current, mode, complete) {
        const count = Math.max(0, Math.min(POSES.length, integer(current)));
        if (complete) return Array.from({ length: count }, (_value, index) => index);
        if (String(mode).toUpperCase() === 'MANUAL' && count === integer(previous) + 1) {
            return [count - 1];
        }
        return [];
    }

    return { POSES, guidanceFor, buildRingModel, arcPath, thumbnailIndexesToLoad };
});
