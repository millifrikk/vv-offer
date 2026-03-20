#!/usr/bin/env python3
"""Full processing pipeline - parses, cross-references, and generates enriched Excel.

Usage:
    python cli_process.py <magnaskra_xlsx> <verklysing_pdf> <bc_export_xlsx> [output.xlsx]

Example:
    python cli_process.py ../vv_docs/Gestastofa-Tilboðsskrá.xlsx \
                          "../vv_docs/Gestastofa-VEL-Kafli 3 Lagnir.pdf" \
                          ../vv_docs/Gestastofa.xlsx \
                          output/enriched.xlsx

Requires ANTHROPIC_API_KEY in .env or environment.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.parsers import MagnaskraParser, VerklysingParser, BCCatalogParser
from app.engine.ai_client import AIClient
from app.engine.section_matcher import SectionMatcher
from app.engine.bc_matcher import BCMatcher
from app.engine.gap_analyzer import GapAnalyzer
from app.output.excel_writer import ExcelWriter


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    magnaskra_path = sys.argv[1]
    verklysing_path = sys.argv[2]
    bc_path = sys.argv[3]
    output_path = sys.argv[4] if len(sys.argv) > 4 else "output/enriched_tilbod.xlsx"

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("VV OFFER TOOL - Full Processing Pipeline")
    print("=" * 70)

    # Step 1: Parse all documents
    print("\n[1/5] Parsing documents...")
    t0 = time.time()

    mag_parser = MagnaskraParser()
    mag_items = mag_parser.parse(magnaskra_path)
    line_items = [i for i in mag_items if not i.is_header]
    print(f"  Magnskrá: {len(line_items)} line items")

    verk_parser = VerklysingParser()
    verk_sections = verk_parser.parse(verklysing_path)
    print(f"  Verklýsing: {len(verk_sections)} sections")

    bc_parser = BCCatalogParser()
    bc_products = bc_parser.parse(bc_path)
    print(f"  BC catalog: {len(bc_products)} products")
    print(f"  Done in {time.time() - t0:.1f}s")

    # Step 2: Match sections (no AI needed - uses section numbers)
    print("\n[2/5] Matching magnskrá items to verklýsing sections...")
    t0 = time.time()

    section_matcher = SectionMatcher()

    # Only process the "3 Lagnir" sheet for now (matching the verklýsing chapter)
    lagnir_items = [i for i in mag_items if i.sheet_name == "3 Lagnir"]
    enriched_items = section_matcher.match_items(lagnir_items, verk_sections)

    matched_count = sum(
        1 for e in enriched_items
        if e.match_status.value == "matched" and not e.magnaskra_item.is_header
    )
    print(f"  Matched: {matched_count}/{len([e for e in enriched_items if not e.magnaskra_item.is_header])}")
    print(f"  Done in {time.time() - t0:.1f}s")

    # Step 3: Match to BC products (AI-powered)
    print("\n[3/5] Matching items to BC products...")
    t0 = time.time()

    ai_client = AIClient()
    bc_matcher = BCMatcher(ai_client)
    enriched_items = bc_matcher.match_items(enriched_items, bc_products)

    bc_matched = sum(1 for e in enriched_items if e.bc_product is not None)
    print(f"  BC matches found: {bc_matched}")
    print(f"  Done in {time.time() - t0:.1f}s")

    # Step 4: Gap analysis
    print("\n[4/5] Analyzing gaps...")
    t0 = time.time()

    gap_analyzer = GapAnalyzer(ai_client)
    gaps = gap_analyzer.analyze(lagnir_items, verk_sections)

    high_gaps = sum(1 for g in gaps if g.severity.value == "high")
    med_gaps = sum(1 for g in gaps if g.severity.value == "medium")
    print(f"  Gaps found: {len(gaps)} ({high_gaps} high, {med_gaps} medium)")
    print(f"  Done in {time.time() - t0:.1f}s")

    # Step 5: Generate Excel
    print("\n[5/5] Generating enriched Excel...")
    t0 = time.time()

    writer = ExcelWriter()
    writer.write(enriched_items, gaps, output_path)

    print(f"  Output: {output_path}")
    print(f"  Done in {time.time() - t0:.1f}s")

    # Summary
    print("\n" + "=" * 70)
    print("COMPLETE")
    print(f"  Items processed: {len(enriched_items)}")
    print(f"  Verklýsing matches: {matched_count}")
    print(f"  BC product matches: {bc_matched}")
    print(f"  Gaps identified: {len(gaps)}")
    print(f"  Output file: {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
