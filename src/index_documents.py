from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
import chromadb

from ocr import extract_text

# ==========================================
# Load environment variables
# ==========================================

load_dotenv()

client = OpenAI()

# ==========================================
# Connect to Chroma
# ==========================================

chroma_client = chromadb.PersistentClient(path="db")

collection = chroma_client.get_or_create_collection(
    name="legal_documents"
)

# ==========================================
# Text splitter
# ==========================================

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

# ==========================================
# Index a single PDF
# ==========================================

def index_pdf(pdf_path):

    pdf_path = Path(pdf_path)

    print(f"\nReading {pdf_path.name}")

    reader = PdfReader(pdf_path)

    total_chunks = 0

    # OCR the whole PDF once if needed
    ocr_text = None
    ocr_used = False

    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text()

        # ----------------------------------
        # Fall back to OCR if page has no text
        # ----------------------------------

        if not text or not text.strip():

            print(f"Page {page_number}: No text found - using OCR")

            if not ocr_used:

                try:
                    ocr_text = extract_text(pdf_path)
                    ocr_used = True
                    print("OCR completed successfully.")

                except Exception as e:
                    print(f"OCR failed: {e}")
                    continue

            text = ocr_text

            if not text or not text.strip():
                print(f"Page {page_number}: OCR found no text")
                continue

        print(f"Page {page_number}: {len(text)} characters")

        chunks = splitter.split_text(text)

        print(f"Page {page_number}: {len(chunks)} chunks")

        for chunk_number, chunk in enumerate(chunks):

            try:

                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=chunk
                )

                embedding = response.data[0].embedding

                document_id = (
                    f"{pdf_path.stem}_{page_number}_{chunk_number}"
                )

                collection.add(
                    ids=[document_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{
                        "file": pdf_path.name,
                        "page": page_number,
                        "chunk": chunk_number
                    }]
                )

                total_chunks += 1

            except Exception as e:
                print(
                    f"Error adding chunk "
                    f"{chunk_number}: {e}"
                )

    print(f"\nFinished indexing {pdf_path.name}")
    print(f"Chunks added: {total_chunks}")

# ==========================================
# Index every PDF in docs/
# ==========================================

def index_all_documents():

    docs_folder = Path("docs")

    pdf_files = list(docs_folder.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.")
        return

    for pdf_file in pdf_files:
        index_pdf(pdf_file)

    print("\nFinished indexing all documents.")

# ==========================================
# Run from command line
# ==========================================

if __name__ == "__main__":
    index_all_documents()