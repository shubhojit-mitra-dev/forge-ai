"use client";

import { useState } from "react";
import { BuilderWorkspace } from "@/features/builder-chat/BuilderWorkspace";
import { EvalObservabilityDrawer } from "@/features/eval-observability/EvalObservabilityDrawer";

export interface ProjectWorkspaceSplitProps {
  projectId: string;
}

export function ProjectWorkspaceSplit({
  projectId,
}: ProjectWorkspaceSplitProps) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(true);
  const [isStreamActive, setIsStreamActive] = useState(false);

  return (
    <div className="flex min-h-full w-full flex-1 flex-col bg-canvas lg:flex-row">
      <main className="min-w-0 flex-1 overflow-y-auto">
        <BuilderWorkspace
          projectId={projectId}
          onOpenEvalDrawer={() => {
            setIsDrawerOpen(true);
            setIsStreamActive(true);
          }}
        />
      </main>
      <EvalObservabilityDrawer
        projectId={projectId}
        isOpen={isDrawerOpen}
        onToggle={() => setIsDrawerOpen((prev) => !prev)}
        streamActive={isStreamActive}
      />
    </div>
  );
}
