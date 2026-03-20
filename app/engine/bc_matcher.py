"""Matches magnskrá items to BC (Business Central) products."""

import json

from app.engine.ai_client import AIClient
from app.models.schemas import BCProduct, EnrichedItem

SYSTEM_PROMPT = """You are an expert in Icelandic plumbing and HVAC product matching.
You help match items from a construction bill of quantities (magnskrá) to products in a
Business Central (BC) product catalog.

The magnskrá uses technical shorthand (e.g., "PP SN10 - ø110", "PEXa -ø20") while the
BC catalog uses product names and SKUs (e.g., "KÚLULOKI 2\" - IVR", "RF GÓLFHITAGRIND 8+8 - COMISA").

Important notes:
- SKU "1125651" is a placeholder for special orders - these items have the real product
  described in the Lýsing (description) field
- Match based on product type, size, and specifications, not just name similarity
- Some magnskrá items (pipes, fittings) may not have a direct BC match since they are
  commodity items sourced from various suppliers"""

MATCH_PROMPT = """Match the following magnskrá items to the best product from the BC catalog.
Only match items where you are confident the BC product is the correct one.

Magnskrá items to match:
{items_json}

BC Product catalog:
{catalog_json}

Return a JSON array of matches. Each match should have:
- "magnaskra_section_nr": the section number from the magnskrá item
- "bc_sku": the matched BC product SKU (or null if no match)
- "bc_description": the matched BC product description (or null)
- "confidence": 0.0 to 1.0 confidence score
- "notes": brief explanation of the match (in English)

Only include items that have a plausible match. Omit items with no match."""


class BCMatcher:
    """Matches magnskrá items to BC products."""

    def __init__(self, ai_client: AIClient | None = None):
        self.ai = ai_client or AIClient()

    def match_items(
        self,
        enriched_items: list[EnrichedItem],
        bc_products: list[BCProduct],
    ) -> list[EnrichedItem]:
        """Match enriched magnskrá items to BC products."""
        # Build BC catalog lookup
        bc_lookup = {p.sku: p for p in bc_products}

        # Filter to actual line items (not headers)
        line_items = [e for e in enriched_items if not e.magnaskra_item.is_header]

        # Process in batches to stay within token limits
        # Send all items in one call - Sonnet 4.6 has 1M context
        batch_size = 500
        all_matches = {}

        for i in range(0, len(line_items), batch_size):
            batch = line_items[i : i + batch_size]
            batch_matches = self._match_batch(batch, bc_products)
            all_matches.update(batch_matches)

        # Apply matches to enriched items
        for item in enriched_items:
            section_nr = item.magnaskra_item.section_nr
            if section_nr in all_matches:
                match = all_matches[section_nr]
                sku = match.get("bc_sku")
                if sku and sku in bc_lookup:
                    item.bc_product = bc_lookup[sku]
                    item.match_confidence = max(
                        item.match_confidence, match.get("confidence", 0.5)
                    )
                    item.notes = match.get("notes", "")
                    if item.match_status.value == "unmatched":
                        item.match_status = "partial"
                elif sku:
                    # SKU not in lookup but was suggested (maybe placeholder)
                    item.bc_product = BCProduct(
                        sku=sku,
                        description=match.get("bc_description", ""),
                        quantity=0,
                    )
                    item.match_confidence = max(
                        item.match_confidence, match.get("confidence", 0.3)
                    )
                    item.notes = match.get("notes", "")

        return enriched_items

    def _match_batch(
        self,
        batch: list[EnrichedItem],
        bc_products: list[BCProduct],
    ) -> dict[str, dict]:
        """Match a batch of items against the BC catalog using Claude."""
        items_data = [
            {
                "section_nr": e.magnaskra_item.section_nr,
                "description": e.magnaskra_item.description,
                "quantity": e.magnaskra_item.quantity,
                "unit": e.magnaskra_item.unit,
            }
            for e in batch
        ]

        catalog_data = [
            {
                "sku": p.sku,
                "description": p.description,
                "unit": p.unit,
                "section": p.section_comment,
            }
            for p in bc_products
            if p.product_type.value == "Vara"
        ]

        prompt = MATCH_PROMPT.format(
            items_json=json.dumps(items_data, ensure_ascii=False, indent=2),
            catalog_json=json.dumps(catalog_data, ensure_ascii=False, indent=2),
        )

        try:
            matches = self.ai.ask_json(SYSTEM_PROMPT, prompt)
            return {m["magnaskra_section_nr"]: m for m in matches if m.get("bc_sku")}
        except Exception as e:
            print(f"  Warning: BC matching batch failed: {e}")
            return {}
