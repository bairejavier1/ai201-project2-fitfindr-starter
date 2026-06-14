"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "fallback_note": None,   # explains any relaxed constraints to the user
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    text = query

    max_price = None
    price_patterns = [
        r"under\s+\$?([\d.]+)",       # under $30 or under 30
        r"under\s+([\d.]+)\s*\$",     # under 30$
        r"\$?([\d.]+)\s+or\s+less",   # $30 or less
        r"([\d.]+)\$\s+or\s+less",    # 30$ or less
        r"less\s+than\s+\$?([\d.]+)", # less than $30
        r"less\s+than\s+([\d.]+)\$",  # less than 30$
        r"max\s+\$?([\d.]+)",         # max $30
        r"up\s+to\s+\$?([\d.]+)",     # up to $30
        r"up\s+to\s+([\d.]+)\$",      # up to 30$
        r"\b([\d.]+)\s*\$",           # 30$ (standalone, catch-all — must be last)
    ]
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            max_price = float(match.group(1))
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            break

    size = None
    size_patterns = [
        # "size US 8", "size US8"
        r"\bsize\s+US\s*(\d+(?:\.\d+)?)\b",
        # "US 8", "US8" standalone
        r"\bUS\s*(\d+(?:\.\d+)?)\b",
        # "size M", "size XL", "size S/M"
        r"\bsize\s+([A-Z]{1,3}(?:\/[A-Z]{1,3})?)\b",
        # "size 8", "size 12"
        r"\bsize\s+(\d+(?:\.\d+)?)\b",
        # "in size M"
        r"\bin\s+size\s+([A-Z]{1,3}(?:\/[A-Z]{1,3})?|\d+(?:\.\d+)?)\b",
        # standalone letter sizes
        r"\b(XS|S|M|L|XL|XXL|XXXL)\b",
    ]
    for pattern in size_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            size = match.group(1).upper()
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            break

    filler = [
        r"i'?m\s+looking\s+for\s+",
        r"looking\s+for\s+",
        r"find\s+me\s+",
        r"i\s+want\s+",
        r"i\s+need\s+",
        r"any\s+",
        r"some\s+",
        r"a\s+",
        r"an\s+",
    ]
    for f in filler:
        text = re.sub(f, " ", text, flags=re.IGNORECASE)

    description = " ".join(text.split()).strip(" .,?!")
    if not description:
        description = query

    return {"description": description, "size": size, "max_price": max_price}


# ── fallback search ───────────────────────────────────────────────────────────

def _search_with_fallback(description: str, size, max_price) -> tuple[list, str | None]:
    """
    Try search_listings with progressively relaxed constraints.
    Returns (results, fallback_note) — fallback_note is None if original search succeeded.
    """
    # Attempt 1: exact constraints
    results = search_listings(description, size=size, max_price=max_price)
    if results:
        return results, None

    # Attempt 2: drop size filter (keep price)
    if size is not None:
        results = search_listings(description, size=None, max_price=max_price)
        if results:
            top_size = results[0]["size"].lower()
            if "one size" in top_size or "oversized" in top_size:
                note = (
                    f"No items explicitly labeled size {size} — "
                    f"top result is One Size / Oversized which fits most — check the listing for exact measurements before buying."
                )
            else:
                note = (
                    f"No exact matches for size {size} — "
                    f"showing closest available size ({results[0]['size']}) instead."
                )
            return results, note

    # Attempt 2b: no size was specified but still no results — just return None
    # (fall through to price/both attempts below)

    # Attempt 3: drop price filter (keep size)
    if max_price is not None:
        results = search_listings(description, size=size, max_price=None)
        if results:
            size_note = f" in size {size}" if size else ""
            top_price = results[0]["price"]
            return results, (
                f"Nothing found{size_note} under ${max_price:.0f} — "
                f"closest match is ${top_price:.2f} (showing results at any price)."
            )

    # Attempt 4: drop both filters
    if size is not None and max_price is not None:
        results = search_listings(description, size=None, max_price=None)
        if results:
            top_price = results[0]["price"]
            return results, (
                f"No exact matches for size {size} under ${max_price:.0f} — "
                f"closest match is ${top_price:.2f} (your size and price filters were removed to find this)."
            )

    return [], None


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    session = _new_session(query, wardrobe)

    parsed = _parse_query(query)
    session["parsed"] = parsed

    results, fallback_note = _search_with_fallback(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results
    session["fallback_note"] = fallback_note

    if not results:
        desc = parsed["description"].lower()
        known_brands = ["nike", "adidas", "gucci", "prada", "zara", "balenciaga", "supreme"]
        brand_tip = ""
        if any(brand in desc for brand in known_brands):
            brand_tip = (
                " Brand names aren't in this dataset — try describing the style instead "
                "(e.g. 'chunky sneakers' or 'running shoes' instead of 'Nike shoes')."
            )
        session["error"] = (
            "No listings found for that search, even after broadening the filters."
            + brand_tip
            + " Try describing the style or category — e.g. 'chunky sneakers', "
            "'leather boots', 'graphic tee', or 'track jacket'."
        )
        return session

    session["selected_item"] = results[0]
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path ===\n")
    s = run_agent("looking for a vintage graphic tee under $30", get_example_wardrobe())
    if s["error"]:
        print(f"Error: {s['error']}")
    else:
        if s["fallback_note"]:
            print(f"⚠️  Note: {s['fallback_note']}\n")
        print(f"Found: {s['selected_item']['title']} — ${s['selected_item']['price']}")

    print("\n=== Fallback: tight constraints ===\n")
    s2 = run_agent("graphic tee size XXS under $5", get_example_wardrobe())
    if s2["error"]:
        print(f"Error: {s2['error']}")
    else:
        print(f"⚠️  Note: {s2['fallback_note']}")
        print(f"Found: {s2['selected_item']['title']}")

    print("\n=== True no-results ===\n")
    s3 = run_agent("designer ballgown", get_example_wardrobe())
    print(f"Error: {s3['error']}")