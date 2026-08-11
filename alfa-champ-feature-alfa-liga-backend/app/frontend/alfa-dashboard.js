(function () {
    'use strict';

    const api = window.AlfaLigaApi;
    if (!api) return;

    function setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    }

    function setConnectionState(state, title) {
        document.querySelectorAll('[data-api-state]').forEach((element) => {
            element.dataset.apiState = state;
            element.title = title;
            element.classList.toggle('bg-green-500', state === 'ready');
            element.classList.toggle('bg-red-500', state === 'error');
            element.classList.toggle('bg-amber-400', state === 'loading');
        });
    }

    async function hydrate() {
        setConnectionState('loading', 'Загрузка данных бизнеса');
        try {
            const state = await api.getBusinessState();
            const revenue = Number(state.revenue.value || 0);
            const contributionMargin = Number(state.contribution_margin.value || 0);
            const estimatedExpenses = Math.max(0, revenue * (1 - contributionMargin));
            const taxReserve = revenue * 0.06;

            setText('leagueRevenue', api.formatCurrency(revenue));
            setText('accountingBalance', api.formatCurrency(state.cash_balance.value));
            setText('accountingRevenue', `+ ${api.formatCurrency(revenue)}`);
            setText('accountingExpenses', `- ${api.formatCurrency(estimatedExpenses)}`);
            setText('accountingTaxReserve', api.formatCurrency(taxReserve));
            setText('accountingTaxPlan', `/ ${api.formatCurrency(taxReserve)} план`);
            setText('accountingWindow', 'Оборот за 60 дней');
            setText('accountingRunway', `${Number(state.runway_days.value || 0).toLocaleString('ru-RU', {
                maximumFractionDigits: 1,
            })} дней запаса`);
            setConnectionState('ready', 'Данные загружены из backend');
        } catch (error) {
            setConnectionState('error', error.message || 'Backend недоступен');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', hydrate, { once: true });
    } else {
        hydrate();
    }
})();
