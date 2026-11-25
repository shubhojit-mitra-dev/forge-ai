"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import {
  Calculator,
  Calendar,
  CloudSun,
  FileSpreadsheet,
  FileText,
  Info,
  Send,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import { chatWithPublicAgent } from "@/lib/api";
import type {
  AgentDefinition,
  HonestReport,
  ToolName,
} from "@/types/forge";

export interface AgentChatRunnerProps {
  agent: AgentDefinition;
  agentName?: string;
  honestReport?: HonestReport | null;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  toolsUsed?: string[];
  latencyMs?: number;
  isError?: boolean;
}

const TOOL_META: Record<
  ToolName,
  { label: string; icon: typeof Calculator; description: string }
> = {
  csv_lookup: {
    label: "csv_lookup",
    icon: FileSpreadsheet,
    description: "Structured CSV row lookup",
  },
  calculator: {
    label: "calculator",
    icon: Calculator,
    description: "Deterministic arithmetic",
  },
  current_date: {
    label: "current_date",
    icon: Calendar,
    description: "Current UTC date & time",
  },
  weather_http: {
    label: "weather_http",
    icon: CloudSun,
    description: "Live weather API lookup",
  },
};

function formatSlugAsTitle(slug: string): string {
  return slug
    .split("-")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function AgentChatRunner({
  agent,
  agentName,
  honestReport = null,
}: AgentChatRunnerProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [inspectOpen, setInspectOpen] = useState(false);

  const displayName = agentName ?? formatSlugAsTitle(agent.slug);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await chatWithPublicAgent(agent.slug, trimmed);
      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: res.answer,
        citations: res.citations,
        toolsUsed: res.tools_used,
        latencyMs: res.latency_ms,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to reach agent endpoint.";
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: errorMessage,
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void sendMessage(input);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage(input);
    }
  }

  return (
    <div className="flex min-h-screen bg-[#faf9f5] text-[#141413]">
      {/* Main Chat Column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Header */}
        <header className="border-b border-[#d1cfc5] bg-[#faf9f5] px-4 py-4 sm:px-8">
          <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-xs uppercase tracking-wider text-[#5e5d59]">
                  FORGE\AI AGENT
                </span>
                <span className="rounded-[8px] border border-[#d1cfc5] bg-[#f0eee6] px-2 py-0.5 font-mono text-[11px] tabular-nums text-[#141413]">
                  v{agent.version}
                </span>
              </div>
              <h1 className="mt-1 font-serif text-2xl font-normal tracking-tight text-[#141413] sm:text-3xl">
                {displayName}
              </h1>
            </div>

            <button
              type="button"
              onClick={() => setInspectOpen((prev) => !prev)}
              aria-expanded={inspectOpen}
              className="inline-flex items-center gap-2 rounded-[8px] border border-[#141413] bg-[#faf9f5] px-3.5 py-2 text-xs font-medium text-[#141413] transition-colors hover:bg-[#f0eee6]"
            >
              <Info className="h-3.5 w-3.5" />
              <span>Inspect Agent Contract &amp; Honest Report</span>
            </button>
          </div>

          {/* Attached Tools Pills */}
          <div className="mx-auto mt-3 flex max-w-3xl flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
              <Wrench className="h-3 w-3" />
              Tools:
            </span>
            {agent.selected_tools.length === 0 ? (
              <span className="rounded-[8px] border border-[#d1cfc5] bg-[#f0eee6] px-2.5 py-1 font-mono text-xs text-[#5e5d59]">
                knowledge-only (no external tools)
              </span>
            ) : (
              agent.selected_tools.map((tool) => {
                const meta = TOOL_META[tool];
                const Icon = meta.icon;
                return (
                  <span
                    key={tool}
                    title={meta.description}
                    className="inline-flex items-center gap-1.5 rounded-[8px] border border-[#d1cfc5] bg-[#f0eee6] px-2.5 py-1 font-mono text-xs text-[#141413]"
                  >
                    <Icon className="h-3.5 w-3.5 text-[#5e5d59]" />
                    {meta.label}
                  </span>
                );
              })
            )}
          </div>
        </header>

        {/* Message Thread */}
        <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.length === 0 ? (
              <div className="rounded-[16px] border border-[#d1cfc5] bg-[#f0eee6] p-6 sm:p-8">
                <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-[#5e5d59]">
                  <Sparkles className="h-3.5 w-3.5 text-[#d97757]" />
                  <span>Grounded Agent Ready</span>
                </div>
                <p className="mt-3 font-serif text-lg leading-relaxed text-[#141413]">
                  Ask a question grounded in this agent&apos;s knowledge base.
                  {agent.output_contract.require_citations
                    ? " Responses include inline source citations and refuse out-of-scope requests."
                    : " Out-of-scope requests are refused according to the agent contract."}
                </p>
                <div className="mt-4 flex flex-wrap gap-2 text-xs text-[#5e5d59]">
                  <span className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] px-2.5 py-1 font-mono">
                    format: {agent.output_contract.format}
                  </span>
                  <span className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] px-2.5 py-1 font-mono tabular-nums">
                    max_words: {agent.output_contract.max_response_words}
                  </span>
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={
                    msg.role === "user"
                      ? "ml-auto max-w-[85%] rounded-[16px] bg-[#141413] px-4 py-3 text-sm text-[#faf9f5]"
                      : `rounded-[16px] border p-5 ${
                          msg.isError
                            ? "border-[#c6613f] bg-[#ebcece]/40 text-[#141413]"
                            : "border-[#d1cfc5] bg-[#f0eee6] text-[#141413]"
                        }`
                  }
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-wider opacity-70">
                      {msg.role === "user" ? "You" : displayName}
                    </span>
                    {msg.latencyMs !== undefined && (
                      <span className="font-mono text-[10px] tabular-nums text-[#5e5d59]">
                        {Math.round(msg.latencyMs)}ms
                      </span>
                    )}
                  </div>

                  <div className="whitespace-pre-wrap text-[15px] leading-relaxed">
                    {msg.content}
                  </div>

                  {/* Inline Citation Chips & Tools Used */}
                  {((msg.citations && msg.citations.length > 0) ||
                    (msg.toolsUsed && msg.toolsUsed.length > 0)) && (
                    <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[#d1cfc5] pt-2.5">
                      {msg.citations?.map((cite, idx) => (
                        <span
                          key={`${msg.id}-cite-${idx}`}
                          className="inline-flex items-center gap-1 rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] px-2 py-0.5 font-mono text-[11px] text-[#141413]"
                        >
                          <FileText className="h-3 w-3 text-[#6a9bcc]" />
                          {cite}
                        </span>
                      ))}
                      {msg.toolsUsed?.map((tool, idx) => (
                        <span
                          key={`${msg.id}-tool-${idx}`}
                          className="inline-flex items-center gap-1 rounded-[8px] border border-[#d1cfc5] bg-[#ebdbbc]/70 px-2 py-0.5 font-mono text-[11px] text-[#141413]"
                        >
                          <Wrench className="h-3 w-3 text-[#5e5d59]" />
                          {tool}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}

            {isLoading && (
              <div className="rounded-[16px] border border-[#d1cfc5] bg-[#f0eee6] p-4">
                <div className="font-mono text-xs text-[#5e5d59]">
                  Retrieving context &amp; generating grounded response…
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Composer */}
        <footer className="border-t border-[#d1cfc5] bg-[#faf9f5] px-4 py-4 sm:px-8">
          <form
            onSubmit={handleSubmit}
            className="mx-auto flex max-w-3xl items-end gap-3"
          >
            <label htmlFor="agent-chat-input" className="sr-only">
              Message {displayName}
            </label>
            <textarea
              id="agent-chat-input"
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Ask ${displayName} a question…`}
              disabled={isLoading}
              className="min-h-[44px] flex-1 resize-none rounded-[8px] border border-[#b0aea5] bg-[#faf9f5] px-3.5 py-2.5 text-sm text-[#141413] placeholder:text-[#87867f] focus:border-[#141413] focus:outline-none disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="inline-flex h-[44px] items-center gap-2 rounded-[16px] bg-[#141413] px-5 text-sm font-medium text-[#faf9f5] transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
              <span>Send</span>
            </button>
          </form>
        </footer>
      </div>

      {/* Inspect Agent Contract & Honest Report Drawer */}
      {inspectOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-[#141413]/30 lg:hidden"
            onClick={() => setInspectOpen(false)}
            aria-hidden="true"
          />
          <aside
            aria-label="Agent Contract and Honest Report"
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[420px] flex-col border-l border-[#d1cfc5] bg-[#f0eee6] text-[#141413] lg:static lg:z-auto lg:w-[420px] lg:shrink-0"
          >
            <div className="flex items-center justify-between border-b border-[#d1cfc5] px-4 py-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-[#141413]" />
                <span className="font-mono text-xs uppercase tracking-wider">
                  Contract &amp; Honest Report
                </span>
              </div>
              <button
                type="button"
                onClick={() => setInspectOpen(false)}
                aria-label="Close inspector drawer"
                className="rounded-[8px] p-1.5 text-[#5e5d59] hover:bg-[#e8e6dc] hover:text-[#141413]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto p-4">
              {/* Output Contract */}
              <section>
                <h2 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
                  Output Contract
                </h2>
                <div className="space-y-2 rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3 text-xs">
                  <div className="flex justify-between">
                    <span className="text-[#5e5d59]">Format</span>
                    <span className="font-mono text-[#141413]">
                      {agent.output_contract.format}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#5e5d59]">Require Citations</span>
                    <span className="font-mono text-[#141413]">
                      {agent.output_contract.require_citations ? "true" : "false"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#5e5d59]">Max Words</span>
                    <span className="font-mono tabular-nums text-[#141413]">
                      {agent.output_contract.max_response_words}
                    </span>
                  </div>
                  <div className="border-t border-[#d1cfc5] pt-2">
                    <div className="text-[#5e5d59]">Refusal Template</div>
                    <p className="mt-1 font-mono text-[11px] leading-relaxed text-[#141413]">
                      {agent.output_contract.refusal_template}
                    </p>
                  </div>
                </div>
              </section>

              {/* Retrieval Config */}
              <section>
                <h2 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
                  Retrieval Config
                </h2>
                <div className="grid grid-cols-2 gap-2 rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3 text-xs">
                  <div>
                    <div className="text-[#5e5d59]">Top K</div>
                    <div className="font-mono tabular-nums text-[#141413]">
                      {agent.retrieval_config.top_k}
                    </div>
                  </div>
                  <div>
                    <div className="text-[#5e5d59]">Threshold</div>
                    <div className="font-mono tabular-nums text-[#141413]">
                      {agent.retrieval_config.similarity_threshold}
                    </div>
                  </div>
                  <div>
                    <div className="text-[#5e5d59]">Chunk Size</div>
                    <div className="font-mono tabular-nums text-[#141413]">
                      {agent.retrieval_config.chunk_size}
                    </div>
                  </div>
                  <div>
                    <div className="text-[#5e5d59]">Hybrid Search</div>
                    <div className="font-mono text-[#141413]">
                      {agent.retrieval_config.hybrid_search ? "enabled" : "off"}
                    </div>
                  </div>
                </div>
              </section>

              {/* Honest Report */}
              <section>
                <h2 className="mb-2 font-mono text-[11px] uppercase tracking-wider text-[#5e5d59]">
                  Honest Report
                </h2>
                {honestReport ? (
                  <div className="space-y-3 rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-[#5e5d59]">Final Pass Rate</span>
                      <span className="font-mono text-base font-semibold tabular-nums text-[#141413]">
                        {(honestReport.final_pass_rate * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="border-t border-[#d1cfc5] pt-2">
                      <div className="text-[#5e5d59]">Recommendation</div>
                      <p className="mt-1 leading-relaxed text-[#141413]">
                        {honestReport.recommendation}
                      </p>
                    </div>
                    {honestReport.known_limitations.length > 0 && (
                      <div className="border-t border-[#d1cfc5] pt-2">
                        <div className="text-[#5e5d59]">Known Limitations</div>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-[#141413]">
                          {honestReport.known_limitations.map((lim, i) => (
                            <li key={i}>{lim}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {honestReport.remaining_failures.length > 0 && (
                      <div className="border-t border-[#d1cfc5] pt-2">
                        <div className="text-[#5e5d59]">
                          Remaining Failures (
                          {honestReport.remaining_failures.length})
                        </div>
                        <div className="mt-1 space-y-1.5">
                          {honestReport.remaining_failures.map((fail, i) => (
                            <div
                              key={i}
                              className="rounded border border-[#d1cfc5] bg-[#f0eee6] p-2 font-mono text-[11px]"
                            >
                              {fail.question ?? fail.reason ?? JSON.stringify(fail)}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-[8px] border border-[#d1cfc5] bg-[#faf9f5] p-3 text-xs text-[#87867f]">
                    Honest Report summary is not attached to this public
                    metadata payload.
                  </div>
                )}
              </section>
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
