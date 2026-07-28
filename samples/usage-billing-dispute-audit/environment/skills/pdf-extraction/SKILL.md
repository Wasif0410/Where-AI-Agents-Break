---
name: pdf-extraction
description: Extract structured data from PDF files using pdfplumber. Use when invoice data or pricing rules are stored in PDFs that may have different layouts across files.
---

# PDF Data Extraction

Use `pdfplumber` to extract text from PDF files. Different PDFs in this task use different layouts — inspect each file's structure before deciding on an extraction approach.

## Workflow

1. Open the PDF with `pdfplumber.open(path)`.
2. Iterate over all pages.
3. Extract the full text from each page using `page.extract_text()`.
4. Inspect the structure: is it a delimited table, a section-based layout, or inline prose?
5. Apply an appropriate parsing strategy for each layout.
6. Strip whitespace from all extracted fields.
7. Cast numeric fields explicitly after extraction.

## Important

- Do not assume all PDFs share one format. Each invoice may use a completely different text structure.
- Validate extracted line totals where possible by cross-checking against invoice subtotals or grand totals.
- Pricing rules must be read from `pricing_addendum.pdf` — do not assume or hardcode tier rates, discounts, or rounding policies.
