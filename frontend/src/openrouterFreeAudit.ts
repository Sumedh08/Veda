export type OpenRouterUsageRecord = {
  provider: string;
  model_name?: string | null;
  succeeded: boolean;
  reported_cost_usd?: number | null;
};

export type OpenRouterFreeAudit = {
  all_entries_openrouter: boolean;
  all_reported_models_free: boolean;
  no_reported_nonzero_cost: boolean;
  unknown_reported_cost_entries: number;
  accepted_responses_report_zero_cost: boolean;
  accepted_response_count: number;
  total_usage_records_at_or_below_free_test_cap: boolean;
  model_ids: string[];
};

export function auditOpenRouterFreeUsage(
  usage: OpenRouterUsageRecord[],
  maxUsageRecords = 50,
): OpenRouterFreeAudit {
  const knownCosts = usage
    .map((entry) => entry.reported_cost_usd)
    .filter((cost): cost is number => typeof cost === 'number' && Number.isFinite(cost));
  const accepted = usage.filter((entry) => entry.succeeded === true);
  const modelIds = [...new Set(usage.map((entry) => entry.model_name).filter((model): model is string => Boolean(model)))];
  const isFreeRoute = (model: string | null | undefined) =>
    model === 'openrouter/free' || Boolean(model?.endsWith(':free'));

  return {
    all_entries_openrouter: usage.every((entry) => entry.provider === 'openrouter'),
    all_reported_models_free: usage.every((entry) => isFreeRoute(entry.model_name)),
    no_reported_nonzero_cost: knownCosts.every((cost) => cost === 0),
    unknown_reported_cost_entries: usage.filter(
      (entry) => typeof entry.reported_cost_usd !== 'number' || !Number.isFinite(entry.reported_cost_usd),
    ).length,
    accepted_responses_report_zero_cost: accepted.every(
      (entry) => entry.reported_cost_usd === 0 && isFreeRoute(entry.model_name),
    ),
    accepted_response_count: accepted.length,
    total_usage_records_at_or_below_free_test_cap: usage.length <= maxUsageRecords,
    model_ids: modelIds,
  };
}
