from career_agents.compass import tools
from career_agents.scout import cli as scout_cli


def test_compass_tools_have_schemas():
    for tool in tools.CLIENT_TOOLS:
        param = tool.to_dict()
        assert param["name"] and param["description"] and param["input_schema"]["type"] == "object"


def test_notes_round_trip():
    assert tools.save_note.call({"topic": "decision", "note": "Target Seattle via Amazon"}) == "Saved."
    assert "Target Seattle" in tools.read_notes.call({"topic": "decision"})
    assert tools.read_notes.call({"topic": "other"}) == "No notes on that topic."


def test_scout_list_on_empty_store(capsys):
    scout_cli.main(["list"])
    assert "Nothing matches" in capsys.readouterr().out


def test_scout_add_then_duplicate(capsys):
    import pytest

    scout_cli.main(["add", "--company", "Uber", "--title", "Director, Product", "--url", "https://u/1"])
    assert "added" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        scout_cli.main(["add", "--company", "Uber", "--title", "Director, Product", "--url", "https://u/1"])
    scout_cli.main(["list"])
    assert "Director, Product" in capsys.readouterr().out
