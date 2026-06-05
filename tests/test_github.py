"""Tests for GitHub signal helpers (pure logic; no network)."""
from piperline.matcher.github import RepoSignal, language_histogram, _topics


def test_language_histogram_counts_and_sorts():
    sigs = [
        RepoSignal(name="a", description=None, url="", homepage=None, primary_language="Python"),
        RepoSignal(name="b", description=None, url="", homepage=None, primary_language="Python"),
        RepoSignal(name="c", description=None, url="", homepage=None, primary_language="Go"),
        RepoSignal(name="d", description=None, url="", homepage=None, primary_language=None),
    ]
    hist = language_histogram(sigs)
    assert hist == {"Python": 2, "Go": 1}
    # sorted descending by count
    assert list(hist.keys())[0] == "Python"


def test_topics_handles_both_shapes():
    assert _topics({"repositoryTopics": [{"name": "ai"}, {"name": "ml"}]}) == ["ai", "ml"]
    assert _topics({"repositoryTopics": ["ai", "ml"]}) == ["ai", "ml"]
    assert _topics({}) == []
