"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  PanelRightClose,
  PanelRightOpen,
  ShieldAlert,
  X,
  XCircle,
} from "lucide-react";
import { z } from "zod";
import { getForgeStreamUrl } from "@/lib/api";
import {
  FailureCategorySchema,
  type EvalCase,
  type EvalCaseType,
  type FailureCategory,
  type HonestReport,
  type IterationLog,
  type JudgeScore,
} from "@/types/forge";

const StageSchema = z.enum([
  "agent_generation",
  "eval_generation",
  "optimization",
  "reporting",
]);
type PipelineStage = z.infer<typeof StageSchema>;

const StageStartedEventSchema = z.object({
  event: z.literal("stage_started"),
  stage: StageSchema,
});

const EvalScoredEventSchema = z.object({
  event: z.literal("eval_scored"),
  iteration: z.number().int(),
  eval_case_id: z.string(),
  passed: z.boolean(),
  failure_category: FailureCategorySchema,
  grounded: z.boolean().optional(),
  refusal_accurate: z.boolean().optional(),
  latency_ms: z.number().optional(),
});

const IterationCompleteEventSchema = z.object({
  event: z.literal("iteration_complete"),
  iteration: z.number().int(),
  score_before: z.number(),
  score_after: z.number(),
  change_type: z.string(),
  what_changed: z.string().optional(),
  why: z.string().optional(),
});

const ForgeFinishedEventSchema = z.object({
  event: z.literal("forge_finished"),
  final_pass_rate: z.number(),
  final_agent_version: z.number().int(),
  stop_reason: z.string(),
});

type EvalFilter = "all" | "failed" | "refusal" | "edge";

interface LiveEvalRow {
  eval_case_id: string;
  case_type: EvalCaseType;
  question: string;
  should_refuse: boolean;
  passed: boolean | null;
  failure_category: FailureCategory;
  grounded: boolean | null;
  refusal_accurate: boolean | null;
  latency_ms: number | null;
  reasoning: string | null;
}

export interface EvalObservabilityDrawerProps {
  projectId: string;
  isOpen?: boolean;
  onToggle?: () => void;
  defaultOpen?: boolean;
  streamActive?: boolean;
  initialEvalCases?: EvalCase[];
  initialScores?: JudgeScore[];
  initialIterations?: IterationLog[];
  initialReport?: HonestReport | null;
}

const STAGE_STEPS: { id: PipelineStage; label: string }[] = [
  { id: "agent_generation", label: "Generator" },
  { id: "eval_generation", label: "Eval Gen (20+)" },
  { id: "optimization", label: "Iter 1..3" },
  { id: "reporting", label: "Report" },
];

const FAILURE_BADGE_STYLES: Record<
  FailureCategory,
  { label: string; className: string }
> = {
  none: {
    label: "passed",
    className: "bg-[#bcd1ca]/50 text-[#141413] border-[#788c5d]/40",
  },
  retrieval_miss: {
    label: "retrieval_miss",
    className: "bg-[#ebdbbc] text-[#141413] border-[#d4a27f]",
  },
  prompt_defect: {
    label: "prompt_defect",
    className: "bg-[#cbcadb]/60 text-[#141413] border-[#6a9bcc]/50",
  },
  hallucination: {
    label: "hallucination",
    className: "bg-[#ebcece] text-[#141413] border-[#c46686]",
  },
  wrong_refusal: {
    label: "wrong_refusal",
    className: "bg-[#d97757]/25 text-[#141413] border-[#c6613f]",
  },
};

function formatPct(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function EvalObservabilityDrawer({
  projectId,
  isOpen: controlledIsOpen,
  onToggle: controlledOnToggle,
  defaultOpen = true,
  streamActive,
  initialEvalCases = [],
  initialScores = [],
  initialIterations = [],
  initialReport = null,
}: EvalObservabilityDrawerProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const isOpen = controlledIsOpen ?? uncontrolledOpen;
  const onToggle =
    controlledOnToggle ?? (() => setUncontrolledOpen((prev) => !prev));
  const [currentStage, setCurrentStage] = useState<PipelineStage | null>(
    initialReport ? "reporting" : null,
  );
  const [isFinished, setIsFinished] = useState<boolean>(Boolean(initialReport));
  const [stopReason, setStopReason] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<
    "idle" | "connecting" | "live" | "closed" | "error"
  >("idle");
  const [filter, setFilter] = useState<EvalFilter>("all");
  const [iterations, setIterations] =
    useState<IterationLog[]>(initialIterations);
  const [liveScoresById, setLiveScoresById] = useState<
    Record<
      string,
      {
        passed: boolean;
        failure_category: FailureCategory;
        grounded: boolean | null;
        refusal_accurate: boolean | null;
        latency_ms: number | null;
        reasoning: string | null;
      }
    >
  >(() => {
    const map: Record<
      string,
      {
        passed: boolean;
        failure_category: FailureCategory;
        grounded: boolean | null;
        refusal_accurate: boolean | null;
        latency_ms: number | null;
        reasoning: string | null;
      }
    > = {};
    for (const s of initialScores) {
      map[s.eval_case_id] = {
        passed: s.passed,
        failure_category: s.failure_category,
        grounded: s.grounded,
        refusal_accurate: s.refusal_accurate,
        latency_ms: null,
        reasoning: s.reasoning,
      };
    }
    return map;
  });

  const shouldStream = streamActive ?? (isOpen && !initialReport && !isFinished);

  useEffect(() => {
    if (!shouldStream || !projectId) {
      return;
    }

    const url = getForgeStreamUrl(projectId);
    const es = new EventSource(url);

    const handleOpen = () => {
      setConnectionState("live");
    };

    const handlePayload = (raw: string) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return;
      }

      const stageEvt = StageStartedEventSchema.safeParse(parsed);
      if (stageEvt.success) {
        setCurrentStage(stageEvt.data.stage);
        return;
      }

      const evalEvt = EvalScoredEventSchema.safeParse(parsed);
      if (evalEvt.success) {
        const d = evalEvt.data;
        setLiveScoresById((prev) => ({
          ...prev,
          [d.eval_case_id]: {
            passed: d.passed,
            failure_category: d.failure_category,
            grounded: d.grounded ?? (d.failure_category !== "hallucination"),
            refusal_accurate:
              d.refusal_accurate ?? (d.failure_category !== "wrong_refusal"),
            latency_ms: d.latency_ms ?? null,
            reasoning: prev[d.eval_case_id]?.reasoning ?? null,
          },
        }));
        return;
      }

      const iterEvt = IterationCompleteEventSchema.safeParse(parsed);
      if (iterEvt.success) {
        const d = iterEvt.data;
        setIterations((prev) => {
          const exists = prev.some((item) => item.iteration === d.iteration);
          const nextEntry: IterationLog = {
            iteration: d.iteration,
            score_before: d.score_before,
            score_after: d.score_after,
            failures_addressed: [],
            change_type: d.change_type,
            what_changed:
              d.what_changed ?? `Applied ${d.change_type} optimization`,
            why:
              d.why ??
              `Targeted failing eval cases in iteration ${d.iteration}`,
          };
          if (exists) {
            return prev.map((item) =>
              item.iteration === d.iteration ? nextEntry : item,
            );
          }
          return [...prev, nextEntry];
        });
        return;
      }

      const finishEvt = ForgeFinishedEventSchema.safeParse(parsed);
      if (finishEvt.success) {
        setCurrentStage("reporting");
        setIsFinished(true);
        setStopReason(finishEvt.data.stop_reason);
        setConnectionState("closed");
        es.close();
      }
    };

    const onStageStarted = (e: MessageEvent<string>) => handlePayload(e.data);
    const onEvalScored = (e: MessageEvent<string>) => handlePayload(e.data);
    const onIterationComplete = (e: MessageEvent<string>) =>
      handlePayload(e.data);
    const onForgeFinished = (e: MessageEvent<string>) => handlePayload(e.data);

    es.addEventListener("open", handleOpen);
    es.addEventListener("stage_started", onStageStarted);
    es.addEventListener("eval_scored", onEvalScored);
    es.addEventListener("iteration_complete", onIterationComplete);
    es.addEventListener("forge_finished", onForgeFinished);
    es.onmessage = (e: MessageEvent<string>) => handlePayload(e.data);
    es.onerror = () => {
      setConnectionState("error");
      es.close();
    };

    return () => {
      es.removeEventListener("open", handleOpen);
      es.removeEventListener("stage_started", onStageStarted);
      es.removeEventListener("eval_scored", onEvalScored);
      es.removeEventListener("iteration_complete", onIterationComplete);
      es.removeEventListener("forge_finished", onForgeFinished);
      es.close();
    };
  }, [projectId, shouldStream]);

  const evalRows: LiveEvalRow[] = useMemo(() => {
    const byId = new Map<string, LiveEvalRow>();

    for (const c of initialEvalCases) {
      const score = liveScoresById[c.id];
      byId.set(c.id, {
        eval_case_id: c.id,
        case_type: c.case_type,
        question: c.question,
        should_refuse: c.should_refuse,
        passed: score ? score.passed : null,
        failure_category: score ? score.failure_category : "none",
        grounded: score ? score.grounded : null,
        refusal_accurate: score ? score.refusal_accurate : null,
        latency_ms: score ? score.latency_ms : null,
        reasoning: score ? score.reasoning : null,
      });
    }

    for (const [id, score] of Object.entries(liveScoresById)) {
      if (!byId.has(id)) {
        byId.set(id, {
          eval_case_id: id,
          case_type:
            score.failure_category === "wrong_refusal" ? "refusal" : "answerable",
          question: `Eval case ${id.slice(0, 8)}`,
          should_refuse: score.failure_category === "wrong_refusal",
          passed: score.passed,
          failure_category: score.failure_category,
          grounded: score.grounded,
          refusal_accurate: score.refusal_accurate,
          latency_ms: score.latency_ms,
          reasoning: score.reasoning,
        });
      }
    }

    return Array.from(byId.values());
  }, [initialEvalCases, liveScoresById]);

  const scorecard = useMemo(() => {
    const scored = evalRows.filter((r) => r.passed !== null);
    if (scored.length === 0) {
      return {
        passRate: initialReport ? initialReport.final_pass_rate : null,
        groundedRate: null,
        refusalRate: null,
        totalScored: 0,
      };
    }

    const passedCount = scored.filter((r) => r.passed).length;
    const groundedEntries = scored.filter((r) => r.grounded !== null);
    const groundedCount = groundedEntries.filter((r) => r.grounded).length;
    const refusalEntries = scored.filter((r) => r.refusal_accurate !== null);
    const refusalCount = refusalEntries.filter((r) => r.refusal_accurate).length;

    return {
      passRate: passedCount / scored.length,
      groundedRate:
        groundedEntries.length > 0
          ? groundedCount / groundedEntries.length
          : null,
      refusalRate:
        refusalEntries.length > 0
          ? refusalCount / refusalEntries.length
          : null,
      totalScored: scored.length,
    };
  }, [evalRows, initialReport]);

  const filteredRows = useMemo(() => {
    switch (filter) {
      case "failed":
        return evalRows.filter((r) => r.passed === false);
      case "refusal":
        return evalRows.filter(
          (r) => r.case_type === "refusal" || r.should_refuse,
        );
      case "edge":
        return evalRows.filter((r) => r.case_type === "edge");
      default:
        return evalRows;
    }
  }, [evalRows, filter]);

  const activeStepIndex = useMemo(() => {
    if (isFinished) return 3;
    if (!currentStage) return -1;
    return STAGE_STEPS.findIndex((s) => s.id === currentStage);
  }, [currentStage, isFinished]);

  const effectiveConnectionState =
    shouldStream && connectionState === "idle" ? "connecting" : connectionState;

  if (!isOpen) {
    return (
      <div className="fixed bottom-4 right-4 z-40 lg:static lg:flex lg:items-start lg:p-3">
        <button
          type="button"
          onClick={onToggle}
          aria-label="Open eval observability panel"
          className="inline-flex items-center gap-2 rounded-[8px] border border-[#d1cfc5] bg-[#f0eee6] px-3 py-2 text-xs font-medium text-[#141413] transition-colors hover:bg-[#e8e6dc]"
        >
          <PanelRightOpen className="h-4 w-4" />
          <span className="font-mono uppercase tracking-wider">
            Observability
          </span>
          {scorecard.passRate !== null && (
            <span className="rounded bg-[#141413] px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-[#faf9f5]">
              {formatPct(scorecard.passRate)}
            </span>
          )}
        </button>
      </div>
    );
  }

  return (
    <>
      {/* Mobile backdrop */}
      <div
        className="fixed inset-0 z-40 bg-[#141413]/30 lg:hidden"
        onClick={onToggle}
        aria-hidden="true"
      />

      <aside
        aria-label="Eval Observability Drawer"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[420px] flex-col border-l border-[#d1cfc5] bg-[#f0eee6] text-[#141413] lg:static lg:z-auto lg:w-[420px] lg:shrink-0"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#d1cfc5] px-4 py-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-[#141413]" />
            <span className="font-mono text-xs uppercase tracking-wider text-[#141413]">
              Eval Observability
            </span>
            <span
              className={`inline-flex items-center gap-1 rounded-[8px] border px-2 py-0.5 font-mono text-[10px] uppercase ${
                effectiveConnectionState === "live"
                  ? "border-[#788c5d] bg-[#bcd1ca]/50 text-[#141413]"
                  : effectiveConnectionState === "error"
                    ? "border-[#c6613f] bg-[#ebcece] text-[#141413]"
                    : "border-[#d1cfc5] bg-[#faf9f5] text-[#5e5d59]"
              }`}
            >
              {effectiveConnectionState === "live"
                ? "live"
                : isFinished
                  ? "complete"
                  : effectiveConnectionState}
            </span>
          </div>
          <button
            type="button"
            onClick={onToggle}
            aria-label="Close eval observability panel"
            className="rounded-[8px] p-1.5 text-[#5e5d59] transition-colors hover:bg-[#e8e6dc] hover:text-[#141413]"
          >
            <PanelRightClose className="hidden h-4 w-4 lg:block" />
            <X className="h-4 w-4 lg:hidden" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          {/* Stage Stepper */}
          <section aria-label="Pipeline Stage Stepper">
            <h3 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
              Pipeline Stage
            </h3>
            <div className="grid grid-cols-4 gap-1.5">
              {STAGE_STEPS.map((step, idx) => {
                const isDone = isFinished || idx < activeStepIndex;
                const isActive = !isFinished && idx === activeStepIndex;
                const label =
                  step.id === "optimization" && iterations.length > 0
                    ? `Iter ${Math.min(iterations.length, 3)}/3`
                    : step.label;
                return (
                  <div
                    key={step.id}
                    className={`rounded-[8px] border px-2 py-1.5 text-center transition-colors ${
                      isActive
                        ? "border-[#141413] bg-[#141413] text-[#faf9f5]"
                        : isDone
                          ? "border-[#788c5d]/60 bg-[#bcd1ca]/40 text-[#141413]"
                          : "border-[#d1cfc5] bg-[#faf9f5] text-[#87867f]"
                    }`}
                  >
                    <div className="font-mono text-[10px] tabular-nums">
                      0{idx + 1}
                    </div>
                    <div className="truncate text-[11px] font-medium">
                      {label}
                    </div>
                  </div>
                );
              })}
            </div>
            {stopReason && (
              <p className="mt-2 font-mono text-[11px] text-[#5e5d59]">
                Stop reason: <span className="text-[#141413]">{stopReason}</span>
              </p>
            )}
          </section>

          {/* Live Scorecard */}
          <section aria-label="Live Scorecard">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
                Live Scorecard
              </h3>
              <span className="font-mono text-[11px] tabular-nums text-[#5e5d59]">
                {scorecard.totalScored} scored
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-2.5">
                <div className="text-[11px] text-[#5e5d59]">Pass Rate</div>
                <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-[#141413]">
                  {formatPct(scorecard.passRate)}
                </div>
              </div>
              <div className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-2.5">
                <div className="text-[11px] text-[#5e5d59]">Grounded</div>
                <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-[#141413]">
                  {formatPct(scorecard.groundedRate)}
                </div>
              </div>
              <div className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-2.5">
                <div className="text-[11px] text-[#5e5d59]">Refusal Acc</div>
                <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-[#141413]">
                  {formatPct(scorecard.refusalRate)}
                </div>
              </div>
            </div>
          </section>

          {/* Per-Iteration Diff Log */}
          <section aria-label="Per-Iteration Diff Log">
            <h3 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
              Iteration Diff Log
            </h3>
            {iterations.length === 0 ? (
              <div className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3 text-xs text-[#87867f]">
                No optimization iterations recorded yet.
              </div>
            ) : (
              <div className="space-y-2">
                {iterations.map((iter) => {
                  const delta = iter.score_after - iter.score_before;
                  return (
                    <div
                      key={iter.iteration}
                      className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-semibold tabular-nums text-[#141413]">
                            Iter {iter.iteration}
                          </span>
                          <span className="rounded bg-[#e3dacc] px-1.5 py-0.5 font-mono text-[10px] text-[#141413]">
                            {iter.change_type}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 font-mono text-xs tabular-nums">
                          <span className="text-[#5e5d59]">
                            {formatPct(iter.score_before)}
                          </span>
                          <ChevronRight className="h-3 w-3 text-[#87867f]" />
                          <span className="font-semibold text-[#141413]">
                            {formatPct(iter.score_after)}
                          </span>
                          <span
                            className={`ml-1 text-[10px] ${
                              delta >= 0 ? "text-[#788c5d]" : "text-[#c6613f]"
                            }`}
                          >
                            ({delta >= 0 ? "+" : ""}
                            {(delta * 100).toFixed(1)}%)
                          </span>
                        </div>
                      </div>
                      <p className="mt-2 text-xs font-medium text-[#141413]">
                        {iter.what_changed}
                      </p>
                      <p className="mt-1 text-[11px] leading-relaxed text-[#5e5d59]">
                        {iter.why}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Filterable Eval Case List */}
          <section aria-label="Eval Cases">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
                Eval Cases ({filteredRows.length})
              </h3>
              <div
                role="tablist"
                aria-label="Filter eval cases"
                className="flex rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-0.5"
              >
                {(
                  [
                    { id: "all", label: "All" },
                    { id: "failed", label: "Failed" },
                    { id: "refusal", label: "Refusal" },
                    { id: "edge", label: "Edge" },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={filter === tab.id}
                    onClick={() => setFilter(tab.id)}
                    className={`rounded-[6px] px-2 py-0.5 text-[11px] font-medium transition-colors ${
                      filter === tab.id
                        ? "bg-[#141413] text-[#faf9f5]"
                        : "text-[#5e5d59] hover:text-[#141413]"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {filteredRows.length === 0 ? (
              <div className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3 text-xs text-[#87867f]">
                No eval cases match this filter.
              </div>
            ) : (
              <div className="space-y-2">
                {filteredRows.map((row) => {
                  const badge = FAILURE_BADGE_STYLES[row.failure_category];
                  return (
                    <div
                      key={row.eval_case_id}
                      className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2">
                          {row.passed === true ? (
                            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#788c5d]" />
                          ) : row.passed === false ? (
                            <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#c6613f]" />
                          ) : (
                            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#87867f]" />
                          )}
                          <p className="text-xs leading-snug text-[#141413]">
                            {row.question}
                          </p>
                        </div>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-1.5">
                        <div className="flex items-center gap-1.5">
                          <span className="rounded border border-[#d1cfc5] bg-[#f0eee6] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[#5e5d59]">
                            {row.case_type}
                          </span>
                          {row.should_refuse && (
                            <span className="inline-flex items-center gap-1 rounded border border-[#d1cfc5] bg-[#ebdbbc]/70 px-1.5 py-0.5 font-mono text-[10px] text-[#141413]">
                              <ShieldAlert className="h-2.5 w-2.5" />
                              refusal
                            </span>
                          )}
                          {row.passed !== null && (
                            <span
                              className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${badge.className}`}
                            >
                              {badge.label}
                            </span>
                          )}
                        </div>
                        {row.latency_ms !== null && (
                          <span className="font-mono text-[10px] tabular-nums text-[#87867f]">
                            {Math.round(row.latency_ms)}ms
                          </span>
                        )}
                      </div>
                      {row.reasoning && row.passed === false && (
                        <p className="mt-1.5 border-t border-[#d1cfc5] pt-1.5 text-[11px] text-[#5e5d59]">
                          {row.reasoning}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </aside>
    </>
  );
}
