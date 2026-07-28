---
name: pdf-extraction
description: Extract text from PDF documents with pdfplumber when rules or policies are stored as PDFs.
---

# PDF Extraction

```python
import pdfplumber

with pdfplumber.open(path) as pdf:
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
```

Parse the extracted text according to the document layout. Footnotes may appear at page bottoms.
