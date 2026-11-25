import { notFound } from "next/navigation";
import { Suspense } from "react";
import { z } from "zod";
import { AgentChatRunner } from "@/features/agent-runner/AgentChatRunner";
import { getPublicAgent } from "@/lib/api";
import {
  HonestReportSchema,
  ToolNameSchema,
  type AgentDefinition,
  type HonestReport,
} from "@/types/forge";

const PublicAgentPayloadSchema = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  slug: z.string().min(1),
  version: z.number().int().min(1),
  selected_tools: z.array(ToolNameSchema),
  output_contract: z.object({
    format: z.enum(["markdown", "json"]),
    require_citations: z.boolean(),
    refusal_template: z.string(),
    max_response_words: z.number(),
  }),
  system_prompt: z.string().optional(),
  name: z.string().optional(),
  retrieval_config: z
    .object({
      chunk_size: z.number(),
      chunk_overlap: z.number(),
      top_k: z.number(),
      similarity_threshold: z.number(),
      hybrid_search: z.boolean(),
    })
    .optional(),
  honest_report: HonestReportSchema.nullable().optional(),
});

interface PublicAgentPageProps {
  params: Promise<{ slug: string }>;
}

async function PublicAgentLoader({ params }: PublicAgentPageProps) {
  const { slug } = await params;

  let rawPayload: Record<string, unknown>;
  try {
    rawPayload = await getPublicAgent(slug);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "";
    if (msg.includes("404")) {
      notFound();
    }
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#faf9f5] px-4 text-[#141413]">
        <div className="max-w-md rounded-[16px] border border-[#d1cfc5] bg-[#f0eee6] p-8">
          <div className="font-mono text-xs uppercase tracking-wider text-[#5e5d59]">
            FORGE\AI
          </div>
          <h1 className="mt-2 font-serif text-2xl font-normal">
            Agent Unavailable
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-[#5e5d59]">
            Unable to load published agent{" "}
            <span className="font-mono text-[#141413]">{slug}</span>.
          </p>
        </div>
      </main>
    );
  }

  const parsed = PublicAgentPayloadSchema.parse(rawPayload);

  const agent: AgentDefinition = {
    id: parsed.id,
    project_id: parsed.project_id,
    slug: parsed.slug,
    version: parsed.version,
    system_prompt: parsed.system_prompt ?? "",
    selected_tools: parsed.selected_tools,
    retrieval_config: parsed.retrieval_config ?? {
      chunk_size: 512,
      chunk_overlap: 64,
      top_k: 5,
      similarity_threshold: 0.7,
      hybrid_search: true,
    },
    output_contract: parsed.output_contract,
  };

  const honestReport: HonestReport | null = parsed.honest_report ?? null;

  return (
    <AgentChatRunner
      agent={agent}
      agentName={parsed.name}
      honestReport={honestReport}
    />
  );
}

export default function PublicAgentPage({ params }: PublicAgentPageProps) {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-[#faf9f5] font-mono text-xs uppercase tracking-wider text-[#5e5d59]">
          Loading agent…
        </main>
      }
    >
      <PublicAgentLoader params={params} />
    </Suspense>
  );
}
