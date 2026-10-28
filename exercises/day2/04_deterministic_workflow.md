# Exercise 04 — Build a Deterministic Ticket Workflow

## Goal

Combine existing application capabilities into one multi-step workflow whose
sequence is controlled by Python application code.

## Time

Approximately 40 minutes.

## Starting point

Working components already exist for:

```text
ticket analysis
order retrieval
FAQ retrieval
ticket persistence
response generation
```

A `WorkflowService` starter and workflow request/response models are provided.

## Requirement

Implement:

```text
POST /workflows/process-ticket
```

The workflow must analyse a support request, obtain required trusted context
where appropriate, persist the ticket, generate a response, update the ticket,
and report which steps executed.

## Before coding

Write the workflow in pseudocode.

Think about:

- when order lookup is necessary
- when FAQ retrieval is necessary
- what happens when required context is unavailable
- when the ticket should be created
- when it should be updated
- which component should determine final application status

## Constraints

- The developer/application controls the sequence.
- Claude must not query MongoDB directly.
- Reuse existing repositories and services.
- Missing required trusted context must not be silently replaced with invented
  facts.
- Do not add tool-calling/agent logic to this workflow.

## Test scenarios

Your instructor will provide scenarios such as:

```text
delivery issue with order ID
return/policy question
urgent complaint requiring review
```

Predict the executed steps before sending each request.

## Deliverable

For one scenario show:

```text
predicted steps
actual executed_steps
final ticket status
trusted context used
```

Then answer:

> Who chose the order of operations in this workflow?
