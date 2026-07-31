from pypdf import PdfReader

CHUNK_SIZE = 1000  # characters

reader = PdfReader("docs/appendix_k.pdf")

text = ""

for page in reader.pages:
    page_text = page.extract_text()
    if page_text:
        text += page_text + "\n"

print(f"Total characters: {len(text)}")

chunks = []

for i in range(0, len(text), CHUNK_SIZE):
    chunk = text[i:i + CHUNK_SIZE]
    chunks.append(chunk)

print(f"\nCreated {len(chunks)} chunks.\n")

for i, chunk in enumerate(chunks):
    print("=" * 60)
    print(f"Chunk {i+1}")
    print("=" * 60)
    print(chunk[:300])     # show first 300 characters
    print()