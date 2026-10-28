from typing import Any

from app.schemas.faq import FAQSource


# Only approved support fields leave the repository boundary.
FAQ_SOURCE_PROJECTION = {
    "_id": 0,
    "faq_id": 1,
    "category": 1,
    "question": 1,
    "answer": 1,
}


class FAQRepository:
    def __init__(self,database: Any,) -> None:
        self.collection = database.faqs

    async def get_by_ids(
        self,
        faq_ids: list[str],
        *,
        limit: int = 3,
    ) -> list[FAQSource]:
        # Deduplicate caller-supplied IDs and keep the context intentionally small.
        requested_ids = list(
            dict.fromkeys(faq_ids)
        )[:limit]

        if not requested_ids:
            return []

        # Only active approved FAQs can be returned.
        cursor = self.collection.find(
            {
                "faq_id": {
                    "$in": requested_ids,
                },
                "active": True,
            },
            FAQ_SOURCE_PROJECTION,
        )

        found: dict[
            str,
            FAQSource,
        ] = {}

        async for document in cursor:
            faq = FAQSource.model_validate(
                document
            )
            found[faq.faq_id] = faq

        # Preserve the requested ID order when returning matches.
        return [
            found[faq_id]
            for faq_id in requested_ids
            if faq_id in found
        ]

    async def search(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[FAQSource]:
        search_query = query.strip()

        if not search_query:
            return []

        # Bound the number of FAQ records supplied to downstream AI calls.
        safe_limit = max(
            1,
            min(limit, 3),
        )

        # MongoDB performs retrieval; Claude does not browse the collection.
        pipeline = [
            {
                "$match": {
                    "active": True,
                    "$text": {
                        "$search":
                            search_query,
                    },
                }
            },
            {
                "$sort": {
                    "score": {
                        "$meta":
                            "textScore",
                    }
                }
            },
            {
                "$limit": safe_limit,
            },
            {
                "$project":
                    FAQ_SOURCE_PROJECTION,
            },
        ]

        cursor = (
            await self.collection.aggregate(
                pipeline
            )
        )

        results: list[FAQSource] = []

        async for document in cursor:
            results.append(
                FAQSource.model_validate(
                    document
                )
            )

        return results
