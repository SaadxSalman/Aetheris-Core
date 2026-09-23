"use client";
/* Small shadcn-flavored primitives used across the workspace. */
import clsx from "clsx";
import { type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

export function Badge({
  children,
  tone = "slate",
  className,
}: {
  children: React.ReactNode;
  tone?: "slate" | "cyan" | "emerald" | "amber" | "rose" | "violet";
  className?: string;
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-500/10 text-slate-300 border-slate-500/30",
    cyan: "bg-cyan-500/10 text-cyan-300 border-cyan-500/30",
    emerald: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    amber: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    rose: "bg-rose-500/10 text-rose-300 border-rose-500/30",
    violet: "bg-violet-500/10 text-violet-300 border-violet-500/30",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Card({
  title,
  icon: Icon,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  icon?: LucideIcon;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("panel flex flex-col min-h-0", className)}>
      {title && (
        <header className="flex items-center justify-between gap-2 border-b border-slate-700/40 px-3 py-2">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            {Icon && <Icon size={13} className="text-cyan-400" />}
            {title}
          </h2>
          <div className="flex items-center gap-1.5">{actions}</div>
        </header>
      )}
      <div className={clsx("min-h-0 flex-1 overflow-auto", bodyClassName)}>
        {children}
      </div>
    </section>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  className,
  type = "button",
  title,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "danger";
  className?: string;
  type?: "button" | "submit";
  title?: string;
}) {
  const styles: Record<string, string> = {
    primary:
      "bg-gradient-to-r from-cyan-500 to-violet-600 text-white hover:from-cyan-400 hover:to-violet-500 shadow-lg shadow-cyan-500/20",
    ghost:
      "bg-slate-800/60 text-slate-300 border border-slate-700/60 hover:bg-slate-700/60",
    danger: "bg-rose-600/80 text-white hover:bg-rose-500",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40",
        styles[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-1 rounded-lg bg-slate-900/70 p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={clsx(
            "rounded-md px-2.5 py-1 text-[11px] font-medium transition",
            active === t.id
              ? "bg-slate-700/80 text-cyan-300 shadow"
              : "text-slate-400 hover:text-slate-200",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function StatusDot({ status }: { status: string }) {
  const color =
    status === "running"
      ? "bg-cyan-400 blink"
      : status === "success"
        ? "bg-emerald-400"
        : status === "failed"
          ? "bg-rose-400"
          : "bg-slate-600";
  return <span className={clsx("inline-block h-2 w-2 rounded-full", color)} />;
}

/** Live "elapsed since t0" ticker. */
export function useTicker(active: boolean) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((t) => t + 1), 100);
    return () => clearInterval(id);
  }, [active]);
}
