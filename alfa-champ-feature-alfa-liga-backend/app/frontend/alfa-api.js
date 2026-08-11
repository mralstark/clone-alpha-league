(function () {
    'use strict';

    const configuredBase = document.documentElement.dataset.apiBase || '';
    const apiBase = configuredBase.trim() || (window.location.protocol === 'file:' ? 'http://localhost:8000' : '');
    const businessId = document.documentElement.dataset.businessId || 'coffee_demo';

    class ApiError extends Error {
        constructor(message, status, payload) {
            super(message);
            this.name = 'ApiError';
            this.status = status;
            this.payload = payload;
        }
    }

    function buildUrl(path) {
        return `${apiBase}${path}`;
    }

    function errorMessage(payload, status) {
        if (payload && Array.isArray(payload.detail)) {
            return payload.detail
                .map((item) => `${item.loc ? item.loc.join('.') : 'request'}: ${item.msg || 'invalid value'}`)
                .join('; ');
        }
        if (payload && typeof payload.detail === 'string') return payload.detail;
        return `Backend вернул ошибку ${status}`;
    }

    async function request(path, options = {}) {
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 45000);
        const headers = new Headers(options.headers || {});
        if (options.body && !headers.has('Content-Type')) {
            headers.set('Content-Type', 'application/json');
        }

        try {
            const response = await fetch(buildUrl(path), {
                ...options,
                headers,
                signal: controller.signal,
            });
            const contentType = response.headers.get('content-type') || '';
            const payload = contentType.includes('application/json')
                ? await response.json()
                : await response.text();

            if (!response.ok) {
                throw new ApiError(errorMessage(payload, response.status), response.status, payload);
            }
            return payload;
        } catch (error) {
            if (error && error.name === 'AbortError') {
                throw new ApiError('Backend не ответил за 45 секунд', 0, null);
            }
            if (error instanceof ApiError) throw error;
            throw new ApiError('Не удалось связаться с backend. Проверьте, что FastAPI запущен.', 0, null);
        } finally {
            window.clearTimeout(timeoutId);
        }
    }

    function getHealth() {
        return request('/api/health');
    }

    function getBusinessState() {
        return request(`/api/businesses/${encodeURIComponent(businessId)}/state`);
    }

    function createDecision(payload) {
        return request('/api/decisions', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    function resimulateCandidate(candidateId, payload) {
        return request(`/api/candidates/${encodeURIComponent(candidateId)}/resimulate`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    function createExperiment(candidateId) {
        return request('/api/experiments', {
            method: 'POST',
            body: JSON.stringify({ candidate_id: candidateId, confirmed: true }),
        });
    }

    function formatCurrency(value) {
        return `${Math.round(Number(value || 0)).toLocaleString('ru-RU')} ₽`;
    }

    function formatPercent(value, digits = 1) {
        return `${(Number(value || 0) * 100).toLocaleString('ru-RU', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        })}%`;
    }

    window.AlfaLigaApi = Object.freeze({
        ApiError,
        businessId,
        getHealth,
        getBusinessState,
        createDecision,
        resimulateCandidate,
        createExperiment,
        formatCurrency,
        formatPercent,
    });
})();
