"""Reading the text out of uploaded PDFs."""
import io

from pypdf import PdfReader


class PdfError(Exception):
    """The upload could not be read as a PDF."""


def read_pages(content: bytes, max_pages: int) -> tuple[list[str], int]:
    """The text of each of the first `max_pages` pages, and the PDF's total page count."""
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            reader.decrypt("")  # many posted PDFs are "encrypted" with an empty password
        return [page.extract_text() or "" for page in reader.pages[:max_pages]], len(reader.pages)
    except Exception as e:  # pypdf raises many types on damaged files
        raise PdfError(str(e)) from e
