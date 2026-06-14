"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string to filter by (case-insensitive), or None.
        max_price:   Maximum price (inclusive), or None.

    Returns:
        A list of matching listing dicts sorted by relevance (highest first).
        Returns [] if nothing matches — does NOT raise an exception.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Step 1: Filter by price
    if max_price is not None:
        listings = [item for item in listings if item["price"] < max_price]

    # Step 2: Filter by size
    # For numeric sizes (shoe sizes), match the exact number so "9" doesn't
    # match when the user asked for "12". For letter sizes (S/M/L), use
    # substring so "M" matches "S/M" and "M/L".
    if size is not None:
        size_lower = size.lower()

        def size_matches(item_size: str) -> bool:
            item_lower = item_size.lower()
            if size_lower.isdigit() or size_lower.replace(".", "").isdigit():
                # Numeric: require the number to appear as a whole word/token
                # so "8" matches "US 8" and "8.5" but NOT "US 9" or "18"
                import re as _re
                return bool(_re.search(r'(?<!\d)' + _re.escape(size_lower) + r'(?!\d)', item_lower))
            else:
                # Letter size: substring is fine ("M" matches "S/M", "M/L")
                return size_lower in item_lower

        listings = [item for item in listings if size_matches(item["size"])]

    # Step 3: Score by keyword overlap with description.
    keywords = description.lower().split()
    phrase = description.lower()

    # Map common user terms to dataset category values so "skirt", "jeans",
    # "jacket" etc. correctly boost items in the right category.
    CATEGORY_MAP = {
        "skirt": "bottoms", "dress": "bottoms", "jeans": "bottoms",
        "pants": "bottoms", "trousers": "bottoms", "shorts": "bottoms",
        "tee": "tops", "shirt": "tops", "top": "tops", "blouse": "tops",
        "sweater": "tops", "hoodie": "tops", "sweatshirt": "tops",
        "cardigan": "tops", "vest": "tops",
        "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear",
        "shacket": "outerwear", "windbreaker": "outerwear", "bomber": "outerwear",
        "sneakers": "shoes", "boots": "shoes", "heels": "shoes",
        "loafers": "shoes", "sandals": "shoes", "shoes": "shoes",
        "bag": "accessories", "belt": "accessories", "hat": "accessories",
        "scarf": "accessories",
    }

    def score(item):
        searchable = " ".join([
            item["title"].lower(),
            item["description"].lower(),
            " ".join(tag.lower() for tag in item["style_tags"]),
            item["category"].lower(),
        ])
        # Base score: individual keyword matches
        base = sum(1 for kw in keywords if kw in searchable)
        # Phrase bonus: only award if phrase is a genuine substring match
        phrase_bonus = 1 if phrase in searchable else 0
        # Category bonus: user said "skirt" → only bottoms get the bonus
        mapped_categories = {CATEGORY_MAP[kw] for kw in keywords if kw in CATEGORY_MAP}
        category_bonus = 3 if item["category"].lower() in mapped_categories else 0
        return base + phrase_bonus + category_bonus

    scored = [(item, score(item)) for item in listings]

    # Step 4: Drop items with zero keyword matches
    scored = [(item, s) for item, s in scored if s > 0]

    # Step 5: Shuffle within each score tier so equal-ranked items vary,
    # then sort by score descending. Genuinely better matches still rise to
    # the top, but ties don't always return the same item first.
    import random
    random.shuffle(scored)
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions or general styling advice.
    """
    fallback = (
        "This piece works well with simple basics — try pairing it with "
        "straight-leg jeans and white sneakers for an easy everyday look."
    )

    try:
        client = _get_groq_client()
        wardrobe_items = wardrobe.get("items", [])

        item_summary = (
            f"Item: {new_item['title']}\n"
            f"Category: {new_item['category']}\n"
            f"Colors: {', '.join(new_item['colors'])}\n"
            f"Style tags: {', '.join(new_item['style_tags'])}\n"
            f"Description: {new_item['description']}"
        )

        if not wardrobe_items:
            # Empty wardrobe — give general styling advice
            prompt = (
                f"A user is considering buying this secondhand item:\n\n"
                f"{item_summary}\n\n"
                "They haven't described their wardrobe yet. Give them 2–3 sentences "
                "of general styling advice: what kinds of pieces pair well with this item, "
                "what vibe or aesthetic it suits, and one specific styling tip. "
                "Keep it casual and direct — like advice from a stylish friend."
            )
        else:
            # Build wardrobe summary
            wardrobe_lines = "\n".join(
                f"- {w['name']} ({w['category']}, {', '.join(w['colors'])})"
                + (f" — {w['notes']}" if w.get("notes") else "")
                for w in wardrobe_items
            )
            prompt = (
                f"A user is considering buying this secondhand item:\n\n"
                f"{item_summary}\n\n"
                f"Their current wardrobe includes:\n{wardrobe_lines}\n\n"
                "Suggest 1–2 complete outfit combinations using the new item plus specific "
                "named pieces from their wardrobe. Be specific about which wardrobe pieces "
                "to use and give a brief styling note for each outfit. "
                "Keep the tone casual, like a stylish friend texting you outfit ideas."
            )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.choices[0].message.content.strip()
        return result if result else fallback

    except Exception:
        return fallback


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence casual caption string.
        Returns a descriptive error message string if outfit is empty.
    """
    if not outfit or not outfit.strip():
        return "Unable to generate fit card: outfit description was empty."

    try:
        client = _get_groq_client()

        title = new_item.get("title", "this piece")
        price = new_item.get("price", "")
        platform = new_item.get("platform", "a thrift app")

        price_str = f"${price:.2f}" if isinstance(price, (int, float)) else str(price)

        prompt = (
            f"Write a 2–4 sentence Instagram/TikTok OOTD caption for this outfit:\n\n"
            f"Thrifted item: {title} — {price_str} from {platform}\n"
            f"Outfit: {outfit}\n\n"
            "Rules:\n"
            "- Sound like a real person posting their outfit, NOT a product description\n"
            "- Mention the item name, price, and platform naturally — once each\n"
            "- Capture the specific vibe of this outfit in casual language\n"
            "- Can include 1–2 relevant emojis if they fit naturally\n"
            "- Do NOT use hashtags\n"
            "- Make it feel fresh and specific to THIS outfit, not generic"
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            temperature=1.2,
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.choices[0].message.content.strip()
        return result if result else "Unable to generate fit card: something went wrong generating the caption."

    except Exception:
        return "Unable to generate fit card: something went wrong generating the caption."