"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LogIn,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import type { ProjectSummary } from "@/types/forge";

type KnownStatus = "forging" | "drafting" | "blocked" | "ready";

interface StatusConfig {
  label: string;
  dotClass: string;
  pulse?: boolean;
}

const STATUS_META: Record<KnownStatus, StatusConfig> = {
  forging: {
    label: "Forging",
    dotClass: "bg-accent-clay",
    pulse: true,
  },
  drafting: {
    label: "Drafting",
    dotClass: "bg-accent-sky",
  },
  blocked: {
    label: "Blocked",
    dotClass: "bg-accent-fig",
  },
  ready: {
    label: "Ready",
    dotClass: "bg-accent-olive",
  },
};

const GROUP_ORDER: KnownStatus[] = ["forging", "drafting", "blocked", "ready"];

function getStatusMeta(status: string): StatusConfig {
  const normalized = status.toLowerCase() as KnownStatus;
  if (normalized in STATUS_META) {
    return STATUS_META[normalized];
  }
  return {
    label: status || "Other",
    dotClass: "bg-text-secondary",
  };
}

export interface CollapsibleSidebarProps {
  projects: ProjectSummary[];
  userEmail: string | null;
}

export function CollapsibleSidebar({
  projects,
  userEmail,
}: CollapsibleSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const groupedProjects = useMemo(() => {
    const groups = new Map<string, ProjectSummary[]>();

    for (const key of GROUP_ORDER) {
      groups.set(key, []);
    }

    for (const project of projects) {
      const normalized = project.status.toLowerCase();
      const groupKey = GROUP_ORDER.includes(normalized as KnownStatus)
        ? normalized
        : "other";
      const existing = groups.get(groupKey) ?? [];
      existing.push(project);
      groups.set(groupKey, existing);
    }

    return Array.from(groups.entries())
      .filter(([, items]) => items.length > 0)
      .map(([key, items]) => ({
        key,
        label:
          key in STATUS_META
            ? STATUS_META[key as KnownStatus].label
            : "Other",
        items,
      }));
  }, [projects]);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      const supabase = createClient();
      await supabase.auth.signOut();
    } catch {
      // Ignore if Supabase env is not configured in preview mode.
    } finally {
      setSigningOut(false);
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <aside
      aria-label="Workspace navigation"
      className={cn(
        "shrink-0 h-screen sticky top-0 flex flex-col bg-surface-secondary border-r border-hairline transition-[width] duration-200 ease-out select-none",
        collapsed ? "w-[56px]" : "w-[260px]",
      )}
    >
      {/* Header & collapse toggle */}
      <div
        className={cn(
          "flex items-center h-14 px-3 border-b border-hairline",
          collapsed ? "justify-center" : "justify-between",
        )}
      >
        {!collapsed ? (
          <Link
            href="/"
            className="font-sans font-bold tracking-tight text-base text-ink truncate"
          >
            FORGE\AI
          </Link>
        ) : null}

        <button
          type="button"
          onClick={() => setCollapsed((prev) => !prev)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className="p-1.5 rounded-[8px] text-text-muted hover:text-ink hover:bg-surface-secondary-hover transition-colors cursor-pointer"
        >
          {collapsed ? (
            <PanelLeftOpen className="w-4 h-4" />
          ) : (
            <PanelLeftClose className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* New Agent CTA */}
      <div className="p-3">
        <Link
          href="/"
          title="New Agent"
          className={cn(
            "flex items-center justify-center gap-2 bg-ink text-canvas font-sans text-sm font-medium rounded-[8px] hover:opacity-90 transition-opacity",
            collapsed ? "h-9 w-8 mx-auto px-0" : "h-10 w-full px-3",
          )}
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed ? <span>New Agent</span> : null}
        </Link>
      </div>

      {/* Grouped project history */}
      <nav
        aria-label="Agent projects"
        className="flex-1 overflow-y-auto px-2 pb-4 space-y-5"
      >
        {groupedProjects.length === 0 ? (
          !collapsed ? (
            <div className="px-2 py-6 text-center">
              <p className="font-mono text-[11px] uppercase tracking-wider text-text-tertiary mb-1">
                No Agents Yet
              </p>
              <p className="font-serif text-sm text-text-muted">
                Create a new agent brief to start forging.
              </p>
            </div>
          ) : null
        ) : (
          groupedProjects.map((group) => (
            <div key={group.key} className="space-y-1">
              {!collapsed ? (
                <div className="px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-text-tertiary">
                  {group.label}
                </div>
              ) : null}

              <ul className="space-y-0.5">
                {group.items.map((project) => {
                  const href = `/projects/${project.id}`;
                  const isActive =
                    pathname === href || pathname.startsWith(`${href}/`);
                  const statusMeta = getStatusMeta(project.status);

                  return (
                    <li key={project.id}>
                      <Link
                        href={href}
                        title={`${project.title} (${statusMeta.label})`}
                        className={cn(
                          "group flex items-center gap-2.5 rounded-[8px] transition-colors",
                          collapsed
                            ? "justify-center h-9 w-9 mx-auto"
                            : "px-2.5 py-2",
                          isActive
                            ? "bg-surface-warm text-ink font-medium"
                            : "text-ink-soft hover:bg-surface-secondary-hover hover:text-ink",
                        )}
                      >
                        <span
                          aria-hidden="true"
                          className={cn(
                            "w-2 h-2 rounded-full shrink-0",
                            statusMeta.dotClass,
                            statusMeta.pulse ? "animate-pulse" : "",
                          )}
                        />
                        {!collapsed ? (
                          <span className="text-[13px] leading-snug truncate">
                            {project.title}
                          </span>
                        ) : null}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </nav>

      {/* Footer: user email & sign-out */}
      <div className="border-t border-hairline p-3">
        {userEmail ? (
          <div
            className={cn(
              "flex items-center gap-2",
              collapsed ? "justify-center" : "justify-between",
            )}
          >
            {!collapsed ? (
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[10px] uppercase tracking-wider text-text-tertiary">
                  Operator
                </p>
                <p
                  title={userEmail}
                  className="text-xs text-ink truncate font-sans"
                >
                  {userEmail}
                </p>
              </div>
            ) : null}

            <button
              type="button"
              onClick={handleSignOut}
              disabled={signingOut}
              title="Sign out"
              aria-label="Sign out"
              className="p-2 rounded-[8px] text-text-muted hover:text-ink hover:bg-surface-secondary-hover transition-colors cursor-pointer disabled:opacity-50"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            title="Sign in"
            className={cn(
              "flex items-center gap-2 rounded-[8px] text-xs font-medium text-ink hover:bg-surface-secondary-hover transition-colors",
              collapsed ? "justify-center h-9 w-9 mx-auto" : "px-2.5 py-2",
            )}
          >
            <LogIn className="w-4 h-4 shrink-0 text-text-muted" />
            {!collapsed ? <span>Sign in</span> : null}
          </Link>
        )}
      </div>
    </aside>
  );
}
