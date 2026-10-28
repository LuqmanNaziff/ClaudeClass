from typing import Any
from pymongo import DESCENDING
from app.schemas.ticket import TicketResponse


# Projection hides MongoDB's internal _id; everything else is the ticket shape.
TICKET_PROJECTION = {"_id": 0}


class TicketRepository:
    def __init__(
        self,
        database: Any,
    ) -> None:
        # Repositories own database access; routes and services do not.
        self.collection = database.tickets

    async def insert(
        self,
        ticket: TicketResponse,
    ) -> TicketResponse:
        # The ticket was already validated by Pydantic; store it as a plain dict.
        await self.collection.insert_one(ticket.model_dump(mode="python"))
        return ticket

    async def replace(self, ticket: TicketResponse) -> TicketResponse:
        # The ticket was already validated by Pydantic; store it as a plain dict.
        result = (
            await self.collection.replace_one(
                {"ticket_id": ticket.ticket_id},
                ticket.model_dump(mode="python"),
            )
        )

        if result.matched_count != 1:
            raise RuntimeError("Ticket not found")

        return ticket

    
    async def get_by_id(
        self,
        ticket_id: str,
    ) -> TicketResponse | None:
        # Scope the query to both the current customer and the requested ticket.
        document = await self.collection.find_one(
            {
                "ticket_id": ticket_id,
            },
            TICKET_PROJECTION,
        )

        # No matching ticket pair means no authorized ticket is available.
        if document is None:
            return None

        # Validate database data before the rest of the application uses it.
        return TicketResponse.model_validate(document)

    async def list(
        self,
        customer_id: str | None = None,
        limit: int = 20,
        skip: int = 0,
    ) -> tuple[list[TicketResponse], int]:
        # Only ever return the current customer's tickets, newest first.
        query: dict[str, object] = {}
        
        #Optional customer_id filter for admin use cases
        if customer_id:
            query["customer_id"] = customer_id

        total = await self.collection.count_documents(query)

        # Newest tickets first, then apply pagination
        cursor = (
            self.collection.find(query, TICKET_PROJECTION)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        items: list[TicketResponse] = []

        async for document in cursor:
            items.append(TicketResponse.model_validate(document))

        return items, total
