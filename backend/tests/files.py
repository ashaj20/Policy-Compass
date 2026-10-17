"""Tiny but structurally valid documents for upload tests."""

import io
import zipfile

PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


def docx_bytes(text: str = "Emergency repairs are attended within 24 hours.") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            f'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
            "</w:body></w:document>",
        )
    return buf.getvalue()


def plain_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "not a word document")
    return buf.getvalue()
