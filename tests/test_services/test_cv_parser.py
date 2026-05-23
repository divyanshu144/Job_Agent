from unittest.mock import MagicMock, patch


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
