from pydantic import BaseModel, Field
from enum import Enum


class MagnaskraItem(BaseModel):
    """A single line item from the tilboðsskrá/magnskrá (bill of quantities)."""
    section_nr: str = Field(description="Section number, e.g. '3.1.1.1'")
    description: str = Field(description="Item description, e.g. 'PP SN10 - ø110'")
    quantity: float | None = Field(default=None, description="Quantity")
    unit: str | None = Field(default=None, description="Unit of measurement, e.g. 'm', 'stk'")
    sheet_name: str = Field(description="Source sheet name, e.g. '3 Lagnir'")
    is_header: bool = Field(default=False, description="True if this is a section header, not a line item")
    parent_section: str | None = Field(default=None, description="Parent section number")


class VerklysingRequirement(BaseModel):
    """A specific requirement extracted from the verklýsing."""
    category: str = Field(description="Category: material, standard, testing, installation, etc.")
    text: str = Field(description="The requirement text")
    is_critical: bool = Field(default=False, description="Whether this is a critical/mandatory requirement")


class VerklysingSection(BaseModel):
    """A section from the verklýsing (work description) PDF."""
    section_nr: str = Field(description="Section number, e.g. '3.1.1'")
    title: str = Field(description="Section title")
    raw_text: str = Field(description="Full text content of the section")
    requirements: list[VerklysingRequirement] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list, description="PDF pages where this section appears")


class BCProductType(str, Enum):
    VARA = "Vara"
    FORDI = "Forði"
    ATHUGASEMD = "Athugasemd"


class BCProduct(BaseModel):
    """A product from the BC (Business Central) catalog export."""
    sku: str = Field(description="Product SKU/item number from BC")
    description: str = Field(description="Product description")
    quantity: float = Field(default=0)
    unit: str = Field(default="STK")
    product_type: BCProductType = Field(default=BCProductType.VARA)
    section_comment: str | None = Field(default=None, description="Section comment from Athugasemd rows")
    unit_price: float | None = Field(default=None, description="Unit price excl. VAT")
    cost_price: float | None = Field(default=None, description="Cost price (SGM)")


class MatchStatus(str, Enum):
    MATCHED = "matched"
    PARTIAL = "partial"
    UNMATCHED = "unmatched"
    GAP = "gap"


class EnrichedItem(BaseModel):
    """A magnskrá item enriched with verklýsing requirements and BC product match."""
    magnaskra_item: MagnaskraItem
    verklysing_section: VerklysingSection | None = None
    verklysing_requirements: list[VerklysingRequirement] = Field(default_factory=list)
    bc_product: BCProduct | None = None
    match_status: MatchStatus = Field(default=MatchStatus.UNMATCHED)
    match_confidence: float = Field(default=0.0, description="0-1 confidence score")
    notes: str = Field(default="")


class GapSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GapItem(BaseModel):
    """A requirement found in verklýsing but missing from magnskrá."""
    source_section: str = Field(description="Verklýsing section number where requirement was found")
    source_title: str = Field(description="Section title")
    requirement_text: str = Field(description="The requirement that's missing from magnskrá")
    severity: GapSeverity = Field(default=GapSeverity.MEDIUM)
    suggested_action: str = Field(default="")


class ParseSummary(BaseModel):
    """Summary of parsed documents."""
    magnaskra_items: int = 0
    magnaskra_sheets: list[str] = Field(default_factory=list)
    verklysing_sections: int = 0
    verklysing_pages: int = 0
    bc_products: int = 0
    bc_comments: int = 0
