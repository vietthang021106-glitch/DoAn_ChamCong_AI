(() => {
    const DEFAULT_MAX_ATTEMPTS = 4;

    const startRecognition = async ({
        fetchImpl,
        readJson,
        csrfToken,
        onPreparing = () => {},
        waitImpl = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds)),
        delayMs = 350,
        maxAttempts = DEFAULT_MAX_ATTEMPTS,
    }) => {
        if (typeof fetchImpl !== 'function' || typeof readJson !== 'function') {
            throw new TypeError('Kiosk AI start requires fetch and JSON readers.');
        }
        const attempts = Math.min(DEFAULT_MAX_ATTEMPTS, Math.max(1, Number(maxAttempts) || DEFAULT_MAX_ATTEMPTS));
        for (let attempt = 0; attempt < attempts; attempt += 1) {
            const response = await fetchImpl('/?action=kiosk_recognition_start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
                body: new URLSearchParams({ _csrf_token: csrfToken || '' }),
                credentials: 'same-origin',
                cache: 'no-store',
            });
            const payload = await readJson(response);
            if (payload.code !== 'AI1_PREPARING') return { response, payload };
            if (attempt + 1 >= attempts) {
                const error = new Error('AI1_PREPARING');
                error.payload = payload;
                throw error;
            }
            onPreparing(attempt + 1, attempts - 1);
            await waitImpl(Math.max(0, Number(delayMs) || 0) * (attempt + 1));
        }
        throw new Error('AI1_PREPARING');
    };

    window.KioskAiStart = { startRecognition, DEFAULT_MAX_ATTEMPTS };
})();
