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

Searches the mock listings dataset for items matching a keyword description, with optional size and price filters. Keyword scoring checks each listing's title, description, and style_tags for overlap with the query keywords. Items with equal scores are shuffled before sorting, so genuinely better matches still rise to the top but ties don't always return the same item first. Returns an empty list if nothing matches — never raises an exception.

Each result dict contains: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

Calls the Groq LLM to suggest 1–2 complete outfit combinations using the thrifted item and named pieces from the user's wardrobe. If the wardrobe is empty, returns general styling advice for the item instead. Never returns an empty string or raises an exception — falls back to a hardcoded tip if the LLM call fails.

Returns a non-empty string.

### `create_fit_card(outfit: str, new_item: dict) → str`

Calls the Groq LLM (temperature=1.2) to generate a 2–4 sentence casual Instagram/TikTok-style caption for the outfit. Mentions the item name, price, and platform naturally. Guards against an empty `outfit` argument — returns a descriptive error string rather than crashing. Higher temperature ensures the output varies for different inputs.

Returns a non-empty string.

---

## How the Planning Loop Works

The loop in `run_agent()` runs sequentially with one conditional branch:

1. **Parse** the user's natural language query using regex to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.

2. **Call `_search_with_fallback`** which tries `search_listings` up to 4 times with progressively relaxed constraints:
   - Attempt 1: exact description + size + price
   - Attempt 2: drop size filter, keep price
   - Attempt 3: drop price filter, keep size
   - Attempt 4: drop both filters
   - If all attempts return empty: set `session["error"]` and **return early** — `suggest_outfit` and `create_fit_card` are never called.
   - If any attempt succeeds: store results and a `fallback_note` explaining what was relaxed, then continue.

3. **Call `suggest_outfit`** with the selected item and wardrobe. Store the string in `session["outfit_suggestion"]`.

4. **Call `create_fit_card`** with the outfit string and selected item. Store in `session["fit_card"]`.

5. **Return the session dict.**

The key conditional is step 2: the agent's behavior changes based on what the search returns. It never calls all three tools unconditionally.

---

## State Management

All state is stored in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. No tool reads from the session directly — the planning loop extracts values and passes them as arguments, keeping tools independently testable.

| Field | Set by | Consumed by |
|---|---|---|
| `query` | `_new_session()` | parse step |
| `parsed` | `_parse_query()` | `_search_with_fallback` call |
| `search_results` | fallback search result | selected_item assignment |
| `selected_item` | planning loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session()` (passed in) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` result | `create_fit_card` |
| `fit_card` | `create_fit_card` result | returned to UI |
| `fallback_note` | `_search_with_fallback` | displayed in listing panel |
| `error` | planning loop on empty results | returned to UI |

---

## Error Handling

### `search_listings` — no results
Returns `[]`. The planning loop runs `_search_with_fallback`, which retries up to 4 times with progressively looser constraints (drop size, drop price, drop both). If all attempts fail, `session["error"]` is set with a specific message. If the query contained a known brand name (Nike, Adidas, Gucci, etc.), the error message specifically tells the user that brand names aren't in the dataset and suggests describing the style instead (e.g. "chunky sneakers" instead of "Nike shoes").

**Tested with:** `designer ballgown size XXS under $5` → all 4 fallback attempts fail, helpful error shown. `graphic tee size XXS under $5` → fallback succeeds at attempt 4, listing panel shows ⚠️ note explaining constraints were relaxed.

### `suggest_outfit` — empty wardrobe
Checks `wardrobe.get("items", [])`. If empty, sends the LLM a different prompt asking for general styling advice rather than specific wardrobe pairings. Never crashes or returns an empty string.

**Tested with:** `get_empty_wardrobe()` → confirmed general styling advice returned, no exception.

### `create_fit_card` — empty outfit string
Checks `if not outfit or not outfit.strip()` before calling the LLM. Returns `"Unable to generate fit card: outfit description was empty."` immediately without making an API call.

**Tested with:** `create_fit_card("", results[0])` → confirmed error string returned, no exception raised.

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop description in `planning.md` before coding — specifically the sentence "if results is empty, return the session early — do NOT proceed to suggest_outfit" — made implementing the branch in `run_agent()` completely mechanical. The code matched the spec line for line.

**Two ways implementation diverged from the spec:**

1. **Fallback retry logic was added after initial implementation.** The original spec described a single `search_listings` call with an early exit on empty results. During testing it became clear that returning a dead-end error when constraints were just slightly too tight (e.g. right item, wrong size) was a bad user experience. A `_search_with_fallback` function was added that retries with progressively relaxed constraints, matching the stretch feature described in the project brief.

2. **Score-tier shuffling was added to `search_listings`.** The spec said to sort by relevance score, which initially always returned the same top result for the same query. Since many items share equal scores, always picking `results[0]` felt broken. Shuffling before sorting means ties are broken randomly while genuinely higher-scored items still rank first — a more honest and varied result.

---

## AI Usage

### Instance 1 — `search_listings` implementation
I gave Claude the Tool 1 spec block from `planning.md` (inputs, return value, failure mode, the instruction to use `load_listings()`) and asked it to implement the function body. The generated code had all three filter/score/sort steps and returned `[]` on no match. I verified it filtered by both `max_price` and `size` only when those params were not `None`, and tested it with three queries before trusting it.

### Instance 2 — Planning loop implementation
I gave Claude the full architecture diagram from `planning.md` and both the Planning Loop and State Management sections, and asked it to implement `run_agent()`. I reviewed the generated code to confirm it branched on `search_results == []` before calling `suggest_outfit`, stored values in the `session` dict at each step, and did not call all three tools unconditionally. I then ran the CLI tests in `agent.py` against both the happy path and the impossible query to verify the branching behavior.