import type { JobEvent } from './types';

export type PlannedModelOperation = {
  operation: string;
  stage: string;
  batch: number;
  completion_tokens: number;
  deferred_reason?: string;
};

export type ModelExecutionPlan = {
  provider: string;
  model: string | null;
  complete: boolean;
  required_calls: number;
  planned_calls: number;
  deferred_calls: number;
  required_output_tokens: number;
  planned_output_tokens: number;
  reserved_calls_before_plan: number;
  authorized_spend_ceiling: number;
  authorized_spend_currency: string;
  remaining_authorized_spend: number;
  latency_estimate_ms: number | null;
  latency_estimate_status: string;
  daily_quota_snapshot: Record<string, unknown> | null;
  accepted: PlannedModelOperation[];
  deferred: PlannedModelOperation[];
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function operations(value: unknown): PlannedModelOperation[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: PlannedModelOperation[] = [];
  for (const item of value) {
    const row = record(item);
    if (!row || typeof row.operation !== 'string' || typeof row.stage !== 'string'
      || !Number.isInteger(row.batch) || !finiteNumber(row.batch)
      || !Number.isInteger(row.completion_tokens) || !finiteNumber(row.completion_tokens)) return null;
    parsed.push({
      operation: row.operation,
      stage: row.stage,
      batch: row.batch,
      completion_tokens: row.completion_tokens,
      ...(typeof row.deferred_reason === 'string' ? { deferred_reason: row.deferred_reason } : {}),
    });
  }
  return parsed;
}

function parsePlan(value: unknown): ModelExecutionPlan | null {
  const row = record(value);
  if (!row || typeof row.provider !== 'string' || typeof row.complete !== 'boolean'
    || !['required_calls', 'planned_calls', 'deferred_calls', 'required_output_tokens',
      'planned_output_tokens', 'reserved_calls_before_plan', 'authorized_spend_ceiling',
      'remaining_authorized_spend']
      .every((key) => finiteNumber(row[key]))
    || typeof row.authorized_spend_currency !== 'string'
    || typeof row.latency_estimate_status !== 'string') return null;
  const accepted = operations(row.accepted);
  const deferred = operations(row.deferred);
  if (!accepted || !deferred) return null;
  const quota = record(row.daily_quota_snapshot);
  return {
    provider: row.provider,
    model: typeof row.model === 'string' ? row.model : null,
    complete: row.complete,
    required_calls: row.required_calls as number,
    planned_calls: row.planned_calls as number,
    deferred_calls: row.deferred_calls as number,
    required_output_tokens: row.required_output_tokens as number,
    planned_output_tokens: row.planned_output_tokens as number,
    reserved_calls_before_plan: row.reserved_calls_before_plan as number,
    authorized_spend_ceiling: row.authorized_spend_ceiling as number,
    authorized_spend_currency: row.authorized_spend_currency,
    remaining_authorized_spend: row.remaining_authorized_spend as number,
    latency_estimate_ms: finiteNumber(row.latency_estimate_ms) ? row.latency_estimate_ms : null,
    latency_estimate_status: row.latency_estimate_status,
    daily_quota_snapshot: quota,
    accepted,
    deferred,
  };
}

export function latestModelExecutionPlan(events: JobEvent[]): ModelExecutionPlan | null {
  for (const event of [...events].reverse()) {
    if (event.event_type !== 'resource_plan') continue;
    const data = record(event.data);
    const plan = parsePlan(data?.model_execution_plan);
    if (plan) return plan;
  }
  return null;
}
