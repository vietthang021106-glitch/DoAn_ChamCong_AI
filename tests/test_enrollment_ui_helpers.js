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
    const complete = enrollmentUi.buildRingModel({
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
    }), 'Đang chờ hình ảnh mới từ camera. Vui lòng giữ nguyên tư thế.');
    assert.equal(enrollmentUi.guidanceFor({
        state: 'ENROLLING', feedback_code: 'NO_FRAME',
    }), 'Không nhận được hình ảnh mới từ camera. Vui lòng báo quản lý.');
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
