from unittest.mock import MagicMock, patch

from docx import Document


async def test_extract_text_from_bytes():
    mock_reader = MagicMock()
    mock_reader.pages = [
        MagicMock(extract_text=MagicMock(return_value="Software Engineer")),
        MagicMock(extract_text=MagicMock(return_value="Python FastAPI")),
    ]
    with patch("backend.services.cv_parser.PdfReader", return_value=mock_reader):
        from backend.services.cv_parser import extract_text_from_pdf_bytes

        result = await extract_text_from_pdf_bytes(b"fake-pdf-bytes")
    assert "Software Engineer" in result
    assert "Python FastAPI" in result


async def test_extract_text_missing_file_returns_empty():
    from backend.services.cv_parser import extract_text_from_file

    result = await extract_text_from_file("nonexistent/path.pdf")
    assert result == ""


async def test_extract_docx_walks_tables_and_headers(tmp_path):
    from backend.services.cv_parser import extract_text_from_docx_bytes

    path = tmp_path / "resume.docx"
    document = Document()
    document.sections[0].header.paragraphs[0].text = "Header Candidate"
    document.add_paragraph("Top-level Summary")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "Postgres"
    document.save(path)

    result = await extract_text_from_docx_bytes(path.read_bytes())

    assert "Header Candidate" in result
    assert "Top-level Summary" in result
    assert "Python" in result
    assert "Postgres" in result
