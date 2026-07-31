from ocr import extract_text

text = extract_text(
    "docs/Appendix B – Grievance Letters & Correspondence (2001, 2005).pdf"
)

print(text[:3000])