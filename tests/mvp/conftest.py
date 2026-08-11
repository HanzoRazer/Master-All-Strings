"""Fixtures for MVP-1F tests."""

from __future__ import annotations

import pytest

from master_all_strings.mvp.application import MvpApplication, load_default_instrument_catalog


@pytest.fixture(scope="session")
def instrument_catalog():
    return load_default_instrument_catalog()


@pytest.fixture
def app(instrument_catalog) -> MvpApplication:
    return MvpApplication(instrument_profiles=instrument_catalog)
