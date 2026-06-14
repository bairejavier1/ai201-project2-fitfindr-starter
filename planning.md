# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items that match a keyword description, an optional size filter, and an optional maximum price. Returns a ranked list of matching listing dicts, best match first. Items with equal scores are shuffled so ties don't always return the same item.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for (e.g., "vintage graphic tee"). Scored against title, description, style_tags, category, and colors.
- `size` (str | None): Size string to filter by, case-insensitive. Numeric sizes use whole-word matching so "8" matches "US 8" but not "US 18". Letter sizes use substring matching so "M" matches "S/M". Pass None to skip size filtering.
- `max_price` (float | None): Maximum price (strictly less than). Pass None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Scoring uses:
- Base score: individual keyword matches across title, description, style_tags, category, colors
- Phrase bonus: +1 if the full description phrase appears as a substring
- Category bonus: +3 if a query keyword maps to the item's category via CATEGORY_MAP (e.g. "boots" → "shoes")

Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list[str]), `size`, `condition`, `price` (float), `colors` (list[str]), `brand` (str or None), `platform`.
Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent runs `_search_with_fallback` which retries up to 4 times with progressively relaxed constraints before giving up.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item and the user's wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations using specific named pieces from the wardrobe. If the wardrobe is empty, returns general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A listing dict — the item the user is considering buying. Uses fields: `title`, `category`, `style_tags`, `colors`, `description`.
- `wardrobe` (dict): A wardrobe dict with an `items` key (list of wardrobe item dicts). Each wardrobe item has: `name`, `category`, `colors`, `style_tags`, `notes`.

**What it returns:**
A non-empty string with 1–2 outfit suggestions. If the wardrobe is empty, returns general styling advice. Never returns an empty string or raises an exception.

**What happens if it fails or returns nothing:**
If the LLM call fails or returns an empty response, returns the fallback string: "This piece works well with simple basics — try pairing it with straight-leg jeans and white sneakers for an easy everyday look."

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM (temperature=1.2) to generate a short, casual, shareable outfit caption (2–4 sentences) — the kind of thing someone would use as an Instagram or TikTok OOTD caption.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit()`.
- `new_item` (dict): The listing dict for the thrifted item. Uses: `title`, `price`, `platform`.

**What it returns:**
A 2–4 sentence string that feels like an authentic social media caption: casual tone, mentions the item name/price/platform naturally once each, captures the outfit vibe in specific terms. Returns a descriptive error message string if `outfit` is empty — never raises an exception.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, returns: "Unable to generate fit card: outfit description was empty." If the LLM call fails, returns: "Unable to generate fit card: something went wrong generating the caption."

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop runs sequentially with conditional branching based on what each tool returns:

1. **Parse query**: Extract `description`, `size`, and `max_price` from the user's natural language query using regex patterns. Supports formats like `under $30`, `30$`, `size M`, `US 8`. Store in `session["parsed"]`.

2. **Call `_search_with_fallback`**: Tries `search_listings` up to 4 times with progressively relaxed constraints:
   - Attempt 1: exact description + size + price
   - Attempt 2: drop size filter, keep price → note explains closest available size
   - Attempt 3: drop price filter, keep size → note shows actual price of result
   - Attempt 4: drop both filters → note explains both were removed
   - **If all attempts return empty**: set `session["error"]` with a helpful message (includes brand name tip if applicable) and return early. Do NOT proceed.
   - **If any attempt succeeds**: set `session["selected_item"] = results[0]`, store `fallback_note`, and continue.

3. **Call `suggest_outfit`**: Pass `session["selected_item"]` and `session["wardrobe"]`. Store the returned string in `session["outfit_suggestion"]`.

4. **Call `create_fit_card`**: Pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store the returned string in `session["fit_card"]`.

5. **Return session**: All three output fields are populated.

The agent never calls `suggest_outfit` or `create_fit_card` with empty/None inputs.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call.

| Field | Set by | Used by |
|---|---|---|
| `query` | `_new_session()` | parse step |
| `parsed` | `_parse_query()` | `_search_with_fallback` call |
| `search_results` | fallback search | selected_item assignment |
| `selected_item` | planning loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session()` (passed in) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` result | `create_fit_card` |
| `fit_card` | `create_fit_card` result | returned to UI |
| `fallback_note` | `_search_with_fallback` | displayed in listing panel |
| `error` | planning loop on failure | returned to UI |

No tool reads from the session dict directly — the planning loop extracts values and passes them as arguments, keeping tools independently testable.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results after all 4 fallback attempts | Sets `session["error"]` with a helpful message. If query contains a known brand name (Nike, Adidas, etc.), adds a tip to describe style instead. Returns session early — suggest_outfit is never called. |
| search_listings | Results found but wrong size/color/style | `app.py` detects mismatches and shows a specific ⚠️ warning (e.g. "No black combat boots found — this is the closest available match."). One Size / Oversized results include a note to check measurements. |
| suggest_outfit | Wardrobe is empty | Calls LLM with a general styling prompt. Returns general advice string — never crashes. |
| create_fit_card | Outfit input is missing or empty string | Returns "Unable to generate fit card: outfit description was empty." — does not raise an exception. |

---

## Architecture

```
User query (natural language)
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─ Step 1: _parse_query() → session["parsed"]
    │          regex: description, size (US sizes + letter sizes), max_price
    │          supports: "under $30", "30$", "size M", "US 8", "size US 9"
    │
    ├─ Step 2: _search_with_fallback(description, size, max_price)
    │               │
    │               ├── Attempt 1: exact (size + price)
    │               ├── Attempt 2: drop size ──► fallback_note: size unavailable
    │               ├── Attempt 3: drop price ─► fallback_note: price + actual cost
    │               ├── Attempt 4: drop both ──► fallback_note: both removed
    │               │
    │               ├── all empty ──► session["error"] = helpful message
    │               │                return session  ◄─── EARLY EXIT
    │               │
    │               └── results found
    │                       │
    │                   session["search_results"] = results
    │                   session["selected_item"]  = results[0]
    │                   session["fallback_note"]  = note or None
    │
    ├─ Step 3: suggest_outfit(selected_item, wardrobe)
    │               │
    │               ├── wardrobe empty ──► LLM: general styling advice
    │               └── wardrobe present ─► LLM: specific outfit combinations
    │                       │
    │                   session["outfit_suggestion"] = result
    │
    └─ Step 4: create_fit_card(outfit_suggestion, selected_item)
                    │
                    ├── outfit empty ──► return error string (no exception)
                    └── outfit present ─► LLM: casual caption (temp=1.2)
                            │
                        session["fit_card"] = result
                            │
                            ▼
                        return session

app.py post-processing (after run_agent returns):
    ├── fallback_note present ──► prepend ⚠️ to listing panel
    ├── wrong category returned ─► ⚠️ "No exact match — closest result shown"
    ├── color mismatch ──────────► ⚠️ "No [color] version found"
    ├── style mismatch ──────────► ⚠️ "No [style] found in dataset"
    └── One Size result ─────────► ⚠️ "Fits most — check measurements"
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings**: Gave Claude the Tool 1 spec block (inputs, return value, failure mode, instruction to use `load_listings()`) and asked it to implement the function body. Verified: (a) filters by `max_price` and `size` only when not None, (b) scores by keyword overlap across title, description, style_tags, (c) returns `[]` on no match. Tested with 3 queries. Later extended with CATEGORY_MAP scoring, phrase bonus, category bonus, and score-tier shuffling after observing poor results in testing.

- **suggest_outfit**: Gave Claude the Tool 2 spec block and asked it to implement using `_get_groq_client()`. Verified the empty wardrobe branch and wardrobe formatting. Tested with both empty and example wardrobe.

- **create_fit_card**: Gave Claude the Tool 3 spec block with `temperature=1.2`. Verified empty-outfit guard returns a string not an exception. Ran 3 times to confirm outputs vary.

**Milestone 4 — Planning loop and state management:**

Gave Claude the full architecture diagram plus Planning Loop and State Management sections to implement `run_agent()`. Verified: (a) branches on empty results and returns early, (b) stores values in session dict, (c) does not call all three tools unconditionally. Extended with `_search_with_fallback` after testing showed dead-end errors were poor UX.

**Stretch feature — Retry logic with fallback:**

Implemented `_search_with_fallback` in `agent.py` with 4 progressive attempts. Each failed attempt generates a specific `fallback_note` explaining what was relaxed and what the closest match costs.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query using regex:
- `description` = "vintage graphic tee"
- `size` = None (not mentioned)
- `max_price` = 30.0 (extracted from "under $30")

Calls `_search_with_fallback("vintage graphic tee", size=None, max_price=30.0)`.
Attempt 1 succeeds — returns items matching "vintage" + "graphic" + "tee" under $30.
`session["selected_item"]` = top result (e.g. "Graphic Tee — 2003 Tour Bootleg Style", $24, depop).

**Step 2:**
Calls `suggest_outfit(new_item=selected_item, wardrobe=example_wardrobe)`.
Wardrobe is non-empty (10 items) → LLM returns specific outfit combinations using named wardrobe pieces.
`session["outfit_suggestion"]` = outfit string.

**Step 3:**
Calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=selected_item)`.
LLM returns a casual 2–4 sentence caption mentioning item name, price, and platform.
`session["fit_card"]` = caption string.

**Final output to user:**
- 🛍️ **Top listing**: formatted item details with price, platform, size, condition, description, tags
- 👗 **Outfit idea**: specific outfit combinations from suggest_outfit
- ✨ **Fit card**: casual social media caption from create_fit_card

**Error path example:**
Query "designer ballgown size XXS under $5" → all 4 fallback attempts fail → `session["error"]` = "No listings found... Try describing the style or category." → UI shows error in panel 1, panels 2 and 3 stay empty.

**Fallback path example:**
Query "graphic tee size XXS under $5" → attempts 1–3 fail → attempt 4 (drop both filters) succeeds → listing panel shows ⚠️ note explaining size and price were removed, along with the actual item price.