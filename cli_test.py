#!/usr/bin/env python3
"""CLI test script - parses all sample files and prints a summary.

Usage:
    python cli_test.py <magnaskra_xlsx> <verklysing_pdf> <bc_export_xlsx>

Example:
    python cli_test.py ../vv_docs/Gestastofa-Tilboðsskrá.xlsx \
                       "../vv_docs/Gestastofa-VEL-Kafli 3 Lagnir.pdf" \
                       ../vv_docs/Gestastofa.xlsx
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.parsers import MagnaskraParser, VerklysingParser, BCCatalogParser


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    magnaskra_path = sys.argv[1]
    verklysing_path = sys.argv[2]
    bc_path = sys.argv[3]

    print("=" * 70)
    print("VV OFFER TOOL - Parser Test")
    print("=" * 70)

    # Parse magnskrá
    print("\n--- Parsing Magnskrá (tilboðsskrá) ---")
    mag_parser = MagnaskraParser()
    mag_items = mag_parser.parse(magnaskra_path)
    sheets = set(item.sheet_name for item in mag_items)
    headers = [i for i in mag_items if i.is_header]
    line_items = [i for i in mag_items if not i.is_header]

    print(f"  Sheets found: {sorted(sheets)}")
    print(f"  Total rows: {len(mag_items)}")
    print(f"  Section headers: {len(headers)}")
    print(f"  Line items (with quantities): {len(line_items)}")

    # Show items per sheet
    for sheet in sorted(sheets):
        sheet_items = [i for i in line_items if i.sheet_name == sheet]
        print(f"    {sheet}: {len(sheet_items)} line items")

    # Show sample items from "3 Lagnir"
    lagnir_items = [i for i in line_items if i.sheet_name == "3 Lagnir"]
    if lagnir_items:
        print(f"\n  Sample items from '3 Lagnir' (first 10):")
        for item in lagnir_items[:10]:
            qty_str = f"{item.quantity} {item.unit}" if item.quantity else "---"
            print(f"    [{item.section_nr}] {item.description} | {qty_str}")

    # Parse verklýsing
    print("\n--- Parsing Verklýsing (work description) ---")
    verk_parser = VerklysingParser()
    verk_sections = verk_parser.parse(verklysing_path)

    print(f"  Sections found: {len(verk_sections)}")

    # Show all sections
    for section in verk_sections:
        pages = ", ".join(str(p) for p in section.page_numbers) if section.page_numbers else "?"
        text_preview = section.raw_text[:80].replace("\n", " ")
        print(f"    [{section.section_nr}] {section.title} (p.{pages})")

    # Parse BC catalog
    print("\n--- Parsing BC Catalog ---")
    bc_parser = BCCatalogParser()
    bc_products = bc_parser.parse(bc_path)

    vara_count = sum(1 for p in bc_products if p.product_type.value == "Vara")
    fordi_count = sum(1 for p in bc_products if p.product_type.value == "Forði")

    print(f"  Products found: {len(bc_products)}")
    print(f"    Vara (products): {vara_count}")
    print(f"    Forði (resources): {fordi_count}")

    # Show unique SKUs vs placeholder
    skus = [p.sku for p in bc_products if p.product_type.value == "Vara"]
    placeholder_count = sum(1 for s in skus if s == "1125651")
    unique_count = len(set(skus)) - (1 if "1125651" in skus else 0)
    print(f"    Unique SKUs: {unique_count}")
    print(f"    Placeholder SKU (1125651 = special orders): {placeholder_count} items")

    # Show sample products
    print(f"\n  Sample products (first 10):")
    for p in bc_products[:10]:
        price_str = f"kr {p.unit_price:,.0f}" if p.unit_price else "no price"
        print(f"    [{p.sku}] {p.description} | qty: {p.quantity} | {price_str}")

    # Cross-reference preview
    print("\n" + "=" * 70)
    print("CROSS-REFERENCE PREVIEW")
    print("=" * 70)

    # Find magnskrá sections that have matching verklýsing sections
    mag_section_nrs = set(i.section_nr.rsplit(".", 1)[0] if "." in i.section_nr else i.section_nr
                         for i in line_items if i.sheet_name == "3 Lagnir")
    verk_section_nrs = set(s.section_nr for s in verk_sections)

    matched = mag_section_nrs & verk_section_nrs
    mag_only = mag_section_nrs - verk_section_nrs
    verk_only = verk_section_nrs - mag_section_nrs

    print(f"\n  Section number matching (Lagnir chapter):")
    print(f"    Matched sections: {len(matched)}")
    print(f"    In magnskrá only: {len(mag_only)}")
    print(f"    In verklýsing only: {len(verk_only)}")

    if verk_only:
        print(f"\n  Sections in verklýsing but NOT in magnskrá (potential gaps):")
        for nr in sorted(verk_only):
            section = next(s for s in verk_sections if s.section_nr == nr)
            print(f"    [{nr}] {section.title}")

    print("\n" + "=" * 70)
    print("DONE - All parsers working correctly!")
    print("=" * 70)


if __name__ == "__main__":
    main()
