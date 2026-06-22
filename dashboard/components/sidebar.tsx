"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Search, Network, GitBranch,
  Users, Layers, CheckSquare, Radio,
  Shield, DatabaseBackup, Settings2, Bookmark,
  Package, ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_PRIMARY = [
  { href: "/",                label: "Overview",        icon: LayoutDashboard },
  { href: "/explorer",        label: "Explorer",        icon: Search },
  { href: "/agents/graph",    label: "Agent Graph",     icon: Network },
  { href: "/memory/timeline", label: "Memory Timeline", icon: GitBranch },
];

const NAV_SECONDARY = [
  { href: "/agents",       label: "Agents",          icon: Users },
  { href: "/streams",      label: "Streams",         icon: Layers },
  { href: "/tasks",        label: "Tasks",           icon: CheckSquare },
  { href: "/search",       label: "Search",          icon: Search },
  { href: "/permissions",  label: "Permissions",     icon: Shield },
  { href: "/snapshots",    label: "Snapshots",       icon: Bookmark },
  { href: "/events",       label: "Protocol Events", icon: Radio },
  { href: "/recovery",     label: "Recovery",        icon: DatabaseBackup },
  { href: "/settings",     label: "Settings",        icon: Settings2 },
];

function NavItem({ href, label, icon: Icon, pathname }: {
  href: string; label: string; icon: React.ComponentType<{ className?: string }>;
  pathname: string;
}) {
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-violet-600/20 text-violet-300"
          : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex h-screen w-56 flex-col border-r border-slate-800 bg-slate-950 px-3 py-6 shrink-0">
      {/* Logo */}
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 text-white font-bold text-sm">W</div>
        <span className="text-slate-100 font-semibold tracking-tight">WalrusOS</span>
        <span className="ml-auto rounded-full bg-violet-900/60 px-2 py-0.5 text-[10px] text-violet-300">v0.1</span>
      </div>

      {/* Primary nav */}
      <nav className="flex flex-col gap-0.5">
        {NAV_PRIMARY.map(item => (
          <NavItem key={item.href} {...item} pathname={pathname} />
        ))}
      </nav>

      <div className="my-4 h-px bg-slate-800" />

      {/* Secondary nav */}
      <nav className="flex flex-col gap-0.5 overflow-y-auto">
        <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
          More
        </p>
        {NAV_SECONDARY.map(item => (
          <NavItem key={item.href} {...item} pathname={pathname} />
        ))}
      </nav>

      {/* Footer */}
      <div className="mt-auto pt-4 px-2 text-[11px] text-slate-600">
        <div>Bridge: localhost:8787</div>
        <div className="flex items-center gap-1 mt-1">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Connected
        </div>
      </div>
    </aside>
  );
}
