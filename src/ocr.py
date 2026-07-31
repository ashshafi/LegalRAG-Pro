from pdf2image import convert_from_path
import pytesseract

# Tesseract
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Poppler
POPPLER_PATH = (
    r"C:\Users\ashsh\Downloads\Release-26.02.0-0\poppler-26.02.0\Library\bin"
)


def extract_text(pdf_path):
    images = convert_from_path(
        pdf_path,
        poppler_path=POPPLER_PATH
    )

    text = ""

    for image in images:
        text += pytesseract.image_to_string(image)
        text += "\n"

    return text