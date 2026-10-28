from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.prompt_data import serialize_prompt_payload
from app.prompts.agent import AGENT_SYSTEM_PROMPT
from app.repositories.faq_repository import FAQRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.agent import (
    AgentSupportRequest,
    ToolExecutionAudit,
)
from app.schemas.common import (
    Priority,
    TicketStatus,
)
from app.schemas.faq import FAQSource
from app.schemas.order import OrderContext
from app.schemas.ticket import (
    TicketCreateRequest,
    TicketResponse,
)
from app.schemas.usage import AIUsage
from app.services.analysis_service import AnalysisService
from app.services.claude_service import (
    ClaudeResponseError,
    ClaudeService,
)
from app.services.ticket_service import TicketService
from app.tools.registry import ToolRegistry


# route -> AgentService -> analyse -> create ticket
#       -> loop: Claude proposes a tool -> ToolRegistry runs it -> result back to Claude
#       -> final reply -> application sets status -> save ticket
# An agentic workflow: Claude decides which tools to call and in what order,
# but the application controls everything that matters. It lists the tools,
# validates and runs each one, limits the number of rounds, and sets the
# final ticket status. Compare with WorkflowService, where Python fixes the steps.

# Keep the agent loop bounded for cost, latency, and application control.
# Without a limit, Claude could keep calling tools and the request would never end.
MAX_TOOL_ROUNDS = 3


# What the agent hands back to the route. Immutable (frozen) so it cannot be
# changed after the run has finished.
@dataclass(frozen=True)
class AgentResult:
    ticket: TicketResponse                  # The final ticket as saved in MongoDB
    final_response: str                     # The customer-facing answer from Claude
    tool_calls: list[ToolExecutionAudit]                                       # Application record of every tool call
    iterations: int                         # How many Claude calls were made
    analysis_usage: AIUsage                 # Tokens used by the analysis call
    agent_usage: AIUsage                    # Tokens used by all agent-loop calls


class AgentService:
    def __init__(
        self,
        *,
        claude_service: ClaudeService,
        analysis_service:AnalysisService,
        ticket_service:TicketService,
        order_repository:OrderRepository,
        faq_repository:FAQRepository,
    ) -> None:
        # Everything is passed in (not created here), so the route controls
        # the lifecycle (including closing Claude) and tests can use fakes.
        # claude_service is used directly for the loop; the repositories are
        # not called here but handed to the ToolRegistry, which runs the tools.
        self.claude_service = claude_service
        self.analysis_service = analysis_service
        self.ticket_service = ticket_service
        self.order_repository = order_repository
        self.faq_repository = faq_repository

    async def support(
        self,
        request: AgentSupportRequest,
    ) -> AgentResult:
        # Step 1: First obtain the same validated analysis used elsewhere in the app.
        analysis_result = (
            await self.analysis_service
            .analyse(request.message)
        )

        # Step 2: Create the current application ticket before tool use begins.
        # The escalate_ticket tool needs an existing ticket to update.
        ticket = (
            await self.ticket_service
            .create(
                TicketCreateRequest(
                    customer_id=(request.customer_id),
                    order_id=(request.order_id),
                    message=(request.message),
                ),
                analysis_result.data,
            )
        )

        # Registry binds available tools to this request/customer/ticket.
        # customer_id and allowed_order_id come from the request, not from
        # Claude, so the model cannot ask about a different customer's order.
        registry = ToolRegistry(
            order_repository = self.order_repository,
            faq_repository = self.faq_repository,
            ticket_service = self.ticket_service,
            customer_id = request.customer_id,
            allowed_order_id = request.order_id,
            ticket_id = ticket.ticket_id,
        )

        # Initial user message contains application-created structured context.
        # serialize_prompt_payload turns the dict into prompt text with the
        # customer's message as a clearly separated, untrusted field.
        # messages is the full conversation; each loop round appends to it.
        messages: list[
            dict[str, Any]
        ] = [
            {
                "role": "user",
                "content":
                    serialize_prompt_payload(
                        {
                            "order_id":
                                request.order_id,
                            "analysis":
                                analysis_result
                                .data
                                .model_dump(mode="json"),
                            "customer_message":
                                request.message,
                        }
                    ),
            }
        ]

        # Keep an application-side audit of actual tool execution.
        tool_calls: list[ToolExecutionAudit] = []

        # Trusted context collected from successful tool runs. It is saved on
        # the ticket at the end. FAQs are keyed by ID so a record returned by
        # two searches is stored only once.
        order_context: (OrderContext | None) = None
        faq_by_id: dict[
            str,
            FAQSource,
        ] = {}

        # Usage is added up across every Claude call in the loop.
        total_input_tokens = 0
        total_output_tokens = 0
        model_name = (self.claude_service.model)
        iterations = 0
        final_response: str | None = None

        # Step 3: the agent loop. Each round is: ask Claude -> if it requests
        # tools, run them and send the results back -> ask again. The loop ends
        # when Claude answers without a tool request, or after MAX_TOOL_ROUNDS.
        # Claude may choose among permitted tools, but only for a bounded number of rounds.
        for _ in range(
            MAX_TOOL_ROUNDS
        ):
            response = (
                await self.claude_service
                .create_message(
                    messages,
                    system=(AGENT_SYSTEM_PROMPT),
                    tools=(registry.definitions()),
                    max_tokens=600,
                )
            )

            iterations += 1
            model_name = response.model
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Preserve assistant content so subsequent tool results follow the protocol.
            assistant_content = self._assistant_content(response.content)

            messages.append(
                {
                    "role": "assistant",
                    "content":
                        assistant_content,
                }
            )

            # Tool-use blocks are requests that the application must inspect/execute.
            # Claude cannot run anything itself; a block is only a request.
            tool_blocks = [
                block
                for block
                in response.content
                if block.type
                == "tool_use"
            ]

            # No tool request means Claude has produced its final text for this round.
            if not tool_blocks:
                final_response = self._extract_text(response.content)
                break

            # Results for this round, sent back to Claude in a single user message.
            tool_results = []

            for block in tool_blocks:
                # Registry validation/authorization happens before any real action.
                execution = (
                    await registry.execute(
                        block.name,
                        block.input,
                    )
                )

                # Store model-proposed arguments for the application audit trail.
                arguments = (
                    dict(block.input)
                    if isinstance(
                        block.input,
                        dict,
                    )
                    else {
                        "raw":
                            str(block.input)
                    }
                )

                tool_calls.append(
                    ToolExecutionAudit(
                        tool_name = block.name,
                        arguments = arguments,
                        success = not execution.is_error,
                        result_summary = execution.summary,
                    )
                )

                # Capture trusted context produced by successful application tools.
                if (
                    execution.order_context
                    is not None
                ):
                    order_context = execution.order_context

                if (
                    execution.faq_context
                    is not None
                ):
                    for faq in (
                        execution.faq_context
                    ):
                        faq_by_id[
                            faq.faq_id
                        ] = faq

                # Return the application's tool result to Claude using the SDK protocol.
                # tool_use_id links this result to the request it answers.
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": execution.content,
                        "is_error": execution.is_error,
                    }
                )

            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )

        # If all tool rounds were used, request one final text-only response.
        # No tools are passed this time, so Claude can only answer in text.
        if final_response is None:
            response = (
                await self.claude_service
                .create_message(
                    messages,
                    system = AGENT_SYSTEM_PROMPT,
                    max_tokens = 600,
                )
            )
            iterations += 1
            model_name = response.model
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            final_response = self._extract_text(response.content)

        # Never save or return an empty answer as if it were valid.
        if not final_response:
            raise ClaudeResponseError(
                "Agent returned no customer-facing response."
            )

        # Reload the ticket because a tool may have changed it (for example escalation).
        current_ticket = (
            await self.ticket_service
            .get(ticket.ticket_id)
        )

        if current_ticket is None:
            raise RuntimeError("Agent ticket missing.")

        # Keep at most 3 FAQ records on the ticket, matching the search limit.
        faq_context = list(
            faq_by_id.values()
        )[:3]

        # Step 4: Application code, not Claude prose, determines the final status.
        # An escalation made by the tool is kept. Otherwise the same rules as
        # the deterministic workflow apply: flag for human review if the
        # analysis asked for it, the ticket is urgent, or required trusted
        # context (order or FAQ) was never retrieved.
        if current_ticket.status == TicketStatus.ESCALATED:
            final_status = TicketStatus.ESCALATED
        else:
            needs_review = (
                current_ticket.analysis.needs_human_review
                or
                current_ticket.analysis.priority == Priority.URGENT
            )

            if (
                current_ticket.analysis.needs_order_lookup
                and
                order_context is None
            ):
                needs_review = True

            if (
                current_ticket.analysis.needs_faq_lookup
                and not
                faq_context
            ):
                needs_review = True

            final_status = (
                TicketStatus.NEEDS_HUMAN_REVIEW
                if needs_review
                else TicketStatus.PROCESSED
            )

        # Step 5: Persist trusted context, final draft, and application-controlled status.
        updated_ticket = (
            TicketResponse.model_validate(
                {
                    **current_ticket
                    .model_dump(mode="python"),
                    "order_context": order_context,
                    "faq_context": faq_context,
                    "draft_response": final_response,
                    "status": final_status,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        )

        updated_ticket = await self.ticket_service.save(updated_ticket)

        # Keep analysis and agent usage separate for observability.
        return AgentResult(
            ticket=updated_ticket,
            final_response=final_response,
            tool_calls=tool_calls,
            iterations=iterations,
            analysis_usage=AIUsage(
                model = analysis_result.model,
                input_tokens = analysis_result.input_tokens,
                output_tokens = analysis_result.output_tokens,
            ),
            agent_usage = AIUsage(
                model = model_name,
                input_tokens = total_input_tokens,
                output_tokens = total_output_tokens,
            ),
        )

    # Helper (no self needed, hence staticmethod). A response can mix text
    # blocks with tool_use blocks, so only the text blocks are kept.
    @staticmethod
    def _extract_text(blocks: list[Any]) -> str:
        # Join all text blocks into the final customer-facing response.
        return "\n".join(
            block.text
            for block in blocks
            if block.type == "text"
        ).strip()

    # Helper. The API requires Claude's previous turn, including its tool_use
    # blocks, to be sent back before the matching tool_result. SDK block
    # objects are converted to plain dicts so they fit in the messages list.
    @staticmethod
    def _assistant_content(blocks: list[Any],) -> list[dict[str, Any]]:
        # Convert SDK content blocks into the form expected in the next message.
        content: list[
            dict[str, Any]
        ] = []

        for block in blocks:
            if block.type == "text":
                content.append(
                    {
                        "type": "text",
                        "text": block.text,
                    }
                )
            elif block.type == "tool_use":
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return content
