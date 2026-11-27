'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const enrollmentUi = require('../public/js/enrollment_ui_helpers.js');

test('browser helper is available on the global while remaining importable by Node', () => {
    assert.equal(globalThis.AI1EnrollmentUI, enrollmentUi);
    const browserWindow = {};
    vm.runInNewContext(fs.readFileSync(require.resolve('../public/js/enrollment_ui_helpers.js'), 'utf8'), {
        window: browserWindow,
    });
    assert.equal(typeof browserWindow.AI1EnrollmentUI.guidanceFor, 'function');
});

test('scanning ring follows the face box and uses AI stability counts', () => {
    const model = enrollmentUi.buildRingModel({
        primary_face_safe: true,
        captured: 2,
        stable_frame_count: 2,
        stable_frames_required: 5,
        face_bbox: [100, 80, 220, 240],
        frame_width: 640,
        frame_height: 480,
    });

    assert.equal(model.visible, true);
    assert.equal(model.centerX, 160);
    assert.equal(model.centerY, 160);
    assert.equal(model.activeIndex, 2);
    assert.equal(model.segments[0].state, 'complete');
    assert.equal(model.segments[1].state, 'complete');
    assert.equal(model.segments[2].state, 'active');
    assert.equal(model.segments[2].extent, 23.2);
    assert.equal(model.segments[3].extent, 0);
});

test('ring hides without current face geometry and completes only from captured samples', () => {
    assert.equal(enrollmentUi.buildRingModel({ captured: 1 }).visible, false);
    assert.equal(enrollmentUi.buildRingModel({
        primary_face_safe: false,
        face_bbox: [100, 80, 220, 240], frame_width: 640, frame_height: 480,
    }).visible, false);
    const complete = enrollmentUi.buildRingModel({
        primary_face_safe: true,
        captured: 5,
        stable_frame_count: 0,
        stable_frames_required: 5,
        face_bbox: [200, 100, 360, 340],
        frame_width: 640,
        frame_height: 480,
    });
    assert.equal(complete.activeIndex, -1);
    assert.deepEqual(complete.segments.map((segment) => segment.extent), [58, 58, 58, 58, 58]);
});

test('safe primary with failed quality gets only a neutral outline and no false stability progress', () => {
    const model = enrollmentUi.buildRingModel({
        primary_face_safe: true,
        quality_code: 'FACE TOO SMALL',
        observation_status: 'QUALITY_REJECTED',
        feedback_code: 'FACE TOO SMALL',
        captured: 1,
        stable_frame_count: 4,
        stable_frames_required: 5,
        face_bbox: [100, 80, 220, 240],
        frame_width: 640,
        frame_height: 480,
    });
    assert.equal(model.visible, true);
    assert.equal(model.stableCount, 0);
    assert.equal(model.segments[1].extent, 0);
    assert.equal(model.segments[0].state, 'complete');
});

test('wrong pose does not display stability progress from a previously valid window', () => {
    const model = enrollmentUi.buildRingModel({
        primary_face_safe: true,
        quality_code: 'PASS',
        observation_status: 'WRONG_POSE',
        feedback_code: 'WRONG_POSE',
        stable_frame_count: 4,
        stable_frames_required: 5,
        face_bbox: [100, 80, 220, 240],
        frame_width: 640,
        frame_height: 480,
    });
    assert.equal(model.stableCount, 0);
    assert.equal(model.segments[0].extent, 0);
});

test('mirrored preview maps the detected box to matching SVG coordinates only', () => {
    const payload = {
        captured: 0,
        primary_face_safe: true,
        stable_frame_count: 0,
        stable_frames_required: 5,
        face_bbox: [100, 80, 220, 240],
        frame_width: 640,
        frame_height: 480,
    };
    const sourceCoordinates = enrollmentUi.buildRingModel(payload);
    const mirroredCoordinates = enrollmentUi.buildRingModel(payload, { mirrorX: true });
    assert.equal(sourceCoordinates.centerX, 160);
    assert.equal(mirroredCoordinates.centerX, 480);
    assert.equal(mirroredCoordinates.centerY, sourceCoordinates.centerY);
    assert.deepEqual(payload.face_bbox, [100, 80, 220, 240]);
});

test('employee guidance is Vietnamese, actionable and omits pose diagnostics', () => {
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', expected_pose: 'left', detected_pose: 'right', feedback_code: 'WRONG_POSE',
    }), 'Quay sang trái một chút.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', expected_pose: 'up', detected_pose: 'up', stable_frame_count: 2,
    }), 'Giữ yên một chút.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', expected_pose: 'down', detected_pose: 'up', feedback_code: 'WRONG_POSE',
    }), 'Cúi xuống một chút.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', quality_code: 'TOO BLURRY',
    }), 'Ảnh chưa rõ. Hãy giữ đầu ổn định.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'AWAITING_CONFIRMATION', expected_pose: null,
    }), 'Đã đủ năm góc. Chờ quản lý kiểm tra và xác nhận lưu.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', feedback_code: 'STALE_FRAME',
    }), 'Khung hình đã cũ hoặc trùng. Đang chờ hình mới từ camera.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', feedback_code: 'NO_FRAME',
    }), 'Không nhận được hình ảnh mới từ camera. Vui lòng báo quản lý.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', face_count: 0, quality_code: 'NO FACE',
    }), 'Chưa phát hiện khuôn mặt. Hãy nhìn vào camera.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', face_count: 2, quality_code: 'MULTIPLE FACES',
    }), 'Vui lòng đứng một mình trước camera.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', face_count: 2, total_face_count: 2,
        primary_face_safe: false, primary_face_area_ratio: 1.4,
        primary_face_area_ratio_required: 2, quality_code: 'MULTIPLE FACES',
    }), 'AI đang phát hiện 2 khuôn mặt; mặt lớn nhất chỉ gấp 1.4 lần mặt kế tiếp (cần ≥2.0). Hãy chỉnh camera để chỉ còn một khuôn mặt rõ.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', face_count: 2, total_face_count: 2,
        primary_face_safe: false, quality_code: 'FACE TOO SMALL',
    }), 'Hãy đến gần camera.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', face_count: 2, total_face_count: 2,
        face_count_lower_bound: true, primary_face_safe: false,
        quality_code: 'MULTIPLE FACES',
    }), 'Vui lòng đứng một mình trước camera.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', face_count: 2, primary_face_safe: true,
        expected_pose: 'left', detected_pose: 'left', stable_frame_count: 1,
    }), 'Giữ yên một chút.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', quality_code: 'FACE TOO SMALL',
    }), 'Hãy đến gần camera.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'MANUAL_FALLBACK', reason: 'FPS infer thấp; frame cũ.',
    }), 'FPS infer thấp; frame cũ.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'MANUAL_FALLBACK', feedback_code: 'AUTO_PAUSED',
    }), 'Phiên tự động đã tạm dừng. Vui lòng báo quản lý để tiếp tục.');
    const messages = [
        'Nhìn thẳng vào camera.', 'Quay sang trái một chút.', 'Giữ yên một chút.',
        'Ảnh chưa rõ. Hãy giữ đầu ổn định.',
    ].join(' ');
    assert.doesNotMatch(messages, /yaw|pitch|roll|reprojection|geodesic|fps|cosine|embedding|\d+°/i);
});

test('AUTO thumbnails are loaded after the full batch is hydrated; MANUAL stays incremental', () => {
    assert.deepEqual(enrollmentUi.thumbnailIndexesToLoad(4, 5, 'AUTO', false), []);
    assert.deepEqual(enrollmentUi.thumbnailIndexesToLoad(4, 5, 'AUTO', true), [0, 1, 2, 3, 4]);
    assert.deepEqual(enrollmentUi.thumbnailIndexesToLoad(2, 3, 'MANUAL', false), [2]);
});

test('SVG arc path is based on the measured face position', () => {
    const path = enrollmentUi.arcPath(160, 160, 81.6, 105.6, -90, 29);
    assert.match(path, /^M /);
    assert.match(path, / A 81\.60 105\.60 0 0 1 /);
});

test('enrollment diagnostics expose measured pose, quality, stability and frame freshness', () => {
    const text = enrollmentUi.diagnosticsFor({
        face_count: 1,
        primary_face_safe: true,
        detection_score: 0.91,
        expected_pose: 'left',
        detected_pose: 'between',
        stable_frame_count: 2,
        stable_frames_required: 5,
        inference_fps: 0.7,
        feedback_code: 'POSE_NOT_READY',
        quality_code: 'PASS',
        face_bbox: [100, 80, 220, 240],
        frame_width: 640,
        frame_height: 480,
        frame_sequence: 42,
        frame_age_ms: 38.2,
        primary_face_area_ratio: 2.4,
    });
    assert.match(text, /Mặt: 1/);
    assert.match(text, /Detect: 0\.91/);
    assert.match(text, /Ổn định: 2\/5/);
    assert.match(text, /0\.7 FPS/);
    assert.match(text, /POSE_NOT_READY/);
    assert.match(text, /BBox \[100, 80, 220, 240\] \/ 640×480/);
    assert.match(text, /Frame #42/);
    assert.match(text, /Tuổi frame 38 ms/);
    assert.match(text, /Tỷ lệ mặt chính\/thứ hai: 2\.40×/);
    const unavailable = enrollmentUi.diagnosticsFor({
        face_count: null,
        detection_score: null,
        inference_fps: null,
        frame_sequence: null,
        frame_age_ms: null,
    });
    assert.match(unavailable, /Mặt: —/);
    assert.match(unavailable, /Detect: —/);
    assert.match(unavailable, /đang đo FPS/);
    assert.doesNotMatch(unavailable, /Frame #0|Tuổi frame 0 ms/);
});
