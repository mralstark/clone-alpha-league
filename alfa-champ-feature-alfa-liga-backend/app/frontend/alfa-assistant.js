(function () {
    'use strict';

    const api = window.AlfaLigaApi;
    if (!api) throw new Error('AlfaLigaApi must be loaded before alfa-assistant.js');

    const scenarioFields = {
        MORNING_DISCOUNT: ['discount_pct'],
        REPEAT_BONUS: ['bonus_pct'],
        MICRO_AD_TEST: [],
        PRICE_CHANGE: ['price_change_pct'],
        OPENING_HOURS_CHANGE: ['opening_hour', 'closing_hour'],
        PRODUCT_BUNDLE: ['bundle_discount_pct'],
        NO_ACTION: [],
    };

    const businessParameters = [
        { id: 'discount_pct', name: 'Скидка в слабые часы', min: 0, max: 30, step: 1, value: 9, currentValue: 0, unit: '%', format: 'number', kind: 'action' },
        { id: 'bonus_pct', name: 'Бонус за повторный визит', min: 0, max: 25, step: 1, value: 7, currentValue: 0, unit: '%', format: 'number', kind: 'action' },
        { id: 'bundle_discount_pct', name: 'Скидка на набор', min: 0, max: 25, step: 1, value: 6, currentValue: 0, unit: '%', format: 'number', kind: 'action' },
        { id: 'price_change_pct', name: 'Изменение цены', min: -20, max: 30, step: 1, value: 5, currentValue: 0, unit: '%', format: 'signed', kind: 'action' },
        { id: 'opening_hour', name: 'Открытие точки', min: 5, max: 12, step: 1, value: 8, currentValue: 8, unit: ':00', format: 'number', kind: 'action' },
        { id: 'closing_hour', name: 'Закрытие точки', min: 17, max: 23, step: 1, value: 20, currentValue: 20, unit: ':00', format: 'number', kind: 'action' },
        { id: 'action_budget', name: 'Бюджет теста', min: 0, max: 20000, step: 500, value: 4500, currentValue: 0, unit: '₽', format: 'money', kind: 'common' },
        { id: 'duration_days', name: 'Длительность теста', min: 1, max: 30, step: 1, value: 10, currentValue: 10, unit: 'дн.', format: 'number', kind: 'common' },
        { id: 'max_budget', name: 'Лимит бюджета', min: 1000, max: 50000, step: 500, value: 10000, currentValue: 10000, unit: '₽', format: 'money', kind: 'constraint' },
        { id: 'max_loss', name: 'Допустимый убыток', min: 500, max: 20000, step: 500, value: 5000, currentValue: 5000, unit: '₽', format: 'money', kind: 'constraint' },
        { id: 'min_cash_reserve', name: 'Неснижаемый остаток', min: 0, max: 200000, step: 5000, value: 50000, currentValue: 50000, unit: '₽', format: 'money', kind: 'constraint' },
        { id: 'revenue', name: 'Выручка за 60 дней', min: 100000, max: 2000000, step: 1000, value: 693000, currentValue: 693000, unit: '₽', format: 'money', kind: 'live' },
        { id: 'average_ticket', name: 'Средний чек', min: 100, max: 1500, step: 10, value: 360, currentValue: 360, unit: '₽', format: 'money', kind: 'live' },
        { id: 'repeat_rate', name: 'Повторные покупки', min: 0, max: 60, step: 1, value: 17, currentValue: 17, unit: '%', format: 'number', kind: 'live' },
        { id: 'contribution_margin', name: 'Contribution margin', min: -10, max: 50, step: 1, value: 15, currentValue: 15, unit: '%', format: 'signed', kind: 'live' },
        { id: 'morning_utilization', name: 'Утренняя загрузка', min: 0, max: 100, step: 1, value: 7, currentValue: 7, unit: '%', format: 'number', kind: 'live' },
        { id: 'cash_balance', name: 'Остаток на счёте', min: 0, max: 500000, step: 5000, value: 180000, currentValue: 180000, unit: '₽', format: 'money', kind: 'live' },
    ];

    const grid = document.getElementById('slidersGrid');
    const chatInput = document.getElementById('chatInput');
    const chatMessages = document.getElementById('chatMessages');
    const chatScroll = document.getElementById('chatScroll');
    const historyList = document.getElementById('historyList');
    const sidebar = document.getElementById('historySidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const scenarioType = document.getElementById('scenarioType');
    const sendButton = document.getElementById('sendButton');
    const apiStatusDot = document.getElementById('apiStatusDot');
    const apiStatusText = document.getElementById('apiStatusText');
    const slidersMap = {};

    let chatSessions = [newSession('Новое моделирование')];
    let activeSessionId = chatSessions[0].id;

    function newSession(title) {
        return {
            id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
            title,
            date: 'Только что',
            messages: [{
                sender: 'ai',
                text: 'Я подключён к симулятору Альфа‑Лиги. Выберите режим, настройте безопасные лимиты и опишите решение, которое хотите проверить.',
            }],
        };
    }

    function formatValue(value, format) {
        const number = Number(value);
        if (format === 'money') return Math.round(number).toLocaleString('ru-RU');
        if (format === 'signed' && number > 0) return `+${number.toLocaleString('ru-RU')}`;
        return number.toLocaleString('ru-RU');
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, Number(value)));
    }

    function updateSlider(item) {
        const { input, display, diffDisplay, currentDisplay, config } = item;
        const value = Number(input.value);
        const percentage = ((value - Number(input.min)) / (Number(input.max) - Number(input.min))) * 100;
        input.style.background = `linear-gradient(to right, #EF3124 0%, #EF3124 ${percentage}%, #E5E7EB ${percentage}%, #E5E7EB 100%)`;
        display.textContent = `${formatValue(value, config.format)} ${config.unit}`;
        currentDisplay.textContent = `${config.kind === 'live' ? 'Из backend' : 'Базовое'}: ${formatValue(config.currentValue, config.format)} ${config.unit}`;

        const difference = value - config.currentValue;
        if (config.kind === 'live') {
            diffDisplay.textContent = 'LIVE';
            diffDisplay.className = 'text-[11px] font-bold h-4 text-green-600';
        } else if (difference > 0) {
            diffDisplay.textContent = `+${formatValue(difference, config.format)}`;
            diffDisplay.className = 'text-[11px] font-bold h-4 text-green-500';
        } else if (difference < 0) {
            diffDisplay.textContent = formatValue(difference, config.format);
            diffDisplay.className = 'text-[11px] font-bold h-4 text-red-500';
        } else {
            diffDisplay.textContent = 'Без изменений';
            diffDisplay.className = 'text-[11px] font-medium h-4 text-gray-400';
        }
    }

    function createSliders() {
        businessParameters.forEach((config) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'flex flex-col gap-2 p-3 bg-gray-50/50 rounded-xl border border-transparent hover:border-gray-200 transition';
            wrapper.dataset.parameter = config.id;
            wrapper.innerHTML = `
                <div class="flex justify-between items-start gap-3">
                    <div class="flex flex-col min-w-0">
                        <label class="font-semibold text-gray-800 text-sm" for="${config.id}">${config.name}</label>
                        <span class="text-[11px] text-gray-500 font-medium" id="current_${config.id}"></span>
                    </div>
                    <div class="flex flex-col items-end shrink-0">
                        <span class="font-bold text-alfa-dark text-lg leading-none" id="val_${config.id}"></span>
                        <span class="text-[11px] font-bold h-4 transition-all" id="diff_${config.id}"></span>
                    </div>
                </div>
                <input type="range" id="${config.id}" min="${config.min}" max="${config.max}" step="${config.step}" value="${config.value}" class="w-full cursor-pointer mt-1 disabled:cursor-not-allowed">
            `;
            grid.appendChild(wrapper);

            const item = {
                wrapper,
                config,
                input: wrapper.querySelector('input'),
                display: wrapper.querySelector(`#val_${config.id}`),
                diffDisplay: wrapper.querySelector(`#diff_${config.id}`),
                currentDisplay: wrapper.querySelector(`#current_${config.id}`),
            };
            slidersMap[config.id] = item;
            item.input.addEventListener('input', () => updateSlider(item));
            updateSlider(item);
        });
        updateScenarioFields();
    }

    function parameterValue(id) {
        return Number(slidersMap[id].input.value);
    }

    function setParameter(id, value, updateBaseline = true) {
        const item = slidersMap[id];
        if (!item || value === null || value === undefined) return;
        const nextValue = clamp(value, item.config.min, item.config.max);
        if (updateBaseline) item.config.currentValue = nextValue;
        item.input.value = nextValue;
        updateSlider(item);
    }

    function resetSliders() {
        Object.values(slidersMap).forEach((item) => {
            item.input.value = item.config.currentValue;
            updateSlider(item);
        });
    }

    function updateScenarioFields() {
        const selected = scenarioType ? scenarioType.value : 'AUTO';
        Object.values(slidersMap).forEach((item) => {
            const { config, wrapper, input } = item;
            let enabled = config.kind === 'constraint' || config.kind === 'live';
            if (config.kind === 'common') enabled = selected !== 'GENERATE' && selected !== 'NO_ACTION';
            if (config.kind === 'action') {
                enabled = selected === 'AUTO' || (scenarioFields[selected] || []).includes(config.id);
            }
            input.disabled = config.kind === 'live' || !enabled;
            wrapper.classList.toggle('opacity-40', !enabled);
            wrapper.classList.toggle('border-green-100', config.kind === 'live');
        });
    }

    function setApiStatus(status, text) {
        apiStatusText.textContent = text;
        apiStatusDot.className = 'w-2 h-2 rounded-full inline-block';
        if (status === 'ready') apiStatusDot.classList.add('bg-green-500');
        else if (status === 'error') apiStatusDot.classList.add('bg-red-500');
        else apiStatusDot.classList.add('bg-amber-400', 'animate-pulse');
    }

    async function loadBusinessState() {
        setApiStatus('loading', 'Загружаю состояние бизнеса');
        try {
            const state = await api.getBusinessState();
            setParameter('revenue', state.revenue.value);
            setParameter('average_ticket', state.average_ticket.value);
            setParameter('repeat_rate', Number(state.repeat_rate.value) * 100);
            setParameter('contribution_margin', Number(state.contribution_margin.value) * 100);
            setParameter('morning_utilization', Number(state.morning_utilization.value) * 100);
            setParameter('cash_balance', state.cash_balance.value);
            setParameter('max_budget', state.constraints.max_budget);
            setParameter('max_loss', state.constraints.max_loss);
            setParameter('min_cash_reserve', state.constraints.min_cash_reserve);
            setApiStatus('ready', 'Backend и данные готовы');
        } catch (error) {
            setApiStatus('error', 'Backend недоступен');
            activeSession().messages.push({ sender: 'error', text: error.message });
            renderMessages();
        }
    }

    function activeSession() {
        return chatSessions.find((session) => session.id === activeSessionId);
    }

    function inferScenario(text) {
        const normalized = text.toLowerCase().replaceAll('ё', 'е');
        if (normalized.includes('ничего не') || normalized.includes('без изменений')) return 'NO_ACTION';
        if (normalized.includes('скид') || normalized.includes('дешевле')) return 'MORNING_DISCOUNT';
        if (normalized.includes('бонус') || normalized.includes('повторн')) return 'REPEAT_BONUS';
        if (normalized.includes('реклам') || normalized.includes('таргет')) return 'MICRO_AD_TEST';
        if (normalized.includes('набор') || normalized.includes('комбо') || normalized.includes('выпеч')) return 'PRODUCT_BUNDLE';
        if (normalized.includes('график') || normalized.includes('часы работы') || normalized.includes('открывать')) return 'OPENING_HOURS_CHANGE';
        if (normalized.includes('цен')) return 'PRICE_CHANGE';
        return 'GENERATE';
    }

    function scenarioRequest(scenario, userText) {
        const duration = parameterValue('duration_days');
        const budget = parameterValue('action_budget');
        const goal = userText ? ` Цель пользователя: ${userText}` : '';
        if (scenario === 'MORNING_DISCOUNT') {
            return `Дать скидку ${parameterValue('discount_pct')}% утром на ${duration} дней с бюджетом ${budget} рублей.${goal}`;
        }
        if (scenario === 'REPEAT_BONUS') {
            return `Дать бонус ${parameterValue('bonus_pct')}% за повторный визит на ${duration} дней с бюджетом ${budget} рублей.${goal}`;
        }
        if (scenario === 'MICRO_AD_TEST') {
            return `Запустить рекламу с бюджетом ${budget} рублей на ${duration} дней.${goal}`;
        }
        if (scenario === 'PRICE_CHANGE') {
            const change = parameterValue('price_change_pct');
            const direction = change < 0 ? 'Снизить' : 'Повысить';
            return `${direction} цену на ${Math.abs(change)}% на ${duration} дней с бюджетом ${budget} рублей.${goal}`;
        }
        if (scenario === 'OPENING_HOURS_CHANGE') {
            return `Изменить часы работы: открывать в ${parameterValue('opening_hour')}:00 и закрывать в ${parameterValue('closing_hour')}:00 на ${duration} дней с бюджетом ${budget} рублей.${goal}`;
        }
        if (scenario === 'PRODUCT_BUNDLE') {
            return `Запустить набор кофе + выпечка со скидкой ${parameterValue('bundle_discount_pct')}% на ${duration} дней с бюджетом ${budget} рублей.${goal}`;
        }
        if (scenario === 'NO_ACTION') return `Пока ничего не менять, оставить без изменений.${goal}`;
        return userText;
    }

    function buildDecisionPayload(text) {
        const selected = scenarioType.value;
        const resolvedScenario = selected === 'AUTO' ? inferScenario(text) : selected;
        const mode = resolvedScenario === 'GENERATE' ? 'GENERATE' : 'EVALUATE';
        return {
            business_id: api.businessId,
            mode,
            request: scenarioRequest(resolvedScenario, text),
            overrides: {
                max_budget: parameterValue('max_budget'),
                max_loss: parameterValue('max_loss'),
                min_cash_reserve: parameterValue('min_cash_reserve'),
            },
            seed: 42,
        };
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function riskLabel(code) {
        const labels = {
            EXPECTED_PROFIT_NEGATIVE: 'Ожидаемая прибыль отрицательная',
            MAX_LOSS_RISK: 'Риск превышения лимита убытка',
            NEGATIVE_MARGIN: 'Риск отрицательной маржи',
        };
        return labels[code] || code.replaceAll('_', ' ').toLowerCase();
    }

    function cardHtml(card) {
        const risks = card.risks.length
            ? `<div class="mt-2 text-[11px] text-amber-700">${card.risks.map((risk) => `⚠ ${escapeHtml(riskLabel(risk))}`).join('<br>')}</div>`
            : '<div class="mt-2 text-[11px] text-green-700">Детерминированные проверки пройдены</div>';
        return `
            <article class="rounded-xl border border-gray-200 bg-gray-50 p-3 mt-3">
                <div class="flex items-start justify-between gap-2">
                    <div>
                        <div class="font-bold text-gray-900">${escapeHtml(card.name)}</div>
                        <div class="text-[11px] text-gray-500 mt-0.5">${card.duration_days} дней · бюджет ${api.formatCurrency(card.budget)}</div>
                    </div>
                    <span class="text-[10px] font-bold text-green-700 bg-green-100 px-2 py-1 rounded-full">${escapeHtml(card.decision)}</span>
                </div>
                <div class="grid grid-cols-2 gap-2 mt-3 text-xs">
                    <div class="bg-white rounded-lg p-2"><span class="text-gray-400 block">Вероятность KPI</span><b>${api.formatPercent(card.kpi_success_probability)}</b></div>
                    <div class="bg-white rounded-lg p-2"><span class="text-gray-400 block">Ожид. эффект</span><b>${api.formatCurrency(card.expected_financial_effect)}</b></div>
                    <div class="bg-white rounded-lg p-2 col-span-2"><span class="text-gray-400 block">P10 / P50 / P90</span><b>${api.formatCurrency(card.p10)} / ${api.formatCurrency(card.p50)} / ${api.formatCurrency(card.p90)}</b></div>
                </div>
                ${risks}
                <div class="flex flex-wrap gap-2 mt-3">
                    <button type="button" data-action="experiment" data-candidate-id="${escapeHtml(card.candidate_id)}" class="px-3 py-2 bg-alfa-red text-white rounded-lg text-xs font-bold hover:bg-red-600">Запустить тест</button>
                    <button type="button" data-action="resimulate" data-candidate-id="${escapeHtml(card.candidate_id)}" data-sprint-id="${escapeHtml(card.sprint_id)}" class="px-3 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg text-xs font-bold hover:border-alfa-red">Пересчитать</button>
                </div>
            </article>
        `;
    }

    function decisionHtml(decision) {
        const cards = decision.best_candidates.map(cardHtml).join('');
        const blocked = decision.blocked_candidates.length
            ? `<details class="mt-3 rounded-lg bg-red-50 p-2"><summary class="cursor-pointer text-xs font-bold text-red-700">Заблокировано сценариев: ${decision.blocked_candidates.length}</summary>${decision.blocked_candidates.map((item) => `<div class="mt-2 text-xs"><b>${escapeHtml(item.name)}</b><br>${item.reasons.map(escapeHtml).join('<br>')}</div>`).join('')}</details>`
            : '';
        const missing = decision.decision_trace.missing_data.length
            ? `<div class="mt-3 text-xs text-amber-700">Нужно дополнить данные: ${decision.decision_trace.missing_data.map(escapeHtml).join(', ')}</div>`
            : '';
        return `
            <div class="text-sm text-gray-800">
                <p>${escapeHtml(decision.problem_summary)}</p>
                ${cards || '<div class="mt-3 rounded-lg bg-amber-50 p-3 text-amber-800">Безопасный сценарий не прошёл проверки.</div>'}
                ${blocked}
                ${missing}
                <details class="mt-3 text-xs text-gray-500">
                    <summary class="cursor-pointer font-semibold">Почему модель так решила</summary>
                    <div class="mt-2">Правила: ${decision.decision_trace.rules_fired.map(escapeHtml).join(', ') || 'нет'}</div>
                    <div class="mt-1">Симулятор: ${escapeHtml(decision.model_versions.simulator)} · 5 000 прогонов</div>
                </details>
            </div>
        `;
    }

    function renderMessages() {
        chatMessages.innerHTML = '';
        activeSession().messages.forEach((message) => {
            const wrapper = document.createElement('div');
            const isUser = message.sender === 'user';
            wrapper.className = `flex gap-3 max-w-[96%] chat-message ${isUser ? 'self-end flex-row-reverse' : 'self-start'}`;

            const avatar = document.createElement('div');
            avatar.className = isUser
                ? 'w-8 h-8 rounded-full bg-alfa-lightRed flex items-center justify-center text-sm shrink-0 mt-1 border border-red-100'
                : 'w-8 h-8 rounded-full bg-[#FFD6D6] flex items-center justify-center text-sm shrink-0 mt-1';
            avatar.textContent = isUser ? 'А' : '🤖';

            const bubble = document.createElement('div');
            if (isUser) {
                bubble.className = 'bg-alfa-red text-white p-3 md:p-4 rounded-2xl rounded-tr-sm shadow-md';
            } else {
                bubble.className = `bg-white p-3 md:p-4 rounded-2xl rounded-tl-sm shadow-sm border w-full overflow-hidden ${message.sender === 'error' ? 'border-red-200 text-red-700' : 'border-gray-100'}`;
            }
            if (message.html) bubble.innerHTML = message.html;
            else {
                const paragraph = document.createElement('p');
                paragraph.className = `text-sm ${message.sender === 'system' ? 'text-gray-500 italic' : ''}`;
                paragraph.textContent = message.text;
                bubble.appendChild(paragraph);
            }

            wrapper.append(avatar, bubble);
            chatMessages.appendChild(wrapper);
        });
        chatScroll.scrollTo({ top: chatScroll.scrollHeight, behavior: 'smooth' });
    }

    async function sendDataToAI() {
        const text = chatInput.value.trim();
        if (!text || sendButton.disabled) return;
        const session = activeSession();
        if (session.messages.length <= 1) {
            session.title = text.length > 28 ? `${text.slice(0, 28)}…` : text;
            updateHistoryUI();
        }

        session.messages.push({ sender: 'user', text });
        session.messages.push({ sender: 'system', text: 'Строю Business State, применяю hard rules и запускаю 5 000 Monte Carlo‑прогонов…' });
        chatInput.value = '';
        sendButton.disabled = true;
        chatInput.disabled = true;
        renderMessages();

        try {
            const decision = await api.createDecision(buildDecisionPayload(text));
            session.messages.pop();
            session.messages.push({ sender: 'ai', html: decisionHtml(decision) });
            setApiStatus('ready', 'Backend и данные готовы');
        } catch (error) {
            session.messages.pop();
            session.messages.push({ sender: 'error', text: error.message });
            setApiStatus('error', 'Ошибка запроса');
        } finally {
            sendButton.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
            renderMessages();
        }
    }

    function resimulationParameters(sprintId) {
        const mappings = {
            MORNING_DISCOUNT: { discount_pct: parameterValue('discount_pct'), target_hours: [8, 9, 10] },
            REPEAT_BONUS: { bonus_pct: parameterValue('bonus_pct') },
            MICRO_AD_TEST: { ad_budget: parameterValue('action_budget') },
            PRICE_CHANGE: { price_change_pct: parameterValue('price_change_pct') },
            OPENING_HOURS_CHANGE: { opening_hour: parameterValue('opening_hour'), closing_hour: parameterValue('closing_hour') },
            PRODUCT_BUNDLE: { bundle_discount_pct: parameterValue('bundle_discount_pct'), target_hours: [8, 9, 10] },
        };
        return mappings[sprintId] || null;
    }

    async function handleCardAction(button) {
        if (button.disabled) return;
        button.disabled = true;
        const session = activeSession();
        session.messages.push({ sender: 'system', text: button.dataset.action === 'experiment' ? 'Создаю подтверждённый mock‑эксперимент…' : 'Пересчитываю карточку без повторного вызова policy…' });
        renderMessages();
        try {
            if (button.dataset.action === 'experiment') {
                const experiment = await api.createExperiment(button.dataset.candidateId);
                session.messages.pop();
                session.messages.push({
                    sender: 'ai',
                    html: `<div class="text-sm"><b>Эксперимент запущен.</b><div class="mt-2 rounded-lg bg-green-50 p-2 text-green-800">Статус: ${escapeHtml(experiment.status)}<br>ID: ${escapeHtml(experiment.experiment_id)}</div><p class="text-xs text-gray-500 mt-2">Интеграции продуктов остаются MOCK и требуют подтверждения владельца.</p></div>`,
                });
            } else {
                const result = await api.resimulateCandidate(button.dataset.candidateId, {
                    parameters: resimulationParameters(button.dataset.sprintId),
                    budget: parameterValue('action_budget'),
                    duration_days: parameterValue('duration_days'),
                    seed: 42,
                });
                session.messages.pop();
                if (result.card) {
                    session.messages.push({ sender: 'ai', html: `<div class="text-sm"><b>Контрфактуальный пересчёт:</b>${cardHtml(result.card)}</div>` });
                } else {
                    session.messages.push({ sender: 'ai', html: `<div class="rounded-lg bg-red-50 p-3 text-sm text-red-800"><b>Сценарий заблокирован.</b><br>${result.reasons.map(escapeHtml).join('<br>')}</div>` });
                }
            }
        } catch (error) {
            session.messages.pop();
            session.messages.push({ sender: 'error', text: error.message });
        } finally {
            renderMessages();
        }
    }

    function toggleHistory() {
        sidebar.classList.toggle('active');
        overlay.classList.toggle('active');
        if (sidebar.classList.contains('active')) updateHistoryUI();
    }

    function updateHistoryUI() {
        historyList.innerHTML = '';
        [...chatSessions].reverse().forEach((session) => {
            const button = document.createElement('button');
            const isActive = session.id === activeSessionId;
            button.type = 'button';
            button.className = `text-left p-3 rounded-xl transition border ${isActive ? 'bg-alfa-lightRed border-red-200 shadow-sm' : 'hover:bg-gray-50 border-transparent hover:border-gray-200'}`;
            const title = document.createElement('div');
            title.className = `font-semibold text-sm truncate ${isActive ? 'text-alfa-red' : 'text-gray-800'}`;
            title.textContent = session.title;
            const meta = document.createElement('div');
            meta.className = `text-xs ${isActive ? 'text-red-400' : 'text-gray-400'} mt-1`;
            meta.textContent = `${session.date} · ${session.messages.length} сообщ.`;
            button.append(title, meta);
            button.addEventListener('click', () => switchChat(session.id));
            historyList.appendChild(button);
        });
    }

    function switchChat(id) {
        activeSessionId = id;
        renderMessages();
        updateHistoryUI();
        if (window.innerWidth < 1024) toggleHistory();
    }

    function createNewChat() {
        const session = newSession('Новое моделирование');
        chatSessions.push(session);
        activeSessionId = session.id;
        renderMessages();
        updateHistoryUI();
    }

    chatInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            sendDataToAI();
        }
    });
    chatMessages.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action]');
        if (button) handleCardAction(button);
    });
    scenarioType.addEventListener('change', updateScenarioFields);

    window.resetSliders = resetSliders;
    window.sendDataToAI = sendDataToAI;
    window.toggleHistory = toggleHistory;
    window.createNewChat = createNewChat;

    createSliders();
    renderMessages();
    loadBusinessState();
})();
