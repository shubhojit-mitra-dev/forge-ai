import {
  ChatResponseSchema,
  GroundabilityReportSchema,
  ProjectSummarySchema,
  type ChatResponse,
  type GroundabilityReport,
  type ProjectSummary,
} from "@/types/forge";
import { z } from "zod";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string; schema?: z.ZodType<T> } = {},
): Promise<T> {
  const { token, schema, headers, ...rest } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(rest.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API ${res.status}: ${errText}`);
  }
  const data: unknown = await res.json();
  return schema ? schema.parse(data) : (data as T);
}

export async function listProjects(token: string): Promise<ProjectSummary[]> {
  return apiFetch("/projects", {
    token,
    schema: z.array(ProjectSummarySchema),
  });
}

export async function createProject(
  token: string,
  title: string,
  brief: string,
): Promise<ProjectSummary> {
  return apiFetch("/projects", {
    method: "POST",
    token,
    body: JSON.stringify({ title, brief }),
    schema: ProjectSummarySchema,
  });
}

export async function getProjectDetail(
  token: string,
  projectId: string,
): Promise<Record<string, unknown>> {
  return apiFetch(`/projects/${projectId}`, { token });
}

export async function uploadDocument(
  token: string,
  projectId: string,
  file: File,
): Promise<{ id: string; filename: string; chunk_count: number }> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch(`/projects/${projectId}/documents`, {
    method: "POST",
    token,
    body: form,
  });
}

export async function startIntake(
  token: string,
  projectId: string,
): Promise<{ questions: string[] }> {
  return apiFetch(`/projects/${projectId}/intake/start`, {
    method: "POST",
    token,
  });
}

export async function submitIntake(
  token: string,
  projectId: string,
  qaPairs: { question: string; answer: string }[],
): Promise<{
  requirements: Record<string, unknown>;
  groundability: GroundabilityReport;
}> {
  const res = await apiFetch<{
    requirements: Record<string, unknown>;
    groundability: unknown;
  }>(`/projects/${projectId}/intake/submit`, {
    method: "POST",
    token,
    body: JSON.stringify({ qa_pairs: qaPairs }),
  });
  return {
    requirements: res.requirements,
    groundability: GroundabilityReportSchema.parse(res.groundability),
  };
}

export async function runForgePipeline(
  token: string,
  projectId: string,
): Promise<Record<string, unknown>> {
  return apiFetch(`/projects/${projectId}/forge/run`, {
    method: "POST",
    token,
  });
}

export function getForgeStreamUrl(projectId: string): string {
  return `${API_BASE}/projects/${projectId}/forge/stream`;
}

export async function getPublicAgent(
  slug: string,
): Promise<Record<string, unknown>> {
  return apiFetch(`/agents/public/${slug}`);
}

export async function chatWithPublicAgent(
  slug: string,
  message: string,
): Promise<ChatResponse> {
  return apiFetch(`/agents/public/${slug}/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
    schema: ChatResponseSchema,
  });
}

