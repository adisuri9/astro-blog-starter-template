from datetime import date, timedelta

import pytest

from career_agents import config
from career_agents.scout.filters import Filter, dedupe, required_years
from career_agents.scout.models import Job


@pytest.fixture
def flt():
    return Filter(config.search_config(), config.companies(), ["Acme Energy"])


@pytest.mark.parametrize("title", [
    "Head of Product, Consumer", "Director of Product Management", "Senior Director, Product - Growth",
    "VP, Product", "Vice President of E-commerce", "General Manager, Grocery", "Head of Category - Home",
    "AVP - Product", "Group Product Manager, Checkout", "Chief Product Officer", "Category Head, Electronics",
    # senior roles outside product are welcome too
    "Head of Business Development", "Director, Business Development", "VP Sales, Americas",
    "Director, Strategy & Operations", "Co-Founder & CEO", "Founding Head of Growth", "Chief of Staff to GM, Ads",
    "Assistant Vice President, Partnerships", "Head, Category Management", "Country Manager, Brazil",
    "Product Marketing Director", "Associate Director, Product", "Director of Growth and Acquisition Marketing",
    # Amazon's Director-equivalent (L7) titles
    "Principal Product Manager - Tech, Amazon Fresh", "Sr. Manager, Product Management",
    # excluded functions are kept when the title is also product/business
    "Director, Product Management - Forward Deployed Engineering", "VP Finance & Business Operations",
])
def test_titles_accepted(flt, title):
    assert flt.title_ok(title)


@pytest.mark.parametrize("title", [
    "Product Manager Intern", "Director of Engineering", "VP Engineering",
    "Head of Talent", "Director, Legal", "Senior Software Engineer", "Executive Assistant to the CEO",
    "Executive Business Partner, Chief Business Officer", "General Manager, Fulfillment Center",
    "Store Director", "Chief Financial Officer", "Head of Security", "Senior Software Engineer, Product",
    "Marketing Coordinator", "Account Executive", "VP, Global People Business Partners",
    "Director, Product & Brand Communications",
])
def test_titles_rejected(flt, title):
    assert not flt.title_ok(title)


def test_core_functions_rank_above_other_senior_roles(flt):
    product = Job("greenhouse", "1", "Airbnb", "VP Product", "Seattle")
    sales = Job("greenhouse", "2", "Airbnb", "VP Sales", "Seattle")
    assert flt.accept(product) and flt.accept(sales)
    assert product.rule_score > sales.rule_score


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


@pytest.mark.parametrize("text, years", [
    ("10+ years of product experience; 3+ years managing managers", 10),
    ("Requires 8-12 years in consumer tech", 8),
    ("minimum 7 years experience", 7),
    ("We were founded 120 years ago; 6+ years required", 6),
    ("Salary $185,000 - $250,000 per year", None),
    ("No experience requirement stated", None),
])
def test_required_years(text, years):
    assert required_years(text) == years


def test_experience_track_titles_need_6_to_20_years(flt):
    def job(title, description):
        return Job("greenhouse", title + description, "Airbnb", title, "Seattle, WA", description=description)

    assert flt.title_level("Product Lead, Payments") == "experience"
    assert flt.title_level("Director, Product") == "senior"
    assert flt.accept(job("Product Lead, Payments", "8+ years of product management experience"))
    assert flt.accept(job("Strategy & Operations Lead", "10-15 years in consulting or tech"))
    assert flt.accept(job("Senior Product Manager, Checkout", "You have 6+ years of experience"))
    assert not flt.accept(job("Senior Product Manager, Checkout", "3+ years of experience"))
    assert not flt.accept(job("Business Operations Manager", "No years mentioned"))
    # senior titles don't depend on the years asked
    assert flt.accept(job("Head of Growth", "3+ years of experience"))
