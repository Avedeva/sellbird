from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sellbird.agents.scout import Scout

STRATEGIES = (
    "hunter", "known_companies", "linkedin",
    "hiring_boards", "profile_search", "company_discovery",
)


def _scout(linkedin_enabled: bool, linkedin_email: str = "") -> Scout:
    brain = SimpleNamespace(load_skills_for_agent=lambda name: "")
    state = SimpleNamespace(log_action=AsyncMock())
    config = SimpleNamespace(
        channels=SimpleNamespace(linkedin=SimpleNamespace(enabled=linkedin_enabled))
    )
    env = SimpleNamespace(linkedin_email=linkedin_email)
    scout = Scout(brain, state, config, env)
    for name in STRATEGIES:
        setattr(scout, f"_prospect_via_{name}", AsyncMock(return_value=0))
    return scout


@pytest.mark.asyncio
async def test_paid_and_linkedin_strategies_are_not_active_even_when_configured():
    """The local-only Scout uses account backfill, public boards and public search."""
    for enabled, email in ((False, ""), (True, "me@example.com")):
        scout = _scout(linkedin_enabled=enabled, linkedin_email=email)
        await scout.run()
        scout._prospect_via_known_companies.assert_awaited_once()
        scout._prospect_via_hiring_boards.assert_awaited_once()
        scout._prospect_via_company_discovery.assert_awaited_once()
        scout._prospect_via_hunter.assert_not_awaited()
        scout._prospect_via_linkedin.assert_not_awaited()
        scout._prospect_via_profile_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_linkedin_login_does_not_enable_profile_search():
    """LinkedIn profile searches remain out of the public-source workflow."""
    scout = _scout(linkedin_enabled=True)
    await scout.run()
    scout._prospect_via_profile_search.assert_not_awaited()
    scout._prospect_via_linkedin.assert_not_awaited()
