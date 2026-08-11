import pytest
from app.services.prior_updater import BayesianPriorUpdater


def test_outlier_filtering():
    updater = BayesianPriorUpdater()
    data = [0.05, 0.06, 0.05, 0.04, 0.99]  # 0.99 — выброс
    filtered = updater.filter_outliers(data)
    assert 0.99 not in filtered
    assert len(filtered) == 4


def test_calculate_posterior_increase():
    """Если реальные факты выше ожиданий, mu_new смещается вверх."""
    updater = BayesianPriorUpdater(min_observations=3)
    mu_0, sigma_0 = 0.05, 0.02
    facts = [0.12, 0.14, 0.13, 0.15]  # Факты выше 5%

    mu_new, sigma_new, stats = updater.calculate_posterior(mu_0, sigma_0, facts)

    assert mu_new > mu_0
    assert sigma_new < sigma_0  # Неопределенность сжалась
    assert stats["status"] == "updated"
