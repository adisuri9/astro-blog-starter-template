from datetime import date, timedelta

import pytest

from career_agents import config
from career_agents.scout.filters import Filter, dedupe
from career_agents.scout.models import Job


@pytest.fixture
def flt():
    return Filter(config.search_config(), config.companies(), ["Acme Energy"])


@pytest.mark.parametrize("title", [
    "Head of Product, Consumer", "Director of Product Management", "Senior Director, Product - Growth",
    "VP, Product", "Vice President of E-commerce", "General Manager, Grocery", "Head of Category - Home",
    "AVP - Product", "Group Product Manager, Checkout", "Chief Product Officer", "Category Head, Electronics",
])
def test_titles_accepted(flt, title):
    assert flt.title_ok(title)


@pytest.mark.parametrize("title", [
    "Senior Product Manager", "Director of Engineering", "Director, Product Design", "VP Sales",
    "Product Marketing Director", "Associate Director, Product", "Director, Business Development",
    "Head of Talent", "Product Manager Intern", "General Manager, Fulfillment Center",
    "Chief of Staff to GM, Ads", "Executive Business Partner, Chief Business Officer",
    "Senior Director, Product and Brand Communications", "Creative Delivery Director, Business Marketing",
    "Director of Growth and Acquisition Marketing", "Director, Production & Planning",
])
def test_titles_rejected(flt, title):
    assert not flt.title_ok(title)


def test_region_prefers_highest_priority(flt):
    assert flt.region_for("Seattle, WA")["key"] == "seattle"
    assert flt.region_for("London, UK; San Francisco, CA")["key"] == "bay_area"
    assert flt.region_for("Austin, TX") is None


def test_wants_lets_ambiguous_locations_through(flt):
    assert flt.wants("Director of Product", "3 Locations")
    assert flt.wants("Director of Product", "")
    assert not flt.wants("Director of Product", "Austin, TX")
    assert not flt.wants("Software Engineer", "Seattle, WA")


def test_accept_sets_region_and_score(flt):
    job = Job("greenhouse", "1", "Airbnb", "Head of Product, Guest Experience", "San Francisco, CA",
              description="Millions of travelers use our marketplace", posted_at=date.today().isoformat())
    assert flt.accept(job)
    assert job.region == "bay_area"
    assert job.rule_score >= 80


def test_accept_drops_blocked_stale_and_b2b_india(flt):
    stale = (date.today() - timedelta(days=90)).isoformat()
    assert not flt.accept(Job("x", "1", "Acme Energy Pvt Ltd", "Head of Product", "Seattle"))
    assert not flt.accept(Job("x", "2", "Airbnb", "Head of Product", "Seattle", posted_at=stale))
    # India roles only count at US multinationals (L-1A launchpad)
    assert not flt.accept(Job("x", "3", "Some Startup", "Head of Product", "Bengaluru, India"))
    assert flt.accept(Job("x", "4", "Amazon", "Director, Product", "Bengaluru, KA, IND"))


def test_posts_skip_title_rules_but_respect_blocklist(flt):
    post = Job("linkedin-post", "u1", "Swiggy", "Product leader for Instamart", "Bengaluru", kind="post")
    assert flt.accept(post)
    assert not flt.accept(Job("linkedin-post", "u2", "Acme Energy", "Head of Product", "", kind="post"))


def test_dedupe_prefers_company_ats():
    a = Job("linkedin", "li-1", "DoorDash", "Director, Product", "San Francisco, CA", description="short")
    b = Job("greenhouse", "dd:9", "DoorDash", "Director, Product", "San Francisco, California", description="longer text")
    kept = dedupe([a, b])
    assert len(kept) == 1 and kept[0].source == "greenhouse"
