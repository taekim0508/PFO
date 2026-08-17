"""The package imports cleanly.

Trivial on purpose. Its real job is to prove the src layout and the editable install
work, rather than passing because the test happened to run from the right directory.
"""

import portfolio_bot


def test_package_imports():
    assert portfolio_bot is not None


def test_version_is_a_non_empty_string():
    assert isinstance(portfolio_bot.__version__, str)
    assert portfolio_bot.__version__
