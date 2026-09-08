"""The default suite is portable; --integration explicitly requires local source data."""
import os
from pathlib import Path
import pytest

INTEGRATION_MODULES={'test_contract.py','test_visuals.py','test_revision.py','test_revision_visuals.py'}


def pytest_addoption(parser):
    parser.addoption('--integration',action='store_true',help='Run Forge/ZIP/Windows-font integration tests too')


def pytest_ignore_collect(collection_path,config):
    return collection_path.name in INTEGRATION_MODULES and not config.getoption('--integration')


def pytest_collection_modifyitems(config,items):
    if not config.getoption('--integration'):
        for item in items:
            if 'integration' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Use --integration with Forge and source bundles'))


def pytest_sessionstart(session):
    if session.config.getoption('--integration'):
        parent=Path(__file__).resolve().parents[2]
        paths=[Path(os.environ.get('PRESS_FORGE_ROOT',parent/'integrated-social-item-forge'))/'src',
               Path(os.environ.get('PRESS_INPUT_ROOT',parent/'outputs/social-language-20260908'))]
        if any(not p.is_dir() for p in paths):
            raise pytest.UsageError('Integration inputs missing. Set PRESS_FORGE_ROOT and PRESS_INPUT_ROOT.')
