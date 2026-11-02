import { describe, expect, it } from 'vitest';
import { auditOpenRouterFreeUsage } from './openrouterFreeAudit';

describe('auditOpenRouterFreeUsage', () => {
  it('keeps missing cost unknown while accepting only free, zero-cost responses', () => {
    const audit = auditOpenRouterFreeUsage([
      {
        provider: 'openrouter',
        model_name: 'provider/model:free',
        succeeded: true,
        reported_cost_usd: 0,
      },
      {
        provider: 'openrouter',
        model_name: 'openrouter/free',
        succeeded: false,
        reported_cost_usd: null,
      },
    ]);

    expect(audit.no_reported_nonzero_cost).toBe(true);
    expect(audit.unknown_reported_cost_entries).toBe(1);
    expect(audit.accepted_responses_report_zero_cost).toBe(true);
    expect(audit.accepted_response_count).toBe(1);
    expect(audit.all_reported_models_free).toBe(true);
  });

  it('flags positive costs and paid or unidentified returned models', () => {
    const audit = auditOpenRouterFreeUsage([
      {
        provider: 'openrouter',
        model_name: 'provider/model-paid',
        succeeded: true,
        reported_cost_usd: 0.01,
      },
    ]);

    expect(audit.no_reported_nonzero_cost).toBe(false);
    expect(audit.accepted_responses_report_zero_cost).toBe(false);
    expect(audit.all_reported_models_free).toBe(false);
  });

  it('flags records beyond the explicit local test cap', () => {
    const usage = Array.from({ length: 3 }, () => ({
      provider: 'openrouter',
      model_name: 'openrouter/free',
      succeeded: false,
      reported_cost_usd: null,
    }));

    expect(auditOpenRouterFreeUsage(usage, 2).total_usage_records_at_or_below_free_test_cap).toBe(
      false,
    );
  });
});
