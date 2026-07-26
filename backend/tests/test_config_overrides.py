"""
Environment override safety (Package C follow-up).

`CAE_DATABASE_URL` reads like it redirects the database, and `database_url`
is a real attribute - but it is a derived property, so pydantic-settings
never looks it up and the override is discarded in silence. A migration run
"against a scratch copy" with that override set migrated the real development
database instead, because nothing said the redirect had not taken.

An override that silently does nothing is worse than one that fails.
"""

import pytest

from app.config import Settings, UnknownSetting, reject_unknown_env_overrides


def test_a_plausible_but_unread_override_is_refused():
    with pytest.raises(UnknownSetting, match="CAE_DATABASE_URL"):
        reject_unknown_env_overrides({"CAE_DATABASE_URL": "sqlite:///scratch.db"})


def test_the_error_names_the_variable_that_actually_works():
    """A refusal that does not say what to do instead just gets worked around."""
    with pytest.raises(UnknownSetting, match="set CAE_DATA_DIR"):
        reject_unknown_env_overrides({"CAE_DB_PATH": "/tmp/x"})


def test_a_near_miss_spelling_is_caught():
    with pytest.raises(UnknownSetting, match="CAE_DATADIR"):
        reject_unknown_env_overrides({"CAE_DATADIR": "/tmp/x"})


def test_every_declared_field_is_accepted():
    environ = {f"CAE_{name.upper()}": "x" for name in Settings.model_fields}
    reject_unknown_env_overrides(environ)


def test_unprefixed_variables_are_none_of_our_business():
    reject_unknown_env_overrides({"PATH": "/usr/bin", "DATABASE_URL": "postgres://x"})
