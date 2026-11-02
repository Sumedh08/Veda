import { defineConfig, devices } from "@playwright/test";

const openRouterLiveMode = process.env.VEDA_OPENROUTER_LIVE_E2E === "1";
const sarvamLiveMode = process.env.VEDA_SARVAM_LIVE_E2E === "1";
const openRouterT112Mode = process.env.VEDA_OPENROUTER_T112_E2E === "1";
const openRouterSingleQuestionMode =
  openRouterT112Mode || process.env.VEDA_OPENROUTER_SINGLE_QUESTION_E2E === "1";
const realApiMode =
  process.env.VEDA_REAL_API_E2E === "1" ||
  Boolean(process.env.VEDA_REAL_E2E_REUSE_DATABASE_PATH) ||
  openRouterLiveMode ||
  sarvamLiveMode;
const managedAuthMode = process.env.VEDA_MANAGED_AUTH_E2E === "1";
const partialSupabaseMode = process.env.VEDA_PARTIAL_SUPABASE_E2E === "1";
const apiPort = process.env.VEDA_REAL_E2E_API_PORT || "8001";
const apiBase =
  process.env.VEDA_E2E_API_BASE_URL || `http://127.0.0.1:${apiPort}/api/v1`;
const backendPython =
  process.env.VEDA_BACKEND_PYTHON ||
  (process.platform === "win32"
    ? ".venv\\Scripts\\python.exe"
    : ".venv/bin/python");
const frontendServer = {
  command: "npm run dev -- --port 5176 --strictPort",
  url: "http://127.0.0.1:5176",
  reuseExistingServer:
    !process.env.CI && !realApiMode && !managedAuthMode && !partialSupabaseMode,
  timeout: 30_000,
  ...(realApiMode
    ? {
        env: {
          VITE_API_BASE_URL: apiBase,
          // Do not let the Vite server inherit backend-only provider keys.
          OPENROUTER_API_KEY: "",
          OPENAI_API_KEY: "",
          SARVAM_API_KEY: "",
        },
      }
    : managedAuthMode
      ? {
          env: {
            VITE_API_BASE_URL: apiBase,
            VITE_SUPABASE_URL: "https://veda-auth-e2e.supabase.co",
            VITE_SUPABASE_ANON_KEY:
              "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.e2e-only-not-a-secret",
          },
        }
      : partialSupabaseMode
        ? {
            env: {
              VITE_API_BASE_URL: apiBase,
              VITE_SUPABASE_URL: "https://veda-auth-e2e.supabase.co",
              VITE_SUPABASE_ANON_KEY: "",
            },
          }
        : {}),
};
const backendServer = {
  command: `"${backendPython}" scripts/${sarvamLiveMode ? "serve_sarvam_glm53_research_e2e.py" : openRouterSingleQuestionMode ? "serve_openrouter_single_question_e2e.py" : openRouterLiveMode ? "serve_openrouter_browser_e2e.py" : "serve_browser_e2e.py"}`,
  cwd: "../backend",
  url: `http://127.0.0.1:${apiPort}/api/v1/health/ready`,
  reuseExistingServer: false,
  timeout: 90_000,
  name: "Veda isolated SQLite API",
  env: {
    VEDA_REAL_E2E_API_PORT: apiPort,
    VEDA_REAL_E2E_DATABASE_PATH: process.env.VEDA_REAL_E2E_DATABASE_PATH || "",
    VEDA_REAL_E2E_REUSE_DATABASE_PATH:
      process.env.VEDA_REAL_E2E_REUSE_DATABASE_PATH || "",
    WORLD_BANK_DOCUMENTS_NONCOMMERCIAL_USE_CONFIRMED:
      process.env.VEDA_WORLD_BANK_DOCUMENTS_NONCOMMERCIAL_USE_CONFIRMED === "1"
        ? "true"
        : "false",
    CRAWL4AI_ENABLED:
      process.env.VEDA_CRAWL4AI_LIVE_E2E === "1" ? "true" : "false",
    // The backend is the only child allowed to receive the process-only key.
    OPENROUTER_API_KEY: openRouterLiveMode
      ? process.env.OPENROUTER_API_KEY || ""
      : "",
    OPENROUTER_MODEL: openRouterLiveMode
      ? process.env.OPENROUTER_MODEL || ""
      : "",
    SARVAM_API_KEY: sarvamLiveMode ? process.env.SARVAM_API_KEY || "" : "",
    OPENAI_API_KEY: "",
    ...(openRouterLiveMode
      ? {
          VEDA_OPENROUTER_LIVE_E2E: "1",
          VEDA_OPENROUTER_OUTPUT_PATH:
            process.env.VEDA_OPENROUTER_OUTPUT_PATH || "",
          VEDA_OPENROUTER_PREFLIGHT_PATH:
            process.env.VEDA_OPENROUTER_PREFLIGHT_PATH || "",
          VEDA_OPENROUTER_REQUEST_COUNTER_PATH:
            process.env.VEDA_OPENROUTER_REQUEST_COUNTER_PATH || "",
          VEDA_OPENROUTER_DATABASE_PATH:
            process.env.VEDA_OPENROUTER_DATABASE_PATH || "",
          VEDA_OPENROUTER_T112_E2E: openRouterT112Mode ? "1" : "",
          VEDA_OPENROUTER_RUN_ID: process.env.VEDA_OPENROUTER_RUN_ID || "",
          VEDA_OPENROUTER_EXPECTED_MODEL:
            process.env.VEDA_OPENROUTER_EXPECTED_MODEL || "",
          OPENROUTER_REASONING_ENABLED:
            process.env.OPENROUTER_REASONING_ENABLED || "",
          VEDA_OPENROUTER_SINGLE_QUESTION_E2E: openRouterSingleQuestionMode
            ? "1"
            : "",
        }
      : sarvamLiveMode
        ? {
            VEDA_SARVAM_LIVE_E2E: "1",
            VEDA_SARVAM_BILLING_VERIFIED:
              process.env.VEDA_SARVAM_BILLING_VERIFIED || "",
            VEDA_SARVAM_OUTPUT_PATH: process.env.VEDA_SARVAM_OUTPUT_PATH || "",
            VEDA_SARVAM_PREFLIGHT_PATH:
              process.env.VEDA_SARVAM_PREFLIGHT_PATH || "",
            VEDA_SARVAM_SERVER_STATE_PATH:
              process.env.VEDA_SARVAM_SERVER_STATE_PATH || "",
            VEDA_SARVAM_RUN_STATE_PATH:
              process.env.VEDA_SARVAM_RUN_STATE_PATH || "",
            VEDA_SARVAM_REQUEST_COUNTER_PATH:
              process.env.VEDA_SARVAM_REQUEST_COUNTER_PATH || "",
            VEDA_SARVAM_DATABASE_PATH:
              process.env.VEDA_SARVAM_DATABASE_PATH || "",
            VEDA_SARVAM_EXPECTED_MODEL:
              process.env.VEDA_SARVAM_EXPECTED_MODEL || "glm5.3-flash",
            VEDA_SARVAM_RUN_ID: process.env.VEDA_SARVAM_RUN_ID || "glm53flash",
            VEDA_REAL_E2E_API_PORT: apiPort,
            LLM_PROVIDER: "sarvam",
            SARVAM_MODEL: "glm5.3-flash",
            ALLOW_PAID_LLM_CALLS: "true",
            SARVAM_MAX_JOB_COST_INR:
              process.env.VEDA_SARVAM_JOB_BUDGET_INR || "20",
            SARVAM_INPUT_PRICE_PER_MILLION_INR: "13.5",
            SARVAM_OUTPUT_PRICE_PER_MILLION_INR: "45",
            OPENAI_API_KEY: "",
            OPENROUTER_API_KEY: "",
            MAX_DAILY_MODEL_CALLS: process.env.VEDA_SARVAM_REQUEST_CAP || "24",
            MAX_DAILY_MODEL_CALLS_PER_USER:
              process.env.VEDA_SARVAM_REQUEST_CAP || "24",
            VEDA_SARVAM_JOB_BUDGET_INR:
              process.env.VEDA_SARVAM_JOB_BUDGET_INR || "20",
            VEDA_SARVAM_REQUEST_CAP:
              process.env.VEDA_SARVAM_REQUEST_CAP || "24",
          }
        : {}),
  },
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: true,
  // Each browser journey starts or exercises a local API and can be resource-heavy.
  // Running four default workers caused API/UI timeouts on the supported Windows dev setup.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5176",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: realApiMode ? [backendServer, frontendServer] : frontendServer,
});
