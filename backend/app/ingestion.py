import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.embeddings import Tokenizer
from app.errors import AppError


@dataclass(frozen=True)
class Section:
    text: str
    page: int | None = None
    heading: str | None = None


def validate_source(filename: str, content: bytes) -> str:
    extension = filename.lower().rsplit(".", 1)[-1]
    if extension not in {"pdf", "md"}:
        raise AppError("UNSUPPORTED_FILE", "Solo se admiten archivos PDF y Markdown", 415)
    if not content:
        raise AppError("EMPTY_FILE", "El archivo está vacío")
    if extension == "pdf" and not content.startswith(b"%PDF-"):
        raise AppError("INVALID_PDF", "El contenido no corresponde a un PDF", 415)
    if extension == "md":
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError("INVALID_ENCODING", "Markdown debe estar codificado en UTF-8") from exc
        if "\x00" in decoded or not decoded.strip():
            raise AppError("INVALID_MARKDOWN", "Markdown debe contener texto legible")
    return extension


def extract_sections(filename: str, content: bytes) -> list[Section]:
    extension = validate_source(filename, content)
    if extension == "md":
        text = content.decode("utf-8-sig")
        sections: list[Section] = []
        heading = None
        body: list[str] = []
        for line in text.splitlines():
            if re.match(r"^#{1,6}\s", line):
                if body:
                    sections.append(Section("\n".join(body), heading=heading))
                heading = line.lstrip("# ").strip()[:300]
                body = [line]
            else:
                body.append(line)
        if body:
            sections.append(Section("\n".join(body), heading=heading))
        # A heading is metadata, not evidence on its own.
        sections = [
            section for section in sections if re.sub(r"(?m)^#{1,6}\s.*$", "", section.text).strip()
        ]
    else:
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise AppError("ENCRYPTED_PDF", "No se admiten PDFs cifrados")
            if len(reader.pages) > 100:
                raise AppError("TOO_MANY_PAGES", "El PDF supera el límite de 100 páginas")
            sections = [
                Section(page.extract_text() or "", page=index + 1)
                for index, page in enumerate(reader.pages)
            ]
        except (PyPdfError, ValueError, OSError) as exc:
            raise AppError("CORRUPT_DOCUMENT", "No se pudo extraer el texto del PDF") from exc
    if sum(len(section.text) for section in sections) > 1_000_000:
        raise AppError("EXTRACTED_TEXT_TOO_LARGE", "El texto extraído supera el límite")
    sections = [section for section in sections if section.text.strip()]
    if not sections:
        raise AppError("NO_EXTRACTABLE_TEXT", "El documento no contiene texto; OCR no disponible")
    return sections


def chunk_sections(
    sections: list[Section],
    tokenizer: Tokenizer,
    max_tokens: int = 400,
    overlap: int = 60,
    respect_paragraphs: bool = True,
) -> list[Section]:
    if max_tokens < 1 or overlap < 0 or overlap >= max_tokens:
        raise ValueError("El solapamiento debe ser menor que el tamaño de fragmento")
    chunks: list[Section] = []
    for section in sections:
        spans = tokenizer.spans(section.text)
        start = 0
        while start < len(spans):
            end = min(start + max_tokens, len(spans))
            if respect_paragraphs and end < len(spans):
                lower = start + max_tokens // 2
                paragraph = section.text.rfind("\n\n", spans[lower][0], spans[end - 1][1])
                if paragraph >= 0:
                    end = next((i for i in range(lower, end) if spans[i][0] >= paragraph), end)
            text = section.text[spans[start][0] : spans[end - 1][1]].strip()
            if text:
                chunks.append(Section(text, section.page, section.heading))
            if end == len(spans):
                break
            start = max(start + 1, end - overlap)
    return chunks
