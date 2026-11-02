import { describe, expect, it } from 'vitest';
import { latestModelExecutionPlan } from './executionPlan';
import type { JobEvent } from './types';

function event(modelExecutionPlan: unknown): JobEvent {
  return {
    id: 'event-1',
    event_type: 'resource_plan',
    stage: 'appraisal',
    message: 'Pre-dispatch plan',
    created_at: '2026-10-30T00:00:00Z',
    data: { model_execution_plan: modelExecutionPlan },
  };
}

const validPlan = {
  provider: 'sarvam',
  model: 'sarvam-105b',
  complete: false,
  required_calls: 7,
  planned_calls: 6,
  deferred_calls: 1,
  required_output_tokens: 28_672,
  planned_output_tokens: 24_576,
  reserved_calls_before_plan: 1,
  authorized_spend_ceiling: 3.5,
  authorized_spend_currency: 'INR',
  remaining_authorized_spend: 3.1,
  latency_estimate_ms: null,
  latency_estimate_status: 'unavailable_no_validated_provider_stage_baseline',
  daily_quota_snapshot: {
    global_remaining: 12,
    per_user_remaining: 5,
  },
  accepted: [{ operation: 'appraisal', stage: 'appraisal', batch: 1, completion_tokens: 4096 }],
  deferred: [{ operation: 'semantic', stage: 'semantic_audit', batch: 1, completion_tokens: 4096, deferred_reason: 'request_quota' }],
};

describe('pre-dispatch model execution plan', () => {
  it('reads the latest saved plan with explicit deferred work and limits', () => {
    const result = latestModelExecutionPlan([event(validPlan)]);
    expect(result?.required_calls).toBe(7);
    expect(result?.planned_calls).toBe(6);
    expect(result?.deferred[0]?.deferred_reason).toBe('request_quota');
    expect(result?.latency_estimate_ms).toBeNull();
    expect(result?.daily_quota_snapshot?.per_user_remaining).toBe(5);
  });

  it('does not present a malformed or post-dispatch event as a workload plan', () => {
    const malformed = event({ ...validPlan, accepted: 'not-an-array' });
    const otherEvent = { ...event(validPlan), event_type: 'step_completed' };
    expect(latestModelExecutionPlan([malformed, otherEvent])).toBeNull();
  });
});
