import base64
import os
from typing import List

import fitz  # PyMuPDF
from pydantic import BaseModel, Field

from pocketflow import Node, StructuredNode


class LineItemSchema(BaseModel):
    description: str = Field(description="Description of the line item")
    quantity: float = Field(description="Quantity of the item")
    unit_price: float = Field(description="Unit price of the item")
    amount: float = Field(description="Total amount for this line item")


class InvoiceSchema(BaseModel):
    invoice_number: str = Field(description="Invoice number")
    vendor: str = Field(description="Vendor name")
    customer: str = Field(description="Customer name")
    date: str = Field(description="Invoice date")
    due_date: str = Field(description="Invoice due date")
    line_items: List[LineItemSchema] = Field(description="List of line items")
    subtotal: float = Field(description="Subtotal amount")
    tax_rate: float = Field(description="Tax rate (e.g., 0.08 for 8% or 8.0)")
    tax_amount: float = Field(description="Tax amount")
    total: float = Field(description="Total amount")


class ExtractFields(StructuredNode):
    """Extracts structured invoice data from a PDF using GPT-4o vision."""

    def __init__(self, max_retries=3, wait=5):
        from utils import get_instructor_client

        model = "gpt-4o"
        if os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            model = "gemini-2.0-flash"

        super().__init__(
            response_model=InvoiceSchema,
            client=get_instructor_client(),
            model=model,
            max_retries=max_retries,
            wait=wait,
        )

    def prep(self, shared):
        pdf_path = shared["pdf_path"]
        print("🔍 Converting PDF to image...")
        doc = fitz.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap(dpi=200)
        image_bytes = pix.tobytes("png")
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        doc.close()

        print("🤔 Extracting invoice fields with GPT-4o vision...")
        prompt = "Extract all fields from this invoice image."

        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            }
        ]

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        shared["extracted"] = data

        print("  Extracted fields:")
        print(f"    Invoice #: {data.get('invoice_number')}")
        print(f"    Vendor: {data.get('vendor')}")
        print(f"    Customer: {data.get('customer')}")
        items = data.get("line_items", [])
        print(f"    Line items: {len(items)}")
        for item in items:
            print(
                f"      - {item['description']}: {item['quantity']:.0f} x ${item['unit_price']:.2f} = ${item['amount']:.2f}"
            )
        print(f"    Subtotal: ${data.get('subtotal', 0):.2f}")
        print(f"    Tax: ${data.get('tax_amount', 0):.2f}")
        print(f"    Total: ${data.get('total', 0):.2f}")


class Validate(Node):
    """Validates invoice math: line item amounts, subtotal, tax, and total."""

    def prep(self, shared):
        return shared["extracted"]

    def exec(self, data):
        print("🔍 Validating invoice math...")
        errors = []

        # Validate each line item: quantity * unit_price == amount
        items = data.get("line_items", [])
        for item in items:
            expected = round(item["quantity"] * item["unit_price"], 2)
            if abs(expected - item["amount"]) > 0.01:
                errors.append(
                    f"Line item '{item['description']}' math error: "
                    f"{item['quantity']} x ${item['unit_price']:.2f} = ${expected:.2f}, "
                    f"but invoice says ${item['amount']:.2f}"
                )

        # Validate subtotal: sum of line item amounts
        computed_subtotal = sum(item["amount"] for item in items)
        if abs(computed_subtotal - data["subtotal"]) > 0.01:
            errors.append(
                f"Subtotal mismatch: items sum to ${computed_subtotal:.2f}, "
                f"invoice says ${data['subtotal']:.2f}"
            )

        # Validate tax: subtotal * tax_rate
        tax_pct = data["tax_rate"] if data["tax_rate"] > 1 else data["tax_rate"] * 100
        computed_tax = round(data["subtotal"] * tax_pct / 100, 2)
        if abs(computed_tax - data["tax_amount"]) > 0.01:
            errors.append(
                f"Tax mismatch: ${data['subtotal']:.2f} x {tax_pct}% = ${computed_tax:.2f}, "
                f"invoice says ${data['tax_amount']:.2f}"
            )

        # Validate total: subtotal + tax_amount
        computed_total = data["subtotal"] + data["tax_amount"]
        if abs(computed_total - data["total"]) > 0.01:
            errors.append(
                f"Total mismatch: ${data['subtotal']:.2f} + ${data['tax_amount']:.2f} = ${computed_total:.2f}, "
                f"invoice says ${data['total']:.2f}"
            )

        return errors

    def post(self, shared, prep_res, exec_res):
        shared["validation_errors"] = exec_res
        if exec_res:
            print("  Validation FAILED:")
            for err in exec_res:
                print(f"    - {err}")
        else:
            print("  Validation passed ✅")
