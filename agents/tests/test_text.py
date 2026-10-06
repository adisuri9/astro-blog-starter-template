from career_agents.text import html_to_text, iso_date, norm


def test_html_to_text_handles_escaped_html_and_lists():
    html = "&lt;p&gt;Own the &amp;amp; P&amp;L&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Grow GMV&lt;/li&gt;&lt;li&gt;Hire&lt;/li&gt;&lt;/ul&gt;"
    assert html_to_text(html) == "Own the & P&L\n\n- Grow GMV\n- Hire"


def test_iso_date_shapes():
    assert iso_date("2026-09-30T10:00:00Z") == "2026-09-30"
    assert iso_date("2026-09-30T10:00:00.123-04:00") == "2026-09-30"
    assert iso_date("September 30, 2026") == "2026-09-30"
    assert iso_date(1790000000000) == "2026-09-21"
    assert iso_date(float("nan")) is None
    assert iso_date("") is None


def test_norm():
    assert norm("Head of Product — Fresh!") == "head of product fresh"
