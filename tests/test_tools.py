"""
tests/test_tools.py

Run with: pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)

def test_search_size_filter():
    results = search_listings("tee", size="M", max_price=None)
    # All results should have 'M' (case-insensitive) in their size string
    assert all("m" in item["size"].lower() for item in results)

def test_search_returns_list_on_bad_query():
    results = search_listings("xyzzy impossiblethingthatdoesntexist")
    assert isinstance(results, list)
    assert results == []

def test_search_results_are_dicts_with_expected_fields():
    results = search_listings("vintage", size=None, max_price=100)
    assert len(results) > 0
    for item in results:
        assert "id" in item
        assert "title" in item
        assert "price" in item
        assert "platform" in item


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 10  # non-empty, meaningful response

def test_suggest_outfit_empty_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 10  # should return general advice, not crash

def test_suggest_outfit_does_not_raise():
    # Should never raise even with minimal item data
    minimal_item = {
        "title": "Test Tee",
        "category": "tops",
        "style_tags": ["vintage"],
        "colors": ["black"],
        "description": "A test tee.",
    }
    result = suggest_outfit(minimal_item, get_empty_wardrobe())
    assert isinstance(result, str)


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert "unable" in result.lower() or "empty" in result.lower()

def test_create_fit_card_whitespace_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert "unable" in result.lower() or "empty" in result.lower()

def test_create_fit_card_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    outfit = "Pair with baggy jeans and chunky sneakers for a 90s look."
    result = create_fit_card(outfit, results[0])
    assert isinstance(result, str)
    assert len(result) > 10

def test_create_fit_card_does_not_raise():
    minimal_item = {"title": "Test Tee", "price": 20.0, "platform": "depop"}
    result = create_fit_card("Some outfit description here.", minimal_item)
    assert isinstance(result, str)