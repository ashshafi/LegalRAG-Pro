from pypdf import PdfReader

pdf_file = "docs/appendix_k.pdf"

reader = PdfReader(pdf_file)

print(f"Number of pages: {len(reader.pages)}")

for page_number, page in enumerate(reader.pages, start=1):
    print(f"\n--- Page {page_number} ---")

    text = page.extract_text()

    if text:
        print(text)
    else:
        print("No text found on this page.")