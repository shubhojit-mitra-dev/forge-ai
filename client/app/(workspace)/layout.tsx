import { Suspense, type ReactNode } from "react";
import { redirect } from "next/navigation";
import { CollapsibleSidebar } from "@/features/sidebar/CollapsibleSidebar";
import { listProjects } from "@/lib/api";
import { createClient } from "@/lib/supabase/server";
import type { ProjectSummary } from "@/types/forge";

function SidebarFallback() {
  return (
    <aside
      aria-label="Loading workspace navigation"
      className="shrink-0 w-[260px] h-screen sticky top-0 flex flex-col bg-surface-secondary border-r border-hairline"
    >
      <div className="h-14 px-3 border-b border-hairline flex items-center">
        <span className="font-sans font-bold tracking-tight text-base text-ink">
          FORGE\AI
        </span>
      </div>
      <div className="p-3">
        <div className="h-10 w-full rounded-[8px] bg-surface-warm/60 animate-pulse" />
      </div>
      <div className="flex-1 px-3 py-2 space-y-2">
        <div className="h-3 w-16 rounded bg-surface-warm/70 animate-pulse" />
        <div className="h-8 w-full rounded-[8px] bg-surface-warm/50 animate-pulse" />
        <div className="h-8 w-5/6 rounded-[8px] bg-surface-warm/50 animate-pulse" />
      </div>
    </aside>
  );
}

async function WorkspaceSidebarLoader() {
  const hasSupabaseEnv = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );

  if (!hasSupabaseEnv) {
    return <CollapsibleSidebar projects={[]} userEmail={null} />;
  }

  let userEmail: string | null = null;
  let projects: ProjectSummary[] = [];
  let shouldRedirectToLogin = false;

  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      shouldRedirectToLogin =
        process.env.NEXT_PUBLIC_REQUIRE_AUTH === "true";
    } else {
      userEmail = user.email ?? null;

      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (session?.access_token) {
        try {
          projects = await listProjects(session.access_token);
        } catch {
          // Backend API may be offline during preview or initial setup.
          projects = [];
        }
      }
    }
  } catch {
    userEmail = null;
    projects = [];
  }

  if (shouldRedirectToLogin) {
    redirect("/login");
  }

  return <CollapsibleSidebar projects={projects} userEmail={userEmail} />;
}

export default function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      <Suspense fallback={<SidebarFallback />}>
        <WorkspaceSidebarLoader />
      </Suspense>
      <main className="flex-1 min-w-0 flex flex-col">{children}</main>
    </div>
  );
}
