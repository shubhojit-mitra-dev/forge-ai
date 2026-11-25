"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Code2,
  Copy,
  Download,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Send,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { z } from "zod";
import {
  createProject,
  getProjectDetail,
  runForgePipeline,
  startIntake,
  submitIntake,
  uploadDocument,
} from "@/lib/api";
import {
  AgentDefinitionSchema,
  GroundabilityReportSchema,
  HonestReportSchema,
  type AgentDefinition,
  type GroundabilityReport,
  type HonestReport,
} from "@/types/forge";

const ACCEPTED_EXTENSIONS = [".pdf", ".csv", ".md", ".txt"] as const;

interface UploadedDocItem {
  localId: string;
  file?: File;
  filename: string;
  chunkCount: number | null;
  status: "queued" | "uploading" | "indexed" | "error";
  error?: string;
}

interface DeliverableArtifacts {
  agent: AgentDefinition;
  honestReport: HonestReport | null;
  requirements: Record<string, unknown> | null;
}

export interface BuilderWorkspaceProps {
  projectId?: string;
  token?: string;
  onOpenEvalDrawer?: () => void;
}

const ProjectDetailPayloadSchema = z
  .object({
    id: z.string().optional(),
    title: z.string().optional(),
    brief: z.string().optional(),
    status: z.string().optional(),
    groundability_report: GroundabilityReportSchema.nullable().optional(),
    requirements_doc: z.record(z.string(), z.unknown()).nullable().optional(),
    agent_definition: AgentDefinitionSchema.nullable().optional(),
    honest_report: HonestReportSchema.nullable().optional(),
    documents: z
      .array(
        z.object({
          id: z.string(),
          filename: z.string(),
          chunk_count: z.number().optional(),
        }),
      )
      .optional(),
  })
  .passthrough();

function isSupportedFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function deriveTitleFromBrief(brief: string): string {
  const cleaned = brief.trim().replace(/\s+/g, " ");
  if (!cleaned) return "Untitled ForgeAI Agent";
  return cleaned.length > 56 ? `${cleaned.slice(0, 53)}...` : cleaned;
}

export function BuilderWorkspace({
  projectId: initialProjectId,
  token = "",
  onOpenEvalDrawer,
}: BuilderWorkspaceProps) {
  const router = useRouter();
  const fileInputId = useId();
  const dropzoneRef = useRef<HTMLDivElement | null>(null);

  const [projectId, setProjectId] = useState<string | undefined>(
    initialProjectId,
  );
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [projectStatus, setProjectStatus] = useState<string>("draft");

  const [docs, setDocs] = useState<UploadedDocItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [requirements, setRequirements] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [groundability, setGroundability] =
    useState<GroundabilityReport | null>(null);
  const [deliverable, setDeliverable] = useState<DeliverableArtifacts | null>(
    null,
  );

  const [isStartingIntake, setIsStartingIntake] = useState(false);
  const [isSubmittingIntake, setIsSubmittingIntake] = useState(false);
  const [isBuildingAgent, setIsBuildingAgent] = useState(false);
  const [isLoadingProject, setIsLoadingProject] = useState(
    Boolean(initialProjectId),
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [copiedUrl, setCopiedUrl] = useState(false);
  const [showArtifactsJson, setShowArtifactsJson] = useState(false);

  const loadProjectState = useCallback(
    async (id: string) => {
      try {
        const raw = await getProjectDetail(token, id);
        const parsed = ProjectDetailPayloadSchema.safeParse(raw);
        if (!parsed.success) return;

        const data = parsed.data;
        if (data.title) setTitle(data.title);
        if (data.brief) setBrief(data.brief);
        if (data.status) setProjectStatus(data.status);
        if (data.groundability_report) {
          setGroundability(data.groundability_report);
        }
        if (data.requirements_doc) {
          setRequirements(data.requirements_doc);
        }
        if (data.documents && data.documents.length > 0) {
          setDocs(
            data.documents.map((doc) => ({
              localId: doc.id,
              filename: doc.filename,
              chunkCount: doc.chunk_count ?? null,
              status: "indexed",
            })),
          );
        }
        if (data.agent_definition) {
          setDeliverable({
            agent: data.agent_definition,
            honestReport: data.honest_report ?? null,
            requirements: data.requirements_doc ?? null,
          });
        }
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to load project details.",
        );
      } finally {
        setIsLoadingProject(false);
      }
    },
    [token],
  );

  useEffect(() => {
    if (!initialProjectId) {
      setIsLoadingProject(false);
      return;
    }
    setProjectId(initialProjectId);
    void loadProjectState(initialProjectId);
  }, [initialProjectId, loadProjectState]);

  const uploadSingleFile = useCallback(
    async (activeId: string, item: UploadedDocItem) => {
      if (!item.file) return;
      setDocs((prev) =>
        prev.map((d) =>
          d.localId === item.localId ? { ...d, status: "uploading" } : d,
        ),
      );
      try {
        const res = await uploadDocument(token, activeId, item.file);
        setDocs((prev) =>
          prev.map((d) =>
            d.localId === item.localId
              ? {
                  ...d,
                  status: "indexed",
                  chunkCount: res.chunk_count,
                }
              : d,
          ),
        );
      } catch (err) {
        setDocs((prev) =>
          prev.map((d) =>
            d.localId === item.localId
              ? {
                  ...d,
                  status: "error",
                  error:
                    err instanceof Error ? err.message : "Upload failed.",
                }
              : d,
          ),
        );
      }
    },
    [token],
  );

  const handleFilesAdded = useCallback(
    (fileList: FileList | File[]) => {
      setErrorMessage(null);
      const incoming = Array.from(fileList);
      const unsupported = incoming.filter((f) => !isSupportedFile(f.name));
      if (unsupported.length > 0) {
        setErrorMessage(
          `Unsupported file type: ${unsupported.map((f) => f.name).join(", ")}. Allowed: PDF, CSV, MD, TXT.`,
        );
      }

      const validFiles = incoming.filter((f) => isSupportedFile(f.name));
      if (validFiles.length === 0) return;

      const newItems: UploadedDocItem[] = validFiles.map((file) => ({
        localId: `${file.name}-${file.size}-${crypto.randomUUID()}`,
        file,
        filename: file.name,
        chunkCount: null,
        status: projectId ? "uploading" : "queued",
      }));

      setDocs((prev) => [...prev, ...newItems]);

      if (projectId) {
        for (const item of newItems) {
          void uploadSingleFile(projectId, item);
        }
      }
    },
    [projectId, uploadSingleFile],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFilesAdded(e.dataTransfer.files);
      }
    },
    [handleFilesAdded],
  );

  const removeDoc = (localId: string) => {
    setDocs((prev) => prev.filter((d) => d.localId !== localId));
  };

  const ensureProjectAndUploads = async (): Promise<string> => {
    let activeId = projectId;
    if (!activeId) {
      const resolvedTitle = title.trim() || deriveTitleFromBrief(brief);
      const created = await createProject(token, resolvedTitle, brief.trim());
      activeId = created.id;
      setProjectId(activeId);
      setTitle(created.title);
      setProjectStatus(created.status);
    }

    const queued = docs.filter((d) => d.status === "queued" && d.file);
    for (const item of queued) {
      await uploadSingleFile(activeId, item);
    }
    return activeId;
  };

  const handleStartIntake = async () => {
    if (!brief.trim()) {
      setErrorMessage("Please describe the agent you want to build first.");
      return;
    }
    setErrorMessage(null);
    setIsStartingIntake(true);
    try {
      const activeId = await ensureProjectAndUploads();
      const res = await startIntake(token, activeId);
      const capped = res.questions.slice(0, 5);
      setQuestions(capped);
      setAnswers(
        capped.reduce<Record<number, string>>((acc, _, idx) => {
          acc[idx] = answers[idx] ?? "";
          return acc;
        }, {}),
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to start intake interview.",
      );
    } finally {
      setIsStartingIntake(false);
    }
  };

  const handleSubmitIntake = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) return;

    setErrorMessage(null);
    setIsSubmittingIntake(true);
    try {
      const qaPairs = questions.map((question, idx) => ({
        question,
        answer: (answers[idx] ?? "").trim() || "No additional constraints.",
      }));
      const res = await submitIntake(token, projectId, qaPairs);
      setRequirements(res.requirements);
      setGroundability(res.groundability);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to submit intake answers.",
      );
    } finally {
      setIsSubmittingIntake(false);
    }
  };

  const handleBuildAgent = async () => {
    if (!brief.trim() && !projectId) {
      setErrorMessage("Provide an agent brief before running the pipeline.");
      return;
    }
    setErrorMessage(null);
    setIsBuildingAgent(true);
    try {
      const activeId = await ensureProjectAndUploads();
      onOpenEvalDrawer?.();
      window.dispatchEvent(
        new CustomEvent("forge:open-eval-drawer", {
          detail: { projectId: activeId },
        }),
      );

      if (!initialProjectId) {
        router.push(`/projects/${activeId}`);
      }

      const result = await runForgePipeline(token, activeId);
      const parsedAgent = AgentDefinitionSchema.safeParse(
        result.agent_definition ?? result,
      );
      const parsedReport = HonestReportSchema.safeParse(result.honest_report);

      if (parsedAgent.success) {
        setDeliverable({
          agent: parsedAgent.data,
          honestReport: parsedReport.success ? parsedReport.data : null,
          requirements,
        });
      } else {
        await loadProjectState(activeId);
      }
      setProjectStatus("completed");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Forge pipeline execution failed.",
      );
    } finally {
      setIsBuildingAgent(false);
    }
  };

  const handleCopyUrl = async (slug: string) => {
    const url = `${window.location.origin}/agent/${slug}`;
    await navigator.clipboard.writeText(url);
    setCopiedUrl(true);
    window.setTimeout(() => setCopiedUrl(false), 2000);
  };

  const handleDownloadJson = () => {
    if (!deliverable) return;
    const blob = new Blob([JSON.stringify(deliverable, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${deliverable.agent.slug}-artifacts.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const isGroundabilityBlocked = Boolean(
    groundability && !groundability.is_passable,
  );
  const totalChunks = docs.reduce(
    (sum, item) => sum + (item.chunkCount ?? 0),
    0,
  );

  if (isLoadingProject) {
    return (
      <div className="flex min-h-[420px] items-center justify-center bg-canvas px-6 py-16">
        <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-wider text-text-muted">
          <Loader2 className="h-4 w-4 animate-spin text-ink" />
          Loading ForgeAI workspace...
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 bg-canvas px-6 py-10 text-ink sm:px-10">
      {/* Editorial Header */}
      <header className="flex flex-col gap-3 border-b border-hairline pb-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-xs uppercase tracking-[0.12em] text-text-muted">
            ForgeAI // Agent Factory
          </span>
          {projectId ? (
            <span className="rounded-[8px] border border-hairline bg-surface-secondary px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-ink-soft">
              Status: {projectStatus}
            </span>
          ) : null}
        </div>
        <h1 className="font-serif text-3xl font-normal tracking-[-0.02em] text-ink sm:text-4xl">
          Build an evaluated, grounded agent from your documents.
        </h1>
        <p className="max-w-2xl font-serif text-lg leading-relaxed text-text-muted">
          Describe the assistant you need, attach your knowledge base, answer
          clarifying questions, and let ForgeAI synthesize, test, and refine the
          agent contract.
        </p>
      </header>

      {errorMessage ? (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-[16px] border border-accent-clay/50 bg-accent-coral/35 px-4 py-3 text-sm text-ink"
        >
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-deep" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="rounded-[8px] p-1 text-text-muted transition-colors hover:bg-surface-secondary hover:text-ink"
            aria-label="Dismiss error"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      {/* Section 1: Brief Composer & Document Uploader */}
      <section className="flex flex-col gap-5 rounded-[16px] border border-hairline bg-surface-secondary/45 p-6">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs uppercase tracking-wider text-text-muted">
            01 // Brief & Knowledge Base
          </span>
          {totalChunks > 0 ? (
            <span className="font-mono text-xs text-accent-olive">
              {totalChunks} chunks indexed
            </span>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="agent-title"
            className="font-sans text-xs font-medium text-ink-soft"
          >
            Agent Title (optional)
          </label>
          <input
            id="agent-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., Acme HR Policy & Benefits Advisor"
            className="w-full rounded-[8px] border border-hairline bg-canvas px-3.5 py-2.5 font-sans text-sm text-ink placeholder:text-text-tertiary focus:border-ink focus:outline-none"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="agent-brief"
            className="font-sans text-xs font-medium text-ink-soft"
          >
            Agent Brief
          </label>
          <textarea
            id="agent-brief"
            rows={4}
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="Describe who this agent serves, what questions it must answer, strict refusal boundaries, and citation requirements..."
            className="w-full resize-y rounded-[8px] border border-hairline bg-canvas px-3.5 py-3 font-serif text-base leading-relaxed text-ink placeholder:font-sans placeholder:text-sm placeholder:text-text-tertiary focus:border-ink focus:outline-none"
          />
        </div>

        {/* Drag-and-drop Document Uploader */}
        <div className="flex flex-col gap-3">
          <div
            ref={dropzoneRef}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center gap-2 rounded-[16px] border border-dashed px-6 py-7 text-center transition-colors ${
              isDragging
                ? "border-ink bg-surface-warm/60"
                : "border-hairline bg-canvas hover:bg-surface-secondary/60"
            }`}
          >
            <Upload className="h-5 w-5 text-ink-soft" />
            <div className="font-sans text-sm text-ink">
              Drag & drop source documents here, or{" "}
              <label
                htmlFor={fileInputId}
                className="cursor-pointer font-medium underline decoration-hairline underline-offset-4 hover:decoration-ink"
              >
                browse files
              </label>
            </div>
            <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
              Supports PDF, CSV, MD, TXT
            </p>
            <input
              id={fileInputId}
              type="file"
              multiple
              accept=".pdf,.csv,.md,.txt"
              className="sr-only"
              onChange={(e) => {
                if (e.target.files) {
                  handleFilesAdded(e.target.files);
                  e.target.value = "";
                }
              }}
            />
          </div>

          {/* File Chips */}
          {docs.length > 0 ? (
            <ul className="flex flex-wrap gap-2" aria-label="Uploaded documents">
              {docs.map((doc) => (
                <li
                  key={doc.localId}
                  className="flex items-center gap-2 rounded-[8px] border border-hairline bg-canvas px-3 py-1.5 text-xs text-ink"
                >
                  <FileText className="h-3.5 w-3.5 text-text-muted" />
                  <span className="max-w-[180px] truncate font-medium">
                    {doc.filename}
                  </span>
                  {doc.status === "uploading" ? (
                    <span className="inline-flex items-center gap-1 font-mono text-[11px] text-text-muted">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      indexing
                    </span>
                  ) : null}
                  {doc.status === "queued" ? (
                    <span className="font-mono text-[11px] text-text-muted">
                      queued
                    </span>
                  ) : null}
                  {doc.status === "indexed" ? (
                    <span className="rounded bg-accent-cactus/45 px-1.5 py-0.5 font-mono text-[11px] text-ink">
                      {doc.chunkCount !== null
                        ? `${doc.chunkCount} chunks`
                        : "indexed"}
                    </span>
                  ) : null}
                  {doc.status === "error" ? (
                    <span
                      className="font-mono text-[11px] text-accent-deep"
                      title={doc.error}
                    >
                      failed
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => removeDoc(doc.localId)}
                    className="ml-0.5 rounded p-0.5 text-text-muted hover:bg-surface-secondary hover:text-ink"
                    aria-label={`Remove ${doc.filename}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <p className="font-sans text-xs text-text-muted">
            Step 1 creates the project, indexes chunks, and generates up to 5
            clarifying questions.
          </p>
          <button
            type="button"
            onClick={handleStartIntake}
            disabled={isStartingIntake || !brief.trim()}
            className="inline-flex h-11 items-center gap-2 rounded-[16px] bg-ink px-5 font-serif text-base font-semibold text-canvas transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {isStartingIntake ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Start Intake Interview
          </button>
        </div>
      </section>

      {/* Section 2: Intake Interviewer Flow (≤ 5 clarifying questions) */}
      {questions.length > 0 ? (
        <section className="flex flex-col gap-5 rounded-[16px] border border-hairline bg-canvas p-6">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs uppercase tracking-wider text-text-muted">
              02 // Intake Interviewer ({questions.length} Questions)
            </span>
          </div>

          <form onSubmit={handleSubmitIntake} className="flex flex-col gap-4">
            {questions.map((question, idx) => (
              <div
                key={`${idx}-${question.slice(0, 24)}`}
                className="flex flex-col gap-2 rounded-[8px] border border-hairline bg-surface-secondary/35 p-4"
              >
                <label
                  htmlFor={`intake-q-${idx}`}
                  className="font-serif text-base font-normal text-ink"
                >
                  <span className="mr-2 font-mono text-xs text-text-muted">
                    Q{idx + 1}.
                  </span>
                  {question}
                </label>
                <input
                  id={`intake-q-${idx}`}
                  type="text"
                  value={answers[idx] ?? ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({ ...prev, [idx]: e.target.value }))
                  }
                  placeholder="Type your answer..."
                  className="w-full rounded-[8px] border border-hairline bg-canvas px-3 py-2 font-sans text-sm text-ink placeholder:text-text-tertiary focus:border-ink focus:outline-none"
                />
              </div>
            ))}

            <div className="flex justify-end pt-1">
              <button
                type="submit"
                disabled={isSubmittingIntake}
                className="inline-flex h-11 items-center gap-2 rounded-[16px] border border-ink bg-canvas px-5 font-serif text-base font-semibold text-ink transition-colors hover:bg-surface-secondary disabled:cursor-not-allowed disabled:opacity-45"
              >
                {isSubmittingIntake ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Submit Answers & Verify Groundability
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {/* Section 3: Groundability Guard Banner */}
      {groundability ? (
        <section
          aria-live="polite"
          className={`flex flex-col gap-4 rounded-[16px] border p-6 ${
            groundability.is_passable
              ? "border-[#788c5d] bg-[#bcd1ca]/35"
              : "border-[#c46686] bg-[#d97757]/15"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              {groundability.is_passable ? (
                <CheckCircle2 className="h-5 w-5 text-[#788c5d]" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-[#d97757]" />
              )}
              <span className="font-mono text-xs uppercase tracking-wider text-ink">
                Groundability Guard //{" "}
                {groundability.is_passable ? "Pass" : "Blocked — Critical Gaps"}
              </span>
            </div>
            <span
              className={`rounded-[8px] px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider ${
                groundability.is_passable
                  ? "bg-[#788c5d] text-canvas"
                  : "bg-[#c46686] text-canvas"
              }`}
            >
              {groundability.is_passable ? "Grounded" : "Action Required"}
            </span>
          </div>

          <p className="font-serif text-base leading-relaxed text-ink">
            {groundability.summary}
          </p>

          {groundability.critical_gaps.length > 0 ? (
            <div className="flex flex-col gap-2">
              <span className="font-mono text-[11px] uppercase tracking-wider text-[#c46686]">
                Critical Missing Topics ({groundability.critical_gaps.length})
              </span>
              <ul className="flex flex-col gap-2">
                {groundability.critical_gaps.map((gap) => (
                  <li
                    key={gap.topic}
                    className="rounded-[8px] border border-[#d97757]/50 bg-canvas/85 px-4 py-3 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-sans font-semibold text-ink">
                        {gap.topic}
                      </span>
                      <span className="font-mono text-xs text-[#c46686]">
                        {Math.round(gap.confidence * 100)}% confidence
                      </span>
                    </div>
                    {gap.gap_reason ? (
                      <p className="mt-1 font-sans text-xs text-ink-soft">
                        {gap.gap_reason}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {groundability.warnings.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Warnings ({groundability.warnings.length})
              </span>
              <ul className="flex flex-col gap-1.5">
                {groundability.warnings.map((warn) => (
                  <li
                    key={warn.topic}
                    className="rounded-[8px] border border-hairline bg-canvas/70 px-3 py-2 text-xs text-ink-soft"
                  >
                    <strong className="text-ink">{warn.topic}:</strong>{" "}
                    {warn.gap_reason ?? "Low supporting coverage."}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* Section 4: Build & Optimize Agent CTA */}
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-[16px] border border-hairline bg-surface-secondary/60 px-6 py-5">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-xs uppercase tracking-wider text-text-muted">
            03 // Synthesis & Critic-Optimizer Loop
          </span>
          <p className="font-sans text-sm text-ink-soft">
            {isGroundabilityBlocked
              ? "Upload documents covering the missing topics above to unblock synthesis."
              : "Synthesizes AgentDefinition, generates evals, and runs iterative refinement."}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {projectId && !deliverable ? (
            <button
              type="button"
              onClick={() => void loadProjectState(projectId)}
              className="inline-flex h-11 items-center gap-2 rounded-[16px] border border-hairline bg-canvas px-4 font-sans text-xs font-medium text-ink hover:bg-surface-secondary"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleBuildAgent}
            disabled={isBuildingAgent || isGroundabilityBlocked || !brief.trim()}
            className="inline-flex h-11 items-center gap-2 rounded-[16px] bg-ink px-6 font-serif text-base font-semibold text-canvas transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isBuildingAgent ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Build & Optimize Agent
          </button>
        </div>
      </section>

      {/* Section 5: Final Deliverable Card */}
      {deliverable ? (
        <section className="flex flex-col gap-5 rounded-[16px] border border-ink bg-canvas p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-4">
            <div className="flex flex-col gap-1">
              <span className="font-mono text-xs uppercase tracking-wider text-[#788c5d]">
                Final Deliverable // Ready to Launch
              </span>
              <h2 className="font-serif text-2xl font-normal text-ink">
                /agent/{deliverable.agent.slug}
              </h2>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void handleCopyUrl(deliverable.agent.slug)}
                className="inline-flex h-10 items-center gap-2 rounded-[16px] border border-hairline bg-surface-secondary px-4 font-sans text-xs font-medium text-ink transition-colors hover:bg-surface-secondary-hover"
              >
                {copiedUrl ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-[#788c5d]" />
                    Copied URL
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    Copy URL
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={() => setShowArtifactsJson((prev) => !prev)}
                className="inline-flex h-10 items-center gap-2 rounded-[16px] border border-hairline bg-canvas px-4 font-sans text-xs font-medium text-ink transition-colors hover:bg-surface-secondary"
              >
                <Code2 className="h-3.5 w-3.5" />
                {showArtifactsJson ? "Hide Artifacts JSON" : "Export Artifacts"}
              </button>

              <Link
                href={`/agent/${deliverable.agent.slug}`}
                className="inline-flex h-10 items-center gap-1.5 rounded-[16px] bg-ink px-4 font-serif text-sm font-semibold text-canvas transition-opacity hover:opacity-90"
              >
                Launch Agent
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-[8px] border border-hairline bg-surface-secondary/50 p-3.5">
              <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Agent Version
              </span>
              <p className="mt-1 font-serif text-xl text-ink">
                v{deliverable.agent.version}
              </p>
            </div>
            <div className="rounded-[8px] border border-hairline bg-surface-secondary/50 p-3.5">
              <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Attached Tools
              </span>
              <p className="mt-1 font-mono text-xs text-ink">
                {deliverable.agent.selected_tools.length > 0
                  ? deliverable.agent.selected_tools.join(", ")
                  : "None (RAG-only)"}
              </p>
            </div>
            <div className="rounded-[8px] border border-hairline bg-surface-secondary/50 p-3.5">
              <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Final Pass Rate
              </span>
              <p className="mt-1 font-serif text-xl text-ink">
                {deliverable.honestReport
                  ? `${Math.round(deliverable.honestReport.final_pass_rate * 100)}%`
                  : "Pending"}
              </p>
            </div>
          </div>

          {showArtifactsJson ? (
            <div className="flex flex-col gap-2 rounded-[8px] border border-hairline bg-inverse p-4 text-canvas">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[11px] uppercase tracking-wider text-text-secondary">
                  Artifacts JSON
                </span>
                <button
                  type="button"
                  onClick={handleDownloadJson}
                  className="inline-flex items-center gap-1.5 rounded-[8px] border border-ink-soft px-2.5 py-1 font-mono text-[11px] text-canvas hover:bg-ink-soft"
                >
                  <Download className="h-3 w-3" />
                  Download JSON
                </button>
              </div>
              <pre className="max-h-80 overflow-auto font-mono text-xs leading-relaxed text-canvas/90">
                {JSON.stringify(deliverable, null, 2)}
              </pre>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
