from backend.schemas import ResumeContentUpdate, ResumeDocumentResponse, ResumeTailorerOutput


def test_content_update_requires_base_rev():
    upd = ResumeContentUpdate(base_rev=3, content=ResumeTailorerOutput(headline="Eng"))
    assert upd.base_rev == 3
    assert upd.content.headline == "Eng"


def test_document_response_carries_rev_and_content():
    resp = ResumeDocumentResponse(
        id="d1",
        kind="master",
        name="Default",
        is_active=True,
        rev=2,
        content=ResumeTailorerOutput(headline="Eng"),
        updated_at="2026-07-22T00:00:00Z",
    )
    assert resp.rev == 2 and resp.content.headline == "Eng"
