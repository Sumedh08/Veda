"""Pure call and completion-capacity planning for model-assisted research stages."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PlannedModelOperation:
    operation: str
    stage: str
    batch: int
    completion_tokens: int
    priority: int = 10
    minimum_completion_tokens: int = 1

    def __post_init__(self) -> None:
        if not self.operation or len(self.operation) > 80:
            raise ValueError("operation identity must be a bounded non-empty string")
        if not self.stage or len(self.stage) > 40:
            raise ValueError("stage identity must be a bounded non-empty string")
        if type(self.batch) is not int or self.batch < 1:
            raise ValueError("operation batch must be a positive integer")
        if type(self.completion_tokens) is not int or self.completion_tokens < 1:
            raise ValueError("completion-token capacity must be a positive integer")
        if type(self.priority) is not int:
            raise ValueError("operation priority must be an integer")
        if type(self.minimum_completion_tokens) is not int or self.minimum_completion_tokens < 1:
            raise ValueError("minimum completion-token capacity must be a positive integer")


def plan_model_execution(
    operations: list[PlannedModelOperation],
    *,
    available_calls: int,
    available_output_tokens: int,
    max_output_tokens_per_call: int,
    provider_completion_limit: int | None = None,
) -> dict:
    """Return explicit accepted/deferred work without changing operation budgets.

    Lower priority numbers reserve capacity first. The caller must surface every
    deferred item and may only dispatch operations listed in ``accepted``. Call
    and total output-token limits are independent constraints.
    """
    for value, name in (
        (available_calls, "available_calls"),
        (available_output_tokens, "available_output_tokens"),
        (max_output_tokens_per_call, "max_output_tokens_per_call"),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if provider_completion_limit is not None and (
        type(provider_completion_limit) is not int or provider_completion_limit < 1
    ):
        raise ValueError("provider completion limit must be a positive integer or unknown")

    accepted: list[dict] = []
    deferred: list[dict] = []
    calls_used = 0
    output_tokens_used = 0
    # Reserve later required stages before optional additional evidence batches.
    for operation in sorted(operations, key=lambda item: (item.priority, item.stage, item.batch)):
        item = asdict(operation)
        reason = None
        if operation.completion_tokens < operation.minimum_completion_tokens:
            reason = "insufficient_operation_capacity"
        elif operation.completion_tokens > max_output_tokens_per_call:
            reason = "veda_completion_capacity"
        elif (
            provider_completion_limit is not None
            and operation.completion_tokens > provider_completion_limit
        ):
            reason = "provider_completion_limit"
        elif calls_used >= available_calls:
            reason = "request_quota"
        elif output_tokens_used + operation.completion_tokens > available_output_tokens:
            reason = "output_token_budget"
        if reason:
            deferred.append({**item, "deferred_reason": reason})
        else:
            accepted.append(item)
            calls_used += 1
            output_tokens_used += operation.completion_tokens

    # Report both lists in research execution order, while allocation above remains priority-aware.
    order = {
        (item.stage, item.batch, item.operation): index for index, item in enumerate(operations)
    }

    def sort_key(item):
        return order[(item["stage"], item["batch"], item["operation"])]

    accepted.sort(key=sort_key)
    deferred.sort(key=sort_key)
    return {
        "required_calls": len(operations),
        "available_calls": available_calls,
        "planned_calls": len(accepted),
        "deferred_calls": len(deferred),
        "required_output_tokens": sum(item.completion_tokens for item in operations),
        "planned_output_tokens": output_tokens_used,
        "complete": not deferred,
        "accepted": accepted,
        "deferred": deferred,
    }
