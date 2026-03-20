"""Matches magnskrá items to verklýsing sections - no AI needed, uses section numbers."""

from app.models.schemas import (
    EnrichedItem,
    MagnaskraItem,
    MatchStatus,
    VerklysingRequirement,
    VerklysingSection,
)


class SectionMatcher:
    """Matches magnskrá items to verklýsing sections by section number.

    No AI needed here - the section numbering is consistent between documents,
    and the raw verklýsing text IS the requirement (no need to re-extract it).
    """

    def match_items(
        self,
        magnaskra_items: list[MagnaskraItem],
        verklysing_sections: list[VerklysingSection],
    ) -> list[EnrichedItem]:
        section_lookup: dict[str, VerklysingSection] = {
            s.section_nr: s for s in verklysing_sections
        }

        enriched = []
        for item in magnaskra_items:
            if item.is_header:
                enriched.append(EnrichedItem(magnaskra_item=item))
                continue

            matched_section = self._find_matching_section(item, section_lookup)

            if matched_section:
                # Convert raw text into a single "general" requirement
                # The full verklýsing text is attached as the section reference
                reqs = []
                if matched_section.raw_text and len(matched_section.raw_text.strip()) > 10:
                    reqs = [VerklysingRequirement(
                        category="general",
                        text=matched_section.raw_text[:500],
                        is_critical=False,
                    )]

                enriched.append(EnrichedItem(
                    magnaskra_item=item,
                    verklysing_section=matched_section,
                    verklysing_requirements=reqs,
                    match_status=MatchStatus.MATCHED,
                    match_confidence=1.0,
                ))
            else:
                enriched.append(EnrichedItem(
                    magnaskra_item=item,
                    match_status=MatchStatus.UNMATCHED,
                ))

        return enriched

    def _find_matching_section(
        self,
        item: MagnaskraItem,
        section_lookup: dict[str, VerklysingSection],
    ) -> VerklysingSection | None:
        """Find the verklýsing section matching a magnskrá item by section number."""
        # Item 3.1.1.1 → try 3.1.1, then 3.1, then 3
        parts = item.section_nr.split(".")
        for depth in range(len(parts) - 1, 0, -1):
            candidate_nr = ".".join(parts[:depth])
            if candidate_nr in section_lookup:
                return section_lookup[candidate_nr]

        if item.parent_section and item.parent_section in section_lookup:
            return section_lookup[item.parent_section]

        return None
