# FitFindr 🛍️

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. Built with Python, Groq (llama-3.3-70b-versatile), and Gradio.

---

## Setup

```bash
# 1. Clone your fork and activate the virtual environment
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
source .venv/Scripts/activate    # Windows (Git Bash)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Groq API key to a .env file
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Run the app
python app.py
```

Open http://127.0.0.1:7860 in your browser.

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`

Searches the mock listings dataset for items matching a keyword description, with optional size and price filters.

Scoring works on three levels:
- **Base score**: keyword matches across title, description, style_tags, category, and colors
- **Phrase bonus**: +1 if the full description appears as a substring in the item
- **Category bonus**: +3 if a query keyword maps to the item's actual category via a built-in CATEGORY_MAP (e.g. "boots" → "shoes", "skirt" → "bottoms") — this prevents color words like "black" from accidentally promoting the wrong category

Size filtering uses whole-word matching for numeric sizes ("8" matches "US 8" but not "US 18") and substring matching for letter sizes ("M" matches "S/M", "M/L"). Price filtering uses strict less-than so "under $20" excludes items at exactly $20.

Items with equal scores are shuffled before sorting so ties don't always return the same item first.

Returns an empty list if nothing matches — never raises an exception.

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

Calls the Groq LLM to suggest 1–2 complete outfit combinations using the thrifted item and named pieces from the user's wardrobe. If the wardrobe is empty, returns general styling advice instead. Falls back to a hardcoded tip if the LLM call fails. Never returns an empty string or raises an exception.

### `create_fit_card(outfit: str, new_item: dict) → str`

Calls the Groq LLM (temperature=1.2) to generate a 2–4 sentence casual Instagram/TikTok-style caption. Mentions the item name, price, and platform naturally. Guards against an empty `outfit` argument — returns a descriptive error string rather than crashing.

---

## How the Planning Loop Works

The loop in `run_agent()` runs sequentially with one key conditional branch:

1. **Parse** the query using regex to extract `description`, `size`, and `max_price`. Handles formats like `under $30`, `30$`, `size M`, `US 8`, `size US 9`.

2. **Call `_search_with_fallback`** — tries `search_listings` up to 4 times with progressively relaxed constraints:
   - Attempt 1: exact description + size + price
   - Attempt 2: drop size filter, keep price → note explains size unavailable, shows closest available size
   - Attempt 3: drop price filter, keep size → note shows actual price of result so user isn't misled
   - Attempt 4: drop both filters → note explains both were removed and shows actual price
   - **If all attempts fail**: set `session["error"]` with a helpful message and return early — `suggest_outfit` and `create_fit_card` are never called
   - **If any attempt succeeds**: store results, set `fallback_note`, continue

3. **Call `suggest_outfit`** with the selected item and wardrobe.

4. **Call `create_fit_card`** with the outfit suggestion and selected item.

5. **Return the session dict.**

---

## State Management

All state is stored in a single `session` dict initialized at the start of each `run_agent()` call. No tool reads from the session directly — the planning loop extracts values and passes them as arguments, keeping tools independently testable.

| Field | Set by | Consumed by |
|---|---|---|
| `query` | `_new_session()` | parse step |
| `parsed` | `_parse_query()` | `_search_with_fallback` |
| `search_results` | fallback search | selected_item assignment |
| `selected_item` | planning loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session()` (passed in) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | returned to UI |
| `fallback_note` | `_search_with_fallback` | listing panel ⚠️ warning |
| `error` | planning loop on failure | returned to UI |

---

## Error Handling

### `search_listings` — no results after all fallbacks
The planning loop runs `_search_with_fallback` with 4 progressively looser attempts. If all fail, `session["error"]` is set with a specific, actionable message. If the query contains a known brand name (Nike, Adidas, Gucci, etc.), the message specifically says brand names aren't in the dataset and suggests describing the style instead.

**Tested with:** `designer ballgown size XXS under $5` → all 4 attempts fail, error message shown with styling suggestions.

### `search_listings` — results found but wrong size, color, or style
`app.py` runs post-processing checks on the returned item and prepends specific ⚠️ warnings to the listing panel:
- **Wrong category entirely**: "No exact match found — showing closest available result."
- **Right category, wrong color**: "No black version found in the dataset — this is the closest available match."
- **Right category, wrong style**: "No combat boots found in the dataset — this is the closest available match."
- **One Size / Oversized result**: "Fits most — check the listing for exact measurements before buying."
- **Fallback constraints relaxed**: explains exactly what was dropped and what the actual price is.

**Tested with:** `black combat boots` → Platform Mary Janes returned with "No combat boots found" warning. `chunky boots size US 9 under $40` → Canvas Sneakers returned with "No chunky boots found" warning.

### `suggest_outfit` — empty wardrobe
Checks `wardrobe.get("items", [])`. If empty, sends the LLM a prompt for general styling advice rather than specific wardrobe pairings. Never crashes.

**Tested with:** `get_empty_wardrobe()` → general styling advice returned, no exception.

### `create_fit_card` — empty outfit string
Checks `if not outfit or not outfit.strip()` before calling the LLM. Returns a descriptive error string immediately.

**Tested with:** `create_fit_card("", results[0])` → error string returned, no exception.

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop in `planning.md` before coding — specifically "if results is empty, return the session early — do NOT proceed to suggest_outfit" — made the branch in `run_agent()` completely mechanical to implement.

**Ways implementation diverged from the spec:**

1. **Fallback retry logic.** The original spec had a single `search_listings` call with early exit on empty results. Testing showed this was a poor experience when constraints were just slightly too tight. `_search_with_fallback` was added with 4 progressive attempts, each generating a specific note explaining what changed — this also covers the stretch feature from the project brief.

2. **Scoring improvements.** The initial keyword scoring always returned the same top result for the same query, and color words like "black" promoted wrong-category items. A CATEGORY_MAP (phrase bonus + category bonus), score-tier shuffling, and whole-word numeric size matching were all added after observing real search failures during testing.

3. **Price filter changed from `<=` to `<`.** The original implementation used inclusive comparison, so "under $20" returned items at exactly $20. Fixed to strict less-than after noticing the discrepancy during testing.

4. **Style and color mismatch warnings added in `app.py`.** The spec didn't mention post-processing the result for honesty checks. After noticing the agent silently returned wrong-category or wrong-style items, a warning system was added that detects and clearly communicates mismatches to the user.

---

## AI Usage

### Instance 1 — `search_listings` implementation
Gave Claude the Tool 1 spec block from `planning.md` (inputs, return value, failure mode, instruction to use `load_listings()`) and asked it to implement the function body. Verified the generated code filtered by both `max_price` and `size` only when not None, scored by keyword overlap, and returned `[]` on no match. Tested with 3 queries. Later directed Claude to extend the scoring with a CATEGORY_MAP, phrase bonus, and category bonus after observing that color words were incorrectly promoting wrong-category items.

### Instance 2 — Planning loop and fallback logic
Gave Claude the full architecture diagram from `planning.md` plus the Planning Loop and State Management sections to implement `run_agent()`. Reviewed the generated code to confirm it branched correctly on empty results and stored values in the session dict. Later directed Claude to extract the search step into `_search_with_fallback` with 4 progressive attempts, specifying exactly what each fallback note should say and that the actual item price must appear in the note so users aren't misled about what they'll pay.