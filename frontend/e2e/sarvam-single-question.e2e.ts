import { expect, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

const modelId = process.env.VEDA_SARVAM_EXPECTED_MODEL || "glm5.3-flash";
const runId = process.env.VEDA_SARVAM_RUN_ID || "glm53flash";
const jobBudgetInr = Number(
  process.env.VEDA_SARVAM_JOB_BUDGET_INR ||
    process.env.SARVAM_MAX_JOB_COST_INR ||
    "20",
);
const requestCap = Number(process.env.VEDA_SARVAM_REQUEST_CAP || "24");
const question = {
  id: "glm53flash-sarvam-developer-productivity",
  question:
    "Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?",
  context:
    "Synthesize empirical studies of generative-AI coding assistants and related developer tools. Compare controlled experiments, field studies, and repository or survey analyses without treating them as interchangeable. Separate task completion time, accepted output, throughput, code quality, rework, and review burden. Do not invent outcomes for a hypothetical company or infer causal effects from abstracts alone. Explain differences by task type and difficulty, developer experience, tool/version, study setting, outcome definition, adoption, and follow-up duration when the retrieved evidence supports those distinctions. Preserve nulls where methods or results are not available.",
  geography: "International; identify study locations when reported",
  population:
    "Software developers, programming tasks, and software teams studied in empirical generative-AI research",
  time_horizon:
    "Studies published 2022 onward, including follow-up duration where reported",
  decision_objective:
    "Explain whether observed productivity changes are consistent across empirical settings and what a 60-engineer product company could safely infer",
  comparator:
    "Comparable developer tasks or teams with and without generative-AI coding assistance, as defined in each study",
  target_outcome:
    "Task completion time, accepted work per developer time, code quality, rework, defects, review burden, and developer experience",
  denominator:
    "Study-specific developers, tasks, commits, or engineer-time; do not pool unlike denominators",
  assumptions_to_test:
    "Task choice and difficulty, participant experience, tool and model version, novelty and learning, selection into use, team spillovers, outcome measurement, reviewer effort, code-quality follow-up, and publication or reporting bias may explain heterogeneous findings.",
};

type SarvamUsage = {
  provider?: string;
  model_name?: string | null;
  succeeded?: boolean;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  reported_cost_inr?: number | null;
  estimated_cost_inr?: number | null;
  error_class?: string | null;
};

function auditSarvamUsage(
  usage: SarvamUsage[],
  maxUsageRecords: number,
  expectedModel: string,
) {
  const finite = (value: unknown): value is number =>
    typeof value === "number" && Number.isFinite(value) && value >= 0;
  const accepted = usage.filter((entry) => entry.succeeded === true);
  const estimateComplete = usage.every((entry) =>
    finite(entry.estimated_cost_inr),
  );
  const reportComplete = usage.every((entry) =>
    finite(entry.reported_cost_inr),
  );
  return {
    all_entries_sarvam: usage.every((entry) => entry.provider === "sarvam"),
    all_reported_models_exact:
      usage.length > 0 &&
      usage.every((entry) => entry.model_name === expectedModel),
    accepted_response_count: accepted.length,
    unknown_usage_metadata_entries: usage.filter(
      (entry) =>
        !finite(entry.prompt_tokens) || !finite(entry.completion_tokens),
    ).length,
    unknown_cost_metadata_entries: usage.filter(
      (entry) =>
        !finite(entry.reported_cost_inr) && !finite(entry.estimated_cost_inr),
    ).length,
    estimated_cost_inr: estimateComplete
      ? usage.reduce((sum, entry) => sum + Number(entry.estimated_cost_inr), 0)
      : null,
    reported_cost_inr: reportComplete
      ? usage.reduce((sum, entry) => sum + Number(entry.reported_cost_inr), 0)
      : null,
    total_usage_records_at_or_below_job_cap: usage.length <= maxUsageRecords,
    model_ids: [
      ...new Set(
        usage
          .map((entry) => entry.model_name)
          .filter((model): model is string => Boolean(model)),
      ),
    ],
  };
}

const requiredOperations = {
  planning: "veda_research_plan_selection_v1",
  appraisal: "veda_appraisal_batch_v2",
  comparison: "veda_comparison_batch_v1",
  synthesis: "veda_report_draft_v3",
  semantic_support: "veda_semantic_report_audit_v1",
} as const;

test("one bounded Sarvam research job completes and its saved evidence is inspected", async ({
  page,
}) => {
  test.setTimeout(1_200_000);
  test.skip(
    process.env.VEDA_SARVAM_LIVE_E2E !== "1",
    "Requires the one-question Sarvam opt-in and verified billing safety.",
  );
  expect(process.env.OPENAI_API_KEY || "").toBe("");
  expect(process.env.OPENROUTER_API_KEY || "").toBe("");
  expect(process.env.SARVAM_MODEL).toBe(modelId);
  expect(process.env.ALLOW_PAID_LLM_CALLS).toBe("true");
  expect(Number(process.env.SARVAM_MAX_JOB_COST_INR)).toBe(jobBudgetInr);
  expect(jobBudgetInr).toBeGreaterThan(0);
  expect(jobBudgetInr).toBeLessThanOrEqual(20);
  expect(requestCap).toBeGreaterThan(0);
  expect(requestCap).toBeLessThanOrEqual(24);
  expect(process.env.VEDA_SARVAM_BILLING_VERIFIED).toBe("1");
  expect(process.env.VEDA_SARVAM_OUTPUT_PATH).toBeTruthy();
  expect(process.env.VEDA_SARVAM_PREFLIGHT_PATH).toBeTruthy();
  expect(process.env.VEDA_SARVAM_REQUEST_COUNTER_PATH).toBeTruthy();
  expect(process.env.VEDA_SARVAM_RUN_STATE_PATH).toBeTruthy();

  await page.goto("/");
  await page
    .getByRole("button", { name: "Continue to local workspace" })
    .click();
  await page.waitForFunction(() => {
    const session = JSON.parse(
      sessionStorage.getItem("veda_local_session") || "{}",
    ) as { token?: string };
    return Boolean(session.token);
  });
  const seededProject = page.locator(".project-grid").getByRole("button", {
    name: /Local browser integration \(synthetic data\)/,
  });
  await expect(seededProject).toBeVisible();
  await seededProject.click();
  if (await page.getByRole("button", { name: "Open navigation" }).isVisible()) {
    await page.getByRole("button", { name: "Open navigation" }).click();
  }

  const apiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || "8001"}/api/v1`,
  ).origin;
  const resumeJobId = process.env.VEDA_SARVAM_RESUME_JOB_ID || "";
  const run = await page.evaluate(
    async ({
      apiOrigin,
      researchQuestion,
      resumeJobId,
      runId,
      expectedModel,
      budgetCeilingInr,
      requestLimit,
    }) => {
      type SafeFailure = { stage: string; class: string; http_status?: number };
      const session = JSON.parse(
        sessionStorage.getItem("veda_local_session") || "{}",
      ) as { token?: string };
      if (!session.token)
        throw new Error("Local browser session was unavailable.");
      const headers = {
        Authorization: `Bearer ${session.token}`,
        "Content-Type": "application/json",
      };
      const api = async (path: string, init: RequestInit = {}) => {
        // Each POST is issued once. This harness never resends an uncertain operation.
        const response = await fetch(`${apiOrigin}/api/v1${path}`, {
          ...init,
          headers,
        });
        const body = response.status === 204 ? null : await response.json();
        if (!response.ok) {
          const error = new Error(
            "Veda local API operation failed.",
          ) as Error & { status?: number; apiCode?: string };
          error.status = response.status;
          const detail = body?.detail;
          error.apiCode =
            typeof detail?.code === "string" ? detail.code : undefined;
          throw error;
        }
        return body as Record<string, any>;
      };

      const result: Record<string, any> = {
        question: researchQuestion.question,
        scope: researchQuestion,
        completed_all_ai_stages: false,
        report_saved: false,
        browser_inspection: {
          attempted: false,
          report_opened: false,
          citation_opened: false,
          original_passage_visible: false,
          methodological_assessment_visible: false,
        },
        errors: [] as SafeFailure[],
        resumed_existing_job: Boolean(resumeJobId),
      };
      let jobId: string | null = null;
      try {
        const terminalStatuses = new Set([
          "completed",
          "completed_with_limitations",
          "failed",
          "cancelled",
        ]);
        const projectList = (await api("/projects")) as {
          items: Record<string, any>[];
        };
        const project = projectList.items.find(
          (item) => item.title === "Local browser integration (synthetic data)",
        );
        if (!project)
          throw new Error("The isolated local test project was unavailable.");
        result.project_id = project.id;
        result.project = { id: project.id, title: project.title };
        let job: Record<string, any>;
        if (resumeJobId) {
          job = await api(`/research-jobs/${resumeJobId}`);
          if (
            job.project_id !== project.id ||
            job.question !== researchQuestion.question ||
            job.status !== "queued" ||
            Number(job.model_calls_reserved || 0) !== 0
          ) {
            throw new Error(
              "The existing T-112 job is no longer safe to resume.",
            );
          }
        } else {
          job = await api(`/projects/${project.id}/research-jobs`, {
            method: "POST",
            body: JSON.stringify({
              ...researchQuestion,
              depth: "standard",
              model_provider: "sarvam",
              model_name: expectedModel,
              budget_ceiling_usd: 0,
              budget_ceiling_inr: budgetCeilingInr,
              idempotency_key: `veda-${runId}-${Date.now()}`,
            }),
          });
        }
        jobId = job.id;
        result.job_id = jobId;
        result.job = job;
        result.advances = [];
        if (job.status !== "queued")
          throw new Error("The research job did not enter its queued state.");

        for (
          let step = 0;
          step < 48 && !terminalStatuses.has(job.status);
          step += 1
        ) {
          const operationKey = `veda-${runId}-step-${step + 1}`;
          // A transport error ends the test; the same POST is never retried.
          job = await api(`/research-jobs/${jobId}/advance`, {
            method: "POST",
            body: JSON.stringify({ operation_key: operationKey }),
          });
          result.job = job;
          result.advances.push({
            status: job.status,
            current_stage: job.current_stage,
            model_calls_reserved: job.model_calls_reserved,
            error_class: job.error_class,
          });
          if (Number(job.model_calls_reserved || 0) > requestLimit) {
            result.errors.push({
              stage: job.current_stage || "unknown",
              class: "local_model_call_limit_exceeded",
            });
            break;
          }
        }
      } catch (error) {
        const safe = error as Error & { status?: number; apiCode?: string };
        result.errors.push({
          stage: result.job?.current_stage || "job_creation_or_advance",
          class: safe.apiCode || safe.name || "browser_api_error",
          ...(safe.status ? { http_status: safe.status } : {}),
        });
        if (jobId) {
          try {
            result.job = await api(`/research-jobs/${jobId}`);
          } catch {
            // The provider operation is not repeated; retain the last confirmed state.
          }
        }
      }

      if (jobId) {
        result.current_stage = result.job?.current_stage || null;
        result.job_status = result.job?.status || null;
        result.model_calls_reserved = Number(
          result.job?.model_calls_reserved || 0,
        );
        try {
          const exported = (await api("/me/export")) as {
            collections: Record<string, any[]>;
          };
          result.provider_usage = (
            exported.collections.usage_ledger || []
          ).filter((entry) => entry.job_id === jobId);
        } catch {
          result.provider_usage = [];
          result.errors.push({
            stage: "usage_collection",
            class: "usage_export_unavailable",
          });
        }
        try {
          result.events = (
            (await api(`/research-jobs/${jobId}/events`)) as { items: any[] }
          ).items;
          result.plan = await api(`/research-jobs/${jobId}/plan`);
          result.candidates = (
            (await api(`/research-jobs/${jobId}/candidates?limit=200`)) as {
              items: any[];
            }
          ).items;
          result.sources = (
            (await api(`/research-jobs/${jobId}/sources`)) as { items: any[] }
          ).items;
          result.claims = (
            (await api(`/research-jobs/${jobId}/claims`)) as { items: any[] }
          ).items;
          result.relationships_record = await api(
            `/research-jobs/${jobId}/relationships`,
          );
          result.relationships = result.relationships_record.items || [];
          result.hypotheses_record = await api(
            `/research-jobs/${jobId}/hypotheses`,
          );
          result.hypotheses = result.hypotheses_record.items || [];
        } catch (error) {
          const safe = error as Error & { status?: number; apiCode?: string };
          result.errors.push({
            stage: "evidence_inspection",
            class: safe.apiCode || safe.name || "inspection_error",
            ...(safe.status ? { http_status: safe.status } : {}),
          });
        }
        if (
          ["completed", "completed_with_limitations"].includes(
            result.job_status,
          )
        ) {
          try {
            result.report = await api(`/research-jobs/${jobId}/report`);
            result.report_saved = Boolean(result.report?.id);
            result.report_inspection = await api(
              `/reports/${result.report.id}/inspection`,
            );
            result.report_export = await api(
              `/reports/${result.report.id}/export?format=json`,
            );
            result.report_export_verified =
              result.report_export?.id === result.report?.id;
          } catch (error) {
            const safe = error as Error & { status?: number; apiCode?: string };
            result.errors.push({
              stage: "report_inspection_api",
              class: safe.apiCode || safe.name || "report_inspection_error",
              ...(safe.status ? { http_status: safe.status } : {}),
            });
          }
        }
      }

      const operations = new Set(
        (result.provider_usage || [])
          .filter((entry: Record<string, any>) => entry.succeeded === true)
          .map((entry: Record<string, any>) => entry.operation),
      );
      result.required_ai_operations = Object.fromEntries(
        Object.entries({
          planning: "veda_research_plan_selection_v1",
          appraisal: "veda_appraisal_batch_v2",
          comparison: "veda_comparison_batch_v1",
          synthesis: "veda_report_draft_v3",
          semantic_support: "veda_semantic_report_audit_v1",
        }).map(([stage, operation]) => [stage, operations.has(operation)]),
      );
      result.completed_all_ai_stages = Object.values(
        result.required_ai_operations,
      ).every(Boolean);
      result.source_counts = {
        candidates: result.candidates?.length || 0,
        selected: result.sources?.length || 0,
        claims: result.claims?.length || 0,
        citations: Object.keys(result.report?.citation_map || {}).length,
        relationships: result.relationships?.length || 0,
        hypotheses: result.hypotheses?.length || 0,
        providers_queried:
          result.report?.verification?.search_coverage?.provider_query_counts ||
          {},
        provider_results:
          result.report?.verification?.search_coverage
            ?.provider_result_counts || {},
      };
      result.source_access_classes = (result.sources || []).map(
        (source: Record<string, any>) => ({
          source_id: source.id,
          title: source.title,
          retrieval_status: source.retrieval_status,
          passage_access_levels: (source.passages || []).map(
            (passage: Record<string, any>) => passage.access_level,
          ),
          source_appraisal: source.appraisal,
        }),
      );
      result.claim_appraisals = (result.claims || []).map(
        (claim: Record<string, any>) => ({
          claim_id: claim.id,
          source_id: claim.source_id,
          text: claim.text,
          passage_ids: claim.passage_ids,
          appraisal: claim.appraisal,
        }),
      );
      result.study_design_contrasts = (result.relationships || []).map(
        (item: Record<string, any>) => ({
          relationship_type: item.relationship_type,
          scope_alignment: item.scope_alignment,
          scope_differences: item.scope_differences,
          rationale: item.rationale,
          evidence: item.evidence,
        }),
      );
      result.competing_hypotheses = result.hypotheses || [];
      const reportVerification = result.report?.verification || {};
      const successfulOperation = (stage: string) =>
        Boolean(result.required_ai_operations?.[stage]);
      result.stage_coverage = {
        planning: successfulOperation("planning"),
        scholarly_discovery: (result.sources?.length || 0) > 0,
        claim_extraction: (result.claims || []).some(
          (claim: Record<string, any>) =>
            Boolean(
              claim.source_id &&
              (claim.passage_id ||
                (Array.isArray(claim.passage_ids) &&
                  claim.passage_ids.length > 0)),
            ),
        ),
        methodological_appraisal: successfulOperation("appraisal"),
        claim_comparison_and_contradiction_analysis:
          successfulOperation("comparison"),
        competing_hypothesis_analysis_recorded:
          result.hypotheses_record?.status !== undefined &&
          result.hypotheses_record?.status !== "not_assessed",
        deterministic_citation_integrity:
          Boolean(reportVerification.status) &&
          (result.source_counts?.citations || 0) > 0,
        semantic_support_assessment:
          successfulOperation("semantic_support") &&
          String(reportVerification.semantic_support_check || "").startsWith(
            "performed_",
          ),
        model_synthesis:
          successfulOperation("synthesis") &&
          result.report?.model_name === expectedModel,
        report_persistence: Boolean(
          result.report_saved && result.report_inspection?.report?.id,
        ),
      };
      return result;
    },
    {
      apiOrigin,
      researchQuestion: question,
      resumeJobId,
      runId,
      expectedModel: modelId,
      budgetCeilingInr: jobBudgetInr,
      requestLimit: requestCap,
    },
  );

  let preflight: Record<string, any> | null = null;
  if (process.env.VEDA_SARVAM_PREFLIGHT_PATH) {
    preflight = JSON.parse(
      await readFile(process.env.VEDA_SARVAM_PREFLIGHT_PATH, "utf8"),
    ) as Record<string, any>;
  }
  const providerUsage = Array.isArray(run.provider_usage)
    ? run.provider_usage
    : [];
  let providerRequestAttempts: number | null = null;
  try {
    const counter = await readFile(
      process.env.VEDA_SARVAM_REQUEST_COUNTER_PATH!,
      "utf8",
    );
    if (/^\d+\s*$/.test(counter))
      providerRequestAttempts = Number(counter.trim());
  } catch {
    // Keep the missing counter visible in the final artifact and fail the strict guard below.
  }
  const runStatePath = process.env.VEDA_SARVAM_RUN_STATE_PATH!;
  let runState: Record<string, any> = {
    status: "no_provider_failure_artifact",
  };
  try {
    runState = JSON.parse(await readFile(runStatePath, "utf8")) as Record<
      string,
      any
    >;
  } catch {
    // The server writes this file only after a provider failure.
  }
  const planningUsage = providerUsage.find(
    (entry: Record<string, any>) =>
      entry.operation === requiredOperations.planning &&
      entry.succeeded === true,
  );
  const compatibilityProbe = {
    status: planningUsage
      ? "accepted_as_first_real_research_operation"
      : "not_accepted",
    accepted: Boolean(planningUsage),
    operation: requiredOperations.planning,
    separate_synthetic_request: false,
  };
  const preDispatchCircuitRecords = providerUsage.filter(
    (entry) => entry.error_class === "sarvam_live_run_stopped_after_failure",
  );
  const dispatchedUsage = providerUsage.filter(
    (entry) => entry.error_class !== "sarvam_live_run_stopped_after_failure",
  );
  const requestCountMatchesUsage =
    providerRequestAttempts === dispatchedUsage.length;
  const usageAudit = auditSarvamUsage(dispatchedUsage, requestCap, modelId);
  const actualModelIds = usageAudit.model_ids;
  const exactModelRoute =
    actualModelIds.length > 0 &&
    actualModelIds.every((model) => model === modelId);
  const artifactPath = process.env.VEDA_SARVAM_OUTPUT_PATH!;
  const artifact = {
    generated_at: new Date().toISOString(),
    authorization_scope:
      "one question only; Sarvam inference under ₹25 inclusive ceiling with at most ₹20 conservative pre-tax reservations; no OpenAI/OpenRouter, fallback, top-up, batch, or deployment",
    question: question.question,
    database_path: process.env.VEDA_SARVAM_DATABASE_PATH || null,
    resumed_from_attempt: process.env.VEDA_SARVAM_RESUME_FROM || null,
    configured_model: modelId,
    preflight,
    compatibility_probe: compatibilityProbe,
    run_state: runState,
    compatibility_probe_requests: 0,
    job_request_hard_cap: requestCap,
    provider_request_hard_cap: requestCap,
    authorized_total_spend_ceiling_inr: 25.0,
    maximum_pre_tax_reservation_inr: jobBudgetInr,
    tax_and_billing_rounding_headroom_inr: 5.0,
    conservative_combined_reservation_inr:
      Number(run.job?.cost_reserved_inr || 0) +
      Number(run.job?.cost_spent_estimate_inr || 0),
    cumulative_conservative_reservation_inr:
      Number(preflight?.prior_conservative_spend_inr || 0) +
      Number(run.job?.cost_reserved_inr || 0) +
      Number(run.job?.cost_spent_estimate_inr || 0),
    provider_request_attempts: providerRequestAttempts,
    provider_usage_records_for_dispatched_requests: dispatchedUsage.length,
    provider_usage_records_prevented_before_post:
      preDispatchCircuitRecords.length,
    request_count_matches_usage: requestCountMatchesUsage,
    provider_rate_limit_retries: 0,
    uncertain_post_resends: 0,
    exact_model_route: exactModelRoute,
    usage_audit: usageAudit,
    ...run,
  };
  await mkdir(dirname(artifactPath), { recursive: true });
  await writeFile(
    artifactPath,
    `${JSON.stringify(artifact, null, 2)}\n`,
    "utf8",
  );

  if (run.report_saved) {
    const browserInspection = run.browser_inspection;
    browserInspection.attempted = true;
    try {
      await page.getByRole("button", { name: "Reports" }).click();
      await expect(
        page.getByRole("heading", { name: "Report history" }),
      ).toBeVisible();
      const row = page.locator(".report-history-row").filter({
        has: page.getByRole("heading", {
          name: question.question,
          exact: true,
        }),
      });
      await expect(row).toHaveCount(1);
      await row.getByRole("button", { name: "Open report" }).click();
      await expect(
        page.getByRole("heading", { name: question.question, exact: true }),
      ).toBeVisible();
      await expect(page.locator(".report-content")).toBeVisible();
      browserInspection.report_opened = true;
      const markdownButton = page.getByRole("button", { name: "Markdown" });
      await expect(markdownButton).toBeVisible();
      const markdownDownloadPromise = page.waitForEvent("download");
      await markdownButton.click();
      const markdownDownload = await markdownDownloadPromise;
      browserInspection.markdown_export_downloaded =
        (await markdownDownload.failure()) === null;
      browserInspection.markdown_export_filename =
        markdownDownload.suggestedFilename();

      const citationIds = Object.keys(run.report?.citation_map || {});
      if (citationIds.length) {
        const citation = page
          .getByRole("button", { name: `Open source ${citationIds[0]}` })
          .first();
        await expect(citation).toBeVisible();
        await citation.click();
        const sourceDrawer = page.locator(".evidence-drawer");
        await expect(sourceDrawer).toBeVisible();
        const passage = sourceDrawer.locator(".passage-chip p").first();
        if (await passage.count()) {
          const text = (await passage.innerText()).trim();
          browserInspection.original_passage_visible = text.length > 0;
          browserInspection.first_visible_passage_excerpt = text.slice(0, 400);
        }
        browserInspection.source_metadata_visible =
          /Source metadata from (Crossref|OpenAlex|World Bank Data360|ILOSTAT)/.test(
            await sourceDrawer.innerText(),
          );
        browserInspection.source_methodological_appraisal_visible =
          /Methodological appraisal/.test(await sourceDrawer.innerText());
        browserInspection.citation_opened = true;
        await page
          .getByRole("button", { name: "Close source inspector" })
          .click();
      }

      const claimUnitDetails = page.locator(".claim-unit-manifest");
      if (await claimUnitDetails.count()) {
        await claimUnitDetails.locator("summary").click();
        const inspectClaim = page
          .getByRole("button", { name: "Inspect exact source span" })
          .first();
        if (await inspectClaim.count()) {
          await inspectClaim.click();
          const claimDrawer = page.locator(".evidence-drawer");
          await expect(claimDrawer).toBeVisible();
          const content = await claimDrawer.innerText();
          browserInspection.methodological_assessment_visible =
            /Methodological (appraisal|relationship)/.test(content);
          browserInspection.claim_inspector_excerpt = content.slice(0, 1200);
          await page
            .getByRole("button", { name: "Close evidence inspector" })
            .click();
        }
      }
    } catch {
      browserInspection.error_class = "browser_report_inspection_failed";
    }
  }

  artifact.browser_inspection = run.browser_inspection;
  artifact.operational_success = Boolean(
    run.report_saved &&
    ["completed", "completed_with_limitations"].includes(
      String(run.job_status),
    ) &&
    run.completed_all_ai_stages &&
    Object.values(run.stage_coverage || {}).every(Boolean) &&
    compatibilityProbe.accepted === true &&
    usageAudit.all_entries_sarvam &&
    usageAudit.all_reported_models_exact &&
    exactModelRoute &&
    usageAudit.accepted_response_count > 0 &&
    providerRequestAttempts !== null &&
    providerRequestAttempts <= requestCap &&
    requestCountMatchesUsage &&
    usageAudit.total_usage_records_at_or_below_job_cap &&
    Number(preflight?.prior_conservative_spend_inr || 0) +
      Number(run.job?.cost_reserved_inr || 0) +
      Number(run.job?.cost_spent_estimate_inr || 0) <=
      20.000001 &&
    run.browser_inspection.report_opened &&
    run.browser_inspection.markdown_export_downloaded &&
    run.report_export_verified &&
    run.browser_inspection.citation_opened &&
    run.browser_inspection.original_passage_visible &&
    run.browser_inspection.source_methodological_appraisal_visible,
  );
  await writeFile(
    artifactPath,
    `${JSON.stringify(artifact, null, 2)}\n`,
    "utf8",
  );

  expect(run.job_id).toBeTruthy();
  expect(run.model_calls_reserved).toBeLessThanOrEqual(requestCap);
  expect(providerRequestAttempts).not.toBeNull();
  expect(providerRequestAttempts).toBeLessThanOrEqual(requestCap);
  expect(requestCountMatchesUsage).toBe(true);
  expect(providerUsage.length).toBeLessThanOrEqual(requestCap);
  expect(usageAudit.all_entries_sarvam).toBe(true);
  expect(usageAudit.all_reported_models_exact).toBe(true);
  expect(exactModelRoute).toBe(true);
  expect(compatibilityProbe.accepted).toBe(true);
  expect(usageAudit.accepted_response_count).toBeGreaterThan(0);
  expect(usageAudit.total_usage_records_at_or_below_job_cap).toBe(true);
  expect(
    Number(run.job?.cost_reserved_inr || 0) +
      Number(run.job?.cost_spent_estimate_inr || 0),
  ).toBeLessThanOrEqual(jobBudgetInr + 0.000001);
  expect(
    Number(preflight?.prior_conservative_spend_inr || 0) +
      Number(run.job?.cost_reserved_inr || 0) +
      Number(run.job?.cost_spent_estimate_inr || 0),
  ).toBeLessThanOrEqual(20.000001);
  expect(run.report_saved).toBe(true);
  expect(run.completed_all_ai_stages).toBe(true);
  expect(Object.values(run.stage_coverage || {}).every(Boolean)).toBe(true);
  expect(["completed", "completed_with_limitations"]).toContain(run.job_status);
  expect(run.browser_inspection.report_opened).toBe(true);
  expect(run.browser_inspection.markdown_export_downloaded).toBe(true);
  expect(run.report_export_verified).toBe(true);
  expect(run.browser_inspection.citation_opened).toBe(true);
  expect(run.browser_inspection.original_passage_visible).toBe(true);
  expect(run.browser_inspection.source_methodological_appraisal_visible).toBe(
    true,
  );
  expect(artifact.operational_success).toBe(true);
});
