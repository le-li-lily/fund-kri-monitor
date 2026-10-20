from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"


@pytest.fixture(scope="session")
def positions_path() -> Path:
    return DATA_DIR / "portfolio_positions.csv"


@pytest.fixture(scope="session")
def returns_path() -> Path:
    return DATA_DIR / "asset_returns.csv"


@pytest.fixture(scope="session")
def thresholds_path() -> Path:
    return CONFIG_DIR / "thresholds.json"


@pytest.fixture(scope="session")
def reference_result(positions_path, returns_path, thresholds_path, tmp_path_factory):
    from fund_kri_monitor.kri import run_monitor

    history = tmp_path_factory.mktemp("history") / "kri_history.csv"
    return run_monitor(
        positions_path=positions_path,
        returns_path=returns_path,
        thresholds_path=thresholds_path,
        history_path=history,
    )


@pytest.fixture
def monitor_result(positions_path, returns_path, thresholds_path, tmp_path):
    """A fresh result object for tests that mutate it before persisting."""
    from fund_kri_monitor.kri import run_monitor

    return run_monitor(
        positions_path=positions_path,
        returns_path=returns_path,
        thresholds_path=thresholds_path,
        history_path=tmp_path / "kri_history.csv",
    )


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "risk_monitor.db"


@pytest.fixture
def positions_frame(positions_path) -> pd.DataFrame:
    return pd.read_csv(positions_path)


def write_positions(target: Path, frame: pd.DataFrame) -> Path:
    frame.to_csv(target, index=False)
    return target
