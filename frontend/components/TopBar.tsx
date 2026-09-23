"use client";
/* Top status bar: service health + active engine providers. */
import clsx from "clsx";
import { Cpu, Database, Gauge, Hexagon, Radio, ShieldCheck } from "lucide-react";
import type { EngineConfig, Health, Stats } from "@/lib/types";
import { Badge } from "./ui";

function Pill({
  icon: Icon,
  label,
  value,
  tone = "slate",
}: {
  icon: any;
  label: string;
  value: string;
  tone?: "slate" | "cyan" | "emerald" | "amber" | "violet" | "rose";
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-slate-700/60 bg-slate-900/70 px-2.5 py-1 text-[10.5px] text-slate-400"
      title={`${label}: ${value}`}
    >
      <Icon size={11} className={clsx(
        tone === "cyan" && "text-cyan-400",
        tone === "emerald" && "text-emerald-400",
        tone === "amber" && "text-amber-400",
        tone === "violet" && "text-violet-400",
        tone === "rose" && "text-rose-400",
        tone === "slate" && "text-slate-500",
      )} />
      <span className="text-slate-600">{label}</span>
      <span className="font-medium text-slate-300">{value}</span>
    </span>
  );
}

export default function TopBar({
  health,
  stats,
  config,
}: {
  health: Health | null;
  stats: Stats | null;
  config: EngineConfig | null;
}) {
  const orchUp = health?.orchestrator?.reachable ?? false;
  return (
    <header className="flex items-center gap-3 border-b border-slate-800/80 bg-slate-950/80 px-4 py-2.5 backdrop-blur">
      <div className="flex items-center gap-2.5">
        <span className="glow-cyan rounded-xl bg-gradient-to-br from-cyan-400/20 to-violet-500/20 p-2">
          <Hexagon size={17} className="text-cyan-300" />
        </span>
        <div className="leading-tight">
          <h1 className="text-[15px] font-bold tracking-tight text-slate-100">
            {config?.app_name ?? "Aetheris Core"}
          </h1>
          <p className="text-[10px] tracking-[0.18em] text-slate-500 uppercase">
            autonomous graphrag mesh
          </p>
        </div>
      </div>

      <div className="ml-2 hidden items-center gap-1.5 xl:flex">
        <Pill
          icon={Radio}
          label="gateway"
          value={health?.status === "ok" ? "online" : "down"}
          tone={health?.status === "ok" ? "emerald" : "rose"}
        />
        <Pill
          icon={Cpu}
          label="orchestrator"
          value={orchUp ? `v${health?.orchestrator?.version ?? "?"}` : "down"}
          tone={orchUp ? "emerald" : "rose"}
        />
        <Pill
          icon={ShieldCheck}
          label="llm"
          value={config ? `${config.llm_provider}` : "…"}
          tone={config?.llm_enabled ? "violet" : "amber"}
        />
        <Pill
          icon={Gauge}
          label="embed"
          value={config ? config.embedding_model : "…"}
          tone="cyan"
        />
        <Pill
          icon={Database}
          label="vector"
          value={stats?.vector.backend ?? config?.vector_backend ?? "…"}
          tone={stats?.vector.backend === "supabase" ? "emerald" : "slate"}
        />
        <Pill
          icon={Hexagon}
          label="graph"
          value={stats?.graph.backend ?? config?.graph_backend ?? "…"}
          tone={stats?.graph.backend === "neo4j" ? "emerald" : "slate"}
        />
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <Badge tone="cyan">docs {stats?.meta.documents ?? "—"}</Badge>
        <Badge tone="slate">chunks {stats?.meta.chunks ?? "—"}</Badge>
        <Badge tone="violet">entities {stats?.meta.entities ?? "—"}</Badge>
        <Badge tone="amber">edges {stats?.graph.edges ?? "—"}</Badge>
        <Badge tone="emerald">communities {stats?.meta.communities ?? "—"}</Badge>
      </div>
    </header>
  );
}
