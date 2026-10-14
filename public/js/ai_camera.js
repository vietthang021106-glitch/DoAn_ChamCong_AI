(() => {
    const image = document.getElementById('ai-camera-image');
    const placeholder = document.getElementById('ai-camera-placeholder');
    const button = document.getElementById('ai-recognize');
    const state = document.getElementById('ai-result-state');
    const employee = document.getElementById('ai-result-employee');
    const code = document.getElementById('ai-result-code');
    const score = document.getElementById('ai-result-score');
    const match = document.getElementById('ai-result-match');
    const csrf = document.getElementById('ai-csrf-token');

    if (!image || !button) return;

    image.addEventListener('error', () => {
        placeholder.hidden = false;
    });
    image.addEventListener('load', () => {
        placeholder.hidden = true;
    });

    const refreshFrame = () => {
        image.src = `/?action=ai_camera_frame&t=${Date.now()}`;
    };
    window.setInterval(refreshFrame, 1500);

    button.addEventListener('click', async () => {
        button.disabled = true;
        state.textContent = 'Đang nhận diện…';
        try {
            const response = await fetch('/?action=ai_recognize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                    'Accept': 'application/json',
                },
                body: new URLSearchParams({ _csrf_token: csrf.value }),
            });
            const result = await response.json();
            state.textContent = result.message || 'Không có kết quả.';
            employee.textContent = result.ho_ten || '—';
            code.textContent = result.ma_nv == null ? '—' : `NV${String(result.ma_nv).padStart(3, '0')}`;
            score.textContent = result.score == null ? '—' : Number(result.score).toFixed(4);
            match.textContent = result.match ? 'Known' : (result.success ? 'Unknown' : 'Không có khuôn mặt');
            if (!response.ok) state.textContent = result.message || 'Không thể nhận diện.';
        } catch (error) {
            state.textContent = 'Không thể kết nối AI service.';
            employee.textContent = code.textContent = score.textContent = match.textContent = '—';
        } finally {
            button.disabled = false;
        }
    });
})();
