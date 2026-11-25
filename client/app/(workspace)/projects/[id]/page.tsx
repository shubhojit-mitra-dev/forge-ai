import { Suspense } from "react";
import { ProjectWorkspaceSplit } from "@/features/builder-chat/ProjectWorkspaceSplit";

async function ProjectWorkspaceLoader({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ProjectWorkspaceSplit projectId={id} />;
}

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center bg-[#faf9f5] font-mono text-xs uppercase tracking-wider text-[#5e5d59]">
          Loading workspace…
        </div>
      }
    >
      <ProjectWorkspaceLoader params={params} />
    </Suspense>
  );
}
