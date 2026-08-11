import uuid
from app.db import Database
from app.models import KnowledgeBaseEntry
from app.services.rag_catalog import RAGCatalogService


def seed_knowledge_base(db_url: str = "sqlite:///./dev_kb.db"):
    # lightweight standalone seeder for local development
    db = Database(db_url)
    db.create_schema()
    rag = RAGCatalogService()
    with db.session_factory() as session:
        # small set for quick local testing
        cases = [
            {
                "category": "HoReCa",
                "target_metric": "retention_rate",
                "okved": "56.10",
                "title": "Утренний клуб",
                "description": "Абонементы для утренних визитов.",
                "action_items": ["Сделать скидку 15%", "Push-уведомления"],
                "associated_products": ["Alfa-Loyalty"],
                "metric_drop": 10.0,
            },
            {
                "category": "Retail",
                "target_metric": "official_revenue",
                "okved": "47.11",
                "title": "СБП-квест",
                "description": "Перевод на СБП у кассы с кэшбеком.",
                "action_items": ["QR на кассе", "Кэшбек"],
                "associated_products": ["Alfa-SBP"],
                "metric_drop": 8.0,
            },
        ]

        for c in cases:
            context = rag.build_context_query(c["category"], c.get("okved"), c["target_metric"], c.get("metric_drop", 5.0))
            vec = rag.encode_text(context)
            entry = KnowledgeBaseEntry(
                id=f"kb_{uuid.uuid4().hex[:8]}",
                category=c["category"],
                okved=c.get("okved"),
                target_metric=c["target_metric"],
                title=c["title"],
                description=c["description"],
                action_items=c["action_items"],
                associated_products=c["associated_products"],
                embedding=vec,
            )
            session.add(entry)

    print("Seeded RAG KB")


if __name__ == '__main__':
    seed_knowledge_base()
