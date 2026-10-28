import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.repositories.faq_repository import FAQRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.agent import (
    EscalateTicketArgs,
    GetOrderStatusArgs,
    SearchFAQArgs,
    ToolName,
)
from app.schemas.common import TicketStatus
from app.schemas.faq import FAQSource
from app.schemas.order import OrderContext
from app.schemas.ticket import TicketResponse
from app.services.ticket_service import TicketService


# AgentService -> ToolRegistry.execute() -> validate -> authorise -> run
# The registry is the safety boundary of the agent. Claude can only ask for a
# tool by name; this class decides whether the request is allowed and does the
# real work with ordinary application code. Claude never touches MongoDB.

# What one tool call produces. Immutable (frozen) like the other result objects.
@dataclass(frozen=True)
class ToolExecutionResult:
    # Content goes back to Claude as tool_result data.
    content: str      # JSON text sent back to Claude
    is_error: bool    # Tells Claude whether the tool call failed
    summary: str      # Short text for the audit list shown in the API response

    # Trusted context is also returned to ordinary application code.
    order_context: (OrderContext | None) = None
    faq_context: (list[FAQSource] | None) = None


# A new registry is created for every request, so each tool is tied to one
# customer, one allowed order and one ticket. Claude cannot change any of these.
class ToolRegistry:
    def __init__(
        self,
        *,
        order_repository:
            OrderRepository,
        faq_repository:
            FAQRepository,
        ticket_service:
            TicketService,
        customer_id: str,
        allowed_order_id:
            str | None,
        ticket_id: str,
    ) -> None:
        # Bind tools to the current request/customer/ticket context.
        self.order_repository = order_repository
        self.faq_repository = faq_repository
        self.ticket_service = ticket_service
        self.customer_id = customer_id
        self.allowed_order_id = allowed_order_id
        self.ticket_id = ticket_id

    def definitions(
        self,
    ) -> list[dict[str, Any]]:
        # These schemas describe the only capabilities Claude is told exist.
        # Each entry is name + description + input_schema. Claude reads the
        # description to decide when to use a tool, and the schema (generated
        # from the Args models) to know which arguments to send.
        return [
            {
                "name": (
                    ToolName
                    .GET_ORDER_STATUS
                    .value
                ),
                "description": (
                    "Retrieve order status "
                    "for the order supplied "
                    "with the current support "
                    "request."
                ),
                "input_schema": (
                    GetOrderStatusArgs
                    .model_json_schema()
                ),
            },
            {
                "name": (
                    ToolName.SEARCH_FAQ
                    .value
                ),
                "description": (
                    "Search approved FAQ "
                    "knowledge for support "
                    "policy or guidance."
                ),
                "input_schema": (
                    SearchFAQArgs
                    .model_json_schema()
                ),
            },
            {
                "name": (
                    ToolName
                    .ESCALATE_TICKET
                    .value
                ),
                "description": (
                    "Escalate the current "
                    "support ticket for "
                    "human handling."
                ),
                "input_schema": (
                    EscalateTicketArgs
                    .model_json_schema()
                ),
            },
        ]

    # Entry point used by the agent loop for every tool_use block. raw_input is
    # exactly what Claude sent, so it is untrusted until a tool validates it.
    # The result always comes back as a ToolExecutionResult, never an exception,
    # so one bad tool call does not crash the whole request.
    async def execute(
        self,
        tool_name: str,
        raw_input: Any,
    ) -> ToolExecutionResult:
        # Application-side allowlist: a model-requested name is not authority.
        allowed = {
            item.value
            for item in ToolName
        }

        if tool_name not in allowed:
            return ToolExecutionResult(
                content=json.dumps(
                    {
                        "error":
                            "Tool is not "
                            "allowlisted."
                    }
                ),
                is_error=True,
                summary=(
                    "Blocked non-"
                    "allowlisted tool."
                ),
            )

        # Dispatch only to explicitly implemented application capabilities.
        if (
            tool_name
            == ToolName
            .GET_ORDER_STATUS
            .value
        ):
            return (
                await self
                ._get_order_status(
                    raw_input
                )
            )

        if (
            tool_name
            == ToolName
            .SEARCH_FAQ
            .value
        ):
            return (
                await self._search_faq(
                    raw_input
                )
            )

        # The allowlist check above guarantees the only name left is escalate_ticket.
        return (
            await self._escalate_ticket(
                raw_input
            )
        )

    # Tool: get_order_status. Three checks run in this order: valid arguments,
    # an order ID exists on the request, and it matches that ID. Only then
    # does the repository query the database.
    async def _get_order_status(
        self,
        raw_input: Any,
    ) -> ToolExecutionResult:
        try:
            # Validate model-proposed arguments before using them.
            args = (
                GetOrderStatusArgs
                .model_validate(
                    raw_input
                )
            )
        except ValidationError:
            return (
                self._invalid_arguments(
                    ToolName
                    .GET_ORDER_STATUS
                )
            )

        # No order on the current request means no order lookup authority.
        if self.allowed_order_id is None:
            return ToolExecutionResult(
                content=json.dumps(
                    {
                        "error":
                            "No order ID was "
                            "supplied."
                    }
                ),
                is_error=True,
                summary=(
                    "Order lookup blocked: "
                    "no request order ID."
                ),
            )

        # Prevent Claude from switching to a different order ID.
        if (
            args.order_id
            != self.allowed_order_id
        ):
            return ToolExecutionResult(
                content=json.dumps(
                    {
                        "error":
                            "Order ID not "
                            "permitted for this "
                            "request."
                    }
                ),
                is_error=True,
                summary=(
                    "Blocked different "
                    "order ID."
                ),
            )

        # Repository adds the customer scope as the final data-access boundary.
        order = (
            await self.order_repository
            .get_order_for_customer(
                self.customer_id,
                args.order_id,
            )
        )

        # Not found is a normal answer, not an error. The same result is
        # returned if the order exists but belongs to another customer, so
        # Claude learns nothing about orders the customer cannot see.
        if order is None:
            return ToolExecutionResult(
                content=json.dumps(
                    {
                        "found": False,
                    }
                ),
                is_error=False,
                summary=(
                    "No authorized order "
                    "was found."
                ),
            )

        # order_context hands the verified order back to AgentService, so it
        # can be saved on the ticket without relying on Claude's wording.
        return ToolExecutionResult(
            content=json.dumps(
                {
                    "found": True,
                    "order":
                        order.model_dump(
                            mode="json"
                        ),
                }
            ),
            is_error=False,
            summary=(
                f"Verified order "
                f"{order.order_id} "
                f"with status "
                f"{order.status.value}."
            ),
            order_context=order,
        )

    # Tool: search_faq. Claude chooses the query text, but the search itself
    # is a normal repository call that only returns approved FAQ records.
    async def _search_faq(
        self,
        raw_input: Any,
    ) -> ToolExecutionResult:
        try:
            # Tool arguments are validated with the same strict-model boundary.
            args = (
                SearchFAQArgs
                .model_validate(
                    raw_input
                )
            )
        except ValidationError:
            return (
                self._invalid_arguments(
                    ToolName.SEARCH_FAQ
                )
            )

        # FAQ retrieval remains ordinary application/database work.
        results = (
            await self.faq_repository
            .search(
                args.query,
                limit=3,
            )
        )

        return ToolExecutionResult(
            content=json.dumps(
                {
                    "matches": [
                        item.model_dump(
                            mode="json"
                        )
                        for item
                        in results
                    ]
                }
            ),
            is_error=False,
            summary=(
                "FAQ search returned "
                f"{len(results)} "
                "approved record(s)."
            ),
            faq_context=results,
        )

    # Tool: escalate_ticket. The only tool that changes saved data. It marks
    # the current ticket as ESCALATED with Claude's reason, and nothing else.
    async def _escalate_ticket(
        self,
        raw_input: Any,
    ) -> ToolExecutionResult:
        try:
            # Validate the escalation reason before changing application state.
            args = (
                EscalateTicketArgs
                .model_validate(
                    raw_input
                )
            )
        except ValidationError:
            return (
                self._invalid_arguments(
                    ToolName
                    .ESCALATE_TICKET
                )
            )

        # Escalation is bound to the current ticket only.
        ticket = (
            await self.ticket_service
            .get(self.ticket_id)
        )

        if ticket is None:
            return ToolExecutionResult(
                content=json.dumps(
                    {
                        "error":
                            "Current ticket "
                            "not found."
                    }
                ),
                is_error=True,
                summary=(
                    "Escalation failed: "
                    "ticket missing."
                ),
            )

        # Python constructs the state change; the model does not edit MongoDB.
        updated = (
            TicketResponse.model_validate(
                {
                    **ticket.model_dump(
                        mode="python"
                    ),
                    "status":
                        TicketStatus
                        .ESCALATED,
                    "escalation_reason":
                        args.reason,
                    "updated_at":
                        datetime.now(
                            timezone.utc
                        ),
                }
            )
        )

        await self.ticket_service.save(
            updated
        )

        return ToolExecutionResult(
            content=json.dumps(
                {
                    "success": True,
                    "ticket_id":
                        ticket.ticket_id,
                    "status":
                        TicketStatus
                        .ESCALATED.value,
                }
            ),
            is_error=False,
            summary=(
                "Current ticket "
                "escalated."
            ),
        )

    # Shared error result for all three tools. The message is deliberately
    # generic: it does not echo back the invalid input or the Pydantic details.
    @staticmethod
    def _invalid_arguments(
        tool_name: ToolName,
    ) -> ToolExecutionResult:
        # Return a controlled tool error instead of executing invalid input.
        return ToolExecutionResult(
            content=json.dumps(
                {
                    "error":
                        "Tool arguments "
                        "failed validation."
                }
            ),
            is_error=True,
            summary=(
                "Invalid arguments "
                f"blocked for "
                f"{tool_name.value}."
            ),
        )
