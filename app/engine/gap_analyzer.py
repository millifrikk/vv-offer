"""Finds requirements in verklýsing that are missing from the magnskrá."""

import json

from app.engine.ai_client import AIClient
from app.models.schemas import (
    GapItem,
    GapSeverity,
    MagnaskraItem,
    VerklysingSection,
)

SYSTEM_PROMPT = """You are an expert in Icelandic construction project documentation.
You identify requirements from work descriptions (verklýsing) that may be missing
from the bill of quantities (magnskrá/tilboðsskrá).

Focus on: specific equipment/materials mentioned but not listed, testing requirements
that need line items, special installation items.

Do NOT flag: general quality statements, overview sections, standard practices."""

GAP_PROMPT = """Compare these verklýsing sections with their corresponding magnskrá items.
Identify specific requirements in the verklýsing NOT covered by the magnskrá items.

{sections_data}

Return a JSON array of gaps. Each gap should have:
- "section_nr": source section number
- "section_title": source section title
- "requirement_text": what's missing (in Icelandic)
- "severity": "high" (material/equipment missing), "medium" (testing/inspection), or "low" (nice-to-have)
- "suggested_action": what to add (in Icelandic)

Return an empty array [] if all requirements are covered. Be selective - only flag real gaps."""


class GapAnalyzer:
    """Identifies requirements in verklýsing missing from magnskrá."""

    def __init__(self, ai_client: AIClient | None = None):
        self.ai = ai_client or AIClient()

    def analyze(
        self,
        magnaskra_items: list[MagnaskraItem],
        verklysing_sections: list[VerklysingSection],
    ) -> list[GapItem]:
        """Find gaps between verklýsing requirements and magnskrá items."""
        # Build magnskrá lookup by parent section
        items_by_section: dict[str, list[MagnaskraItem]] = {}
        for item in magnaskra_items:
            if item.is_header:
                continue
            parts = item.section_nr.split(".")
            for depth in range(len(parts) - 1, 0, -1):
                parent = ".".join(parts[:depth])
                items_by_section.setdefault(parent, []).append(item)

        # Filter to content sections (skip overview/yfirlit)
        content_sections = [
            s for s in verklysing_sections
            if not s.section_nr.endswith(".0")
            and s.raw_text
            and len(s.raw_text.strip()) >= 30
        ]

        # Process in batches of ~8 sections per API call
        all_gaps = []
        # Send all sections in one call - Sonnet 4.6 has 1M context
        batch_size = 200
        for i in range(0, len(content_sections), batch_size):
            batch = content_sections[i:i + batch_size]
            print(f"  Gap analysis: batch {i // batch_size + 1}/{(len(content_sections) + batch_size - 1) // batch_size}")
            gaps = self._analyze_batch(batch, items_by_section)
            all_gaps.extend(gaps)

        return all_gaps

    def _analyze_batch(
        self,
        sections: list[VerklysingSection],
        items_by_section: dict[str, list[MagnaskraItem]],
    ) -> list[GapItem]:
        """Analyze a batch of sections for gaps in one API call."""
        sections_data = ""
        for section in sections:
            mag_items = items_by_section.get(section.section_nr, [])
            if not mag_items:
                parts = section.section_nr.split(".")
                if len(parts) >= 2:
                    parent = ".".join(parts[:2])
                    mag_items = items_by_section.get(parent, [])

            items_text = "\n".join(
                f"    [{i.section_nr}] {i.description} | {i.quantity} {i.unit}"
                for i in mag_items
            ) if mag_items else "    (No items)"

            sections_data += f"\n--- Verklýsing {section.section_nr}: {section.title} ---\n"
            sections_data += section.raw_text[:1000] + "\n"
            sections_data += f"Magnskrá items:\n{items_text}\n"

        prompt = GAP_PROMPT.format(sections_data=sections_data)

        try:
            data = self.ai.ask_json(SYSTEM_PROMPT, prompt)
            gaps = []
            for item in data:
                severity_str = item.get("severity", "medium")
                try:
                    severity = GapSeverity(severity_str)
                except ValueError:
                    severity = GapSeverity.MEDIUM

                gaps.append(GapItem(
                    source_section=item.get("section_nr", ""),
                    source_title=item.get("section_title", ""),
                    requirement_text=item.get("requirement_text", ""),
                    severity=severity,
                    suggested_action=item.get("suggested_action", ""),
                ))
            return gaps
        except Exception as e:
            print(f"  Warning: Gap analysis batch failed: {e}")
            return []
