"""
app.py — Gradio interface for FitFindr.
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", ""

    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    session = run_agent(query=user_query.strip(), wardrobe=wardrobe)

    if session["error"]:
        return session["error"], "", ""

    item = session["selected_item"]
    brand_str = f" — {item['brand']}" if item.get("brand") else ""

    # Prepend fallback note to listing panel if constraints were relaxed
    fallback_str = ""
    if session.get("fallback_note"):
        fallback_str = f"⚠️  {session['fallback_note']}\n\n"

    # Warn if the result category doesn't match what the user asked for
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
    }
    query_words = user_query.lower().split()
    expected_categories = {CATEGORY_MAP[w] for w in query_words if w in CATEGORY_MAP}
    actual_category = item.get("category", "").lower()

    if expected_categories and actual_category not in expected_categories:
        # Result is in a completely different category than what was asked for
        fallback_str += (
            f"⚠️  No exact match found for your search — "
            f"showing the closest available result. "
            f"Try describing the style more specifically (e.g. 'chelsea boots', 'platform boots', 'ankle boots').\n\n"
        )
    elif expected_categories and actual_category in expected_categories:
        # Right category — check for color and style mismatches
        query_colors = [w for w in query_words if w in ["black","white","brown","tan","red","blue","green","grey","gray","navy","cream","beige"]]
        item_colors = [c.lower() for c in item.get("colors", [])]
        color_mismatch = query_colors and not any(qc in " ".join(item_colors) for qc in query_colors)

        STYLE_MAP = {
            "combat": "combat boots", "chelsea": "chelsea boots",
            "platform": "platform", "ankle": "ankle boots",
            "mary": "mary janes", "sneakers": "sneakers",
            "loafers": "loafers", "heels": "heels",
            "graphic": "graphic tee", "flannel": "flannel",
            "denim": "denim", "leather": "leather",
            "midi": "midi", "mini": "mini", "maxi": "maxi",
        }
        item_searchable = (item.get("title","") + " " + " ".join(item.get("style_tags",[]))).lower()
        style_mismatches = [
            STYLE_MAP[kw] for kw in query_words
            if kw in STYLE_MAP and STYLE_MAP[kw].split()[0] not in item_searchable
        ]

        if color_mismatch and style_mismatches:
            fallback_str += (
                f"⚠️  No {' '.join(query_colors)} {', '.join(style_mismatches)} found in the dataset — "
                f"this is the closest available match.\n\n"
            )
        elif color_mismatch:
            fallback_str += (
                f"⚠️  No {' '.join(query_colors)} version found in the dataset — "
                f"this is the closest available match.\n\n"
            )
        elif style_mismatches:
            fallback_str += (
                f"⚠️  No {', '.join(style_mismatches)} found in the dataset — "
                f"this is the closest available match.\n\n"
            )

    listing_text = (
        f"{fallback_str}"
        f"{item['title']}{brand_str}\n\n"
        f"💵  ${item['price']:.2f}  |  {item['platform'].capitalize()}\n"
        f"📏  Size: {item['size']}\n"
        f"✅  Condition: {item['condition'].capitalize()}\n\n"
        f"{item['description']}\n\n"
        f"🏷️  Tags: {', '.join(item['style_tags'])}"
    )

    return listing_text, session["outfit_suggestion"], session["fit_card"]


EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(label="🛍️ Top listing found", lines=8, interactive=False)
            outfit_output = gr.Textbox(label="👗 Outfit idea", lines=8, interactive=False)
            fitcard_output = gr.Textbox(label="✨ Your fit card", lines=8, interactive=False)

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()