# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items that match a keyword description, an optional size filter, and an optional maximum price. Returns a ranked list of matching listing dicts, best match first.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for (e.g., "vintage graphic tee"). Used for keyword scoring against title, description, and style_tags.
- `size` (str | None): Size string to filter by, case-insensitive (e.g., "M" should match "S/M", "M/L"). Pass None to skip size filtering.
- `max_price` (float | None): Maximum price (inclusive). Pass None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains:
`id`, `title`, `description`, `category`, `style_tags` (list[str]), `size`, `condition`, `price` (float), `colors` (list[str]), `brand` (str or None), `platform`.
Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to: "No listings found for that search. Try broader keywords, a different size, or a higher price limit." It returns the session early without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item and the user's wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations using specific named pieces from the wardrobe. If the wardrobe is empty, returns general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A listing dict — the item the user is considering buying. Uses fields: `title`, `category`, `style_tags`, `colors`, `description`.
- `wardrobe` (dict): A wardrobe dict with an `items` key (list of wardrobe item dicts). Each wardrobe item has: `name`, `category`, `colors`, `style_tags`, `notes`.

**What it returns:**
A non-empty string with 1–2 outfit suggestions. If the wardrobe is empty, returns general styling advice (what kinds of pieces pair well, what vibe the item suits). Never returns an empty string or raises an exception.

**What happens if it fails or returns nothing:**
If the LLM call fails or returns an empty response, returns the fallback string: "This piece works well with simple basics — try pairing it with straight-leg jeans and white sneakers for an easy everyday look."

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM to generate a short, casual, shareable outfit caption (2–4 sentences) — the kind of thing someone would use as an Instagram or TikTok OOTD caption. Uses a higher temperature for variety.

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

1. **Parse query**: Extract `description`, `size`, and `max_price` from the user's natural language query using regex patterns. Store in `session["parsed"]`.

2. **Call `search_listings`**: Pass parsed parameters. Store result in `session["search_results"]`.
   - **If `search_results` is empty**: Set `session["error"]` to a helpful message explaining what to try differently. Return the session immediately. Do NOT proceed.
   - **If `search_results` is non-empty**: Set `session["selected_item"] = search_results[0]` (top result). Continue.

3. **Call `suggest_outfit`**: Pass `session["selected_item"]` and `session["wardrobe"]`. Store the returned string in `session["outfit_suggestion"]`.

4. **Call `create_fit_card`**: Pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store the returned string in `session["fit_card"]`.

5. **Return session**: The agent is done. All three output fields are populated.

The agent never calls `suggest_outfit` or `create_fit_card` with empty/None inputs. It stops at the first failure and communicates clearly what went wrong.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. Fields:

| Field | Set by | Used by |
|---|---|---|
| `query` | `_new_session()` | parse step |
| `parsed` | parse step | `search_listings` call |
| `search_results` | `search_listings` | selected_item assignment |
| `selected_item` | planning loop (results[0]) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session()` (passed in) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | returned to caller / UI |
| `error` | planning loop on failure | returned to caller / UI |

No tool reads from the session dict directly — the planning loop extracts the relevant value and passes it as an argument. This keeps tools testable in isolation.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` = "No listings found for that search. Try broader keywords, a different size, or a higher price limit." Returns session early — suggest_outfit is never called. |
| suggest_outfit | Wardrobe is empty | Calls LLM with a general styling prompt for the item alone (no wardrobe needed). Returns general advice string rather than crashing. |
| create_fit_card | Outfit input is missing or empty string | Returns the string "Unable to generate fit card: outfit description was empty." — does not raise an exception. |

---

## Architecture

```
User query (natural language)
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─ Step 1: Parse query → session["parsed"]
    │          (regex extract: description, size, max_price)
    │
    ├─ Step 2: search_listings(description, size, max_price)
    │               │
    │               ├── results == [] ──► session["error"] = "No listings found..."
    │               │                    return session  ◄─── EARLY EXIT
    │               │
    │               └── results non-empty
    │                       │
    │                   session["search_results"] = results
    │                   session["selected_item"]  = results[0]
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
                    └── outfit present ─► LLM: casual caption
                            │
                        session["fit_card"] = result
                            │
                            ▼
                        return session
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings**: Give Claude the Tool 1 spec block (inputs, return value, failure mode) and ask it to implement the function body using `load_listings()` from `utils/data_loader.py`. Verify the generated code: (a) filters by both `max_price` and `size` only when those params are not None, (b) scores by keyword overlap across `title`, `description`, and `style_tags`, (c) returns `[]` on no match — not None, not an exception. Test with 3 queries before trusting it.

- **suggest_outfit**: Give Claude the Tool 2 spec block and ask it to implement the function using the Groq client from `_get_groq_client()`. Verify the generated code handles the empty wardrobe branch and formats the wardrobe items list into a readable prompt string. Test with both an empty wardrobe and the example wardrobe.

- **create_fit_card**: Give Claude the Tool 3 spec block and ask it to implement the function with `temperature=1.2` (for variety). Verify the empty-outfit guard is present and returns a string (not raises). Run 3 times on the same input and confirm outputs differ.

**Milestone 4 — Planning loop and state management:**

Give Claude the full Architecture diagram above plus the Planning Loop and State Management sections. Ask it to implement `run_agent()` in `agent.py` following the numbered steps in the file's TODO. Verify the generated code: (a) branches on `search_results == []` and returns early, (b) stores values in the session dict at each step (not local variables), (c) does NOT call all three tools unconditionally. Run the CLI test in `agent.py` with both the happy path and the impossible query to confirm branching works.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query using regex:
- `description` = "vintage graphic tee"
- `size` = None (not mentioned)
- `max_price` = 30.0 (extracted from "under $30")

Calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`.

Returns 2 matches (both under $30, both matching "vintage" + "graphic tee" in tags):
- `lst_006`: "Graphic Tee — 2003 Tour Bootleg Style" — $24, depop (score: 3)
- `lst_033`: "Vintage Band Tee — Faded Grey" — $19, depop (score: 3)

`session["selected_item"]` = lst_006 (first result).

**Step 2:**
Calls `suggest_outfit(new_item=lst_006, wardrobe=example_wardrobe)`.

The wardrobe is non-empty (10 items), so the LLM receives the new item details and the wardrobe list. It returns something like:

"Pair the boxy 2003 Tour tee with your baggy dark-wash jeans and chunky white sneakers — tuck the front corner slightly and let the rest hang loose for that broken-in 90s feel. Or layer it over your white ribbed tank and wear it with the black combat boots for a grungier take."

`session["outfit_suggestion"]` = above string.

**Step 3:**
Calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=lst_006)`.

The LLM returns a caption like:

"snagged this faded 2003 tour tee off depop for $24 and it immediately earned a permanent spot in the rotation 🖤 baggy jeans + chunky sneakers and suddenly i'm back in 2003. full look details in my stories"

`session["fit_card"]` = above string.

**Final output to user:**
Three panels populate in the UI:
- 🛍️ **Top listing**: "Graphic Tee — 2003 Tour Bootleg Style | $24.00 | depop | Size: L | Condition: good"
- 👗 **Outfit idea**: The suggest_outfit string above
- ✨ **Fit card**: The caption string above

**Error path example:**
If the user queries "designer ballgown size XXS under $5", `search_listings` returns `[]`. The agent sets `session["error"]` = "No listings found for that search. Try broader keywords, a different size, or a higher price limit." and returns. `suggest_outfit` and `create_fit_card` are never called. The UI shows the error message in the first panel and leaves the other two empty.