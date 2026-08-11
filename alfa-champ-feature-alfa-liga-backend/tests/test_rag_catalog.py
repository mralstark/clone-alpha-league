from app.services.rag_catalog import RAGCatalogService
from app.models import KnowledgeBaseEntry


def test_rag_context_encoding():
    service = RAGCatalogService()
    text = service.build_context_query("HoReCa", "56.10", "retention_rate", 12.5)
    vector = service.encode_text(text)

    assert isinstance(vector, list)
    assert len(vector) == 384


def test_search_similar_sprints(app):
    service = RAGCatalogService()
    db = app.state.db

    with db.session_factory() as session:
        # create a seed entry
        entry = KnowledgeBaseEntry(
            id="kb_test_1",
            category="HoReCa",
            okved="56.10",
            target_metric="retention_rate",
            title="Test case",
            description="Test description",
            action_items=["do x", "do y"],
            associated_products=["Alfa-Loyalty"],
            embedding=service.encode_text(service.build_context_query("HoReCa", "56.10", "retention_rate", 10.0)),
        )
        session.add(entry)

    with db.session_factory() as session:
        results = service.search_similar_sprints(
            session=session,
            category="HoReCa",
            target_metric="retention_rate",
            metric_drop_pct=10.0,
            okved="56.10",
            top_k=3,
        )

    assert len(results) > 0
    assert results[0]["source"] == "rag_kb_knn"
