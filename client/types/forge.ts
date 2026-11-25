import { z } from "zod";

export const ToolNameSchema = z.enum([
  "csv_lookup",
  "calculator",
  "weather_http",
  "current_date",
]);
export type ToolName = z.infer<typeof ToolNameSchema>;

export const EvalCaseTypeSchema = z.enum(["answerable", "refusal", "edge"]);
export type EvalCaseType = z.infer<typeof EvalCaseTypeSchema>;

export const FailureCategorySchema = z.enum([
  "none",
  "retrieval_miss",
  "prompt_defect",
  "hallucination",
  "wrong_refusal",
]);
export type FailureCategory = z.infer<typeof FailureCategorySchema>;

export const ProjectSummarySchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  brief: z.string(),
  status: z.string(),
  created_at: z.string().optional(),
});
export type ProjectSummary = z.infer<typeof ProjectSummarySchema>;

export const TopicGroundabilitySchema = z.object({
  topic: z.string(),
  is_grounded: z.boolean(),
  confidence: z.number(),
  supporting_documents: z.array(z.string()),
  gap_reason: z.string().nullable().optional(),
});

export const GroundabilityReportSchema = z.object({
  is_passable: z.boolean(),
  critical_gaps: z.array(TopicGroundabilitySchema),
  warnings: z.array(TopicGroundabilitySchema),
  summary: z.string(),
});
export type GroundabilityReport = z.infer<typeof GroundabilityReportSchema>;

export const AgentDefinitionSchema = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  slug: z.string(),
  version: z.number().int(),
  system_prompt: z.string(),
  selected_tools: z.array(ToolNameSchema),
  retrieval_config: z.object({
    chunk_size: z.number(),
    chunk_overlap: z.number(),
    top_k: z.number(),
    similarity_threshold: z.number(),
    hybrid_search: z.boolean(),
  }),
  output_contract: z.object({
    format: z.enum(["markdown", "json"]),
    require_citations: z.boolean(),
    refusal_template: z.string(),
    max_response_words: z.number(),
  }),
});
export type AgentDefinition = z.infer<typeof AgentDefinitionSchema>;

export const EvalCaseSchema = z.object({
  id: z.string().uuid(),
  case_type: EvalCaseTypeSchema,
  question: z.string(),
  expected_sources: z.array(z.string()),
  expected_facts: z.array(z.string()),
  should_refuse: z.boolean(),
  rationale: z.string(),
});
export type EvalCase = z.infer<typeof EvalCaseSchema>;

export const JudgeScoreSchema = z.object({
  eval_case_id: z.string().uuid(),
  grounded: z.boolean(),
  correct: z.boolean(),
  refusal_accurate: z.boolean(),
  passed: z.boolean(),
  failure_category: FailureCategorySchema,
  reasoning: z.string(),
  deterministic_checks: z.record(z.string(), z.boolean()),
});
export type JudgeScore = z.infer<typeof JudgeScoreSchema>;

export const IterationLogSchema = z.object({
  iteration: z.number().int(),
  score_before: z.number(),
  score_after: z.number(),
  failures_addressed: z.array(z.string().uuid()),
  change_type: z.string(),
  what_changed: z.string(),
  why: z.string(),
});
export type IterationLog = z.infer<typeof IterationLogSchema>;

export const HonestReportSchema = z.object({
  project_id: z.string().uuid(),
  final_agent_version: z.number().int(),
  per_iteration_scores: z.array(z.record(z.string(), z.union([z.number(), z.string()]))),
  final_pass_rate: z.number(),
  remaining_failures: z.array(z.record(z.string(), z.string())),
  known_limitations: z.array(z.string()),
  recommendation: z.string(),
});
export type HonestReport = z.infer<typeof HonestReportSchema>;

export const ChatResponseSchema = z.object({
  answer: z.string(),
  citations: z.array(z.string()),
  tools_used: z.array(z.string()),
  latency_ms: z.number(),
});
export type ChatResponse = z.infer<typeof ChatResponseSchema>;

