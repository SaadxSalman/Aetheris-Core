"use client";
/* Query composer + streamed answer + citation attestation panel. */
import {
  BadgeCheck,
  FileText,
  Globe,
  Link2,
  Play,
  Square,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import type { AnswerMeta, Citation, GradeInfo, GroundingInfo } from "@/lib/types";
import { apiPost } from "@/lib/api";
import { Badge, Button, Card } from "./ui";

function Inline({ text }: { text: string }) {
  const parts = text.split(/(\[\d{1,2}\])/g);
  return (
    <>
      {parts.map((p, i) =>
        /^\[\d{1,2}\]$/.test(p) ? (
          <sup
            key={i}
            className="mx-0.5 rounded border border-cyan-500/40 bg-cyan-500/15 px-1 text-[9px] font-bold text-cyan-300"
          >
            {p}
          </sup>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

function AnswerBody({ text, streaming }: { text: string; streaming: boolean }) {
  const lines = text.split("\n");
  return (
    <div className={streaming ? "caret whitespace-pre-wrap" : "whitespace-pre-wrap"}>
      {lines.map((line, i) => {
        const bullet = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
        if (bullet) {
          return (
            <div key={i} className="flex gap-2 pl-1">
              <span className="shrink-0 select-none text-cyan-400">{bullet[2]}</span>
              <span>
                <Inline text={bullet[3]} />
              </span>
            </div>
          );
        }
        if (!line.trim()) return <div key={i} className="h-2" />;
        return (
          <p key={i} className="text-[13px] leading-relaxed text-slate-200">
            <Inline text={line} />
          </p>
        );
      })}
    </div>
  );
}

function CitationRow({ c }: { c: Citation }) {
  const [state, setState] = useState<"idle" | "checking" | "valid" | "invalid">("idle");
  const verify = async () => {
    setState("checking");
    try {
      const res = await apiPost<{ valid: boolean }>("/api/verify-citation", {
        chunk_id: c.chunk_id,
        content_sha256: c.content_sha256,
        request_id: c.request_id,
        attestation: c.attestation,
      });
      setState(res.valid ? "valid" : "invalid");
    } catch {
      setState("invalid");
    }
  };
  return (
    <li className="rounded-lg border border-slate-700/50 bg-slate-900/50 p-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-bold text-cyan-300">
              {c.index}
            </span>
            <span className="truncate text-xs font-medium text-slate-200">{c.title}</span>
          </div>
          {c.header_path && (
            <div className="mt-0.5 truncate text-[10px] text-slate-500" title={c.header_path}>
              {c.header_path}
            </div>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge tone={c.source === "web" ? "amber" : c.source === "community" ? "violet" : "slate"}>
              {c.source === "web" ? <Globe size={9} /> : <FileText size={9} />}
              {c.source}
            </Badge>
            <span className="font-mono text-[9px] text-slate-600">
              {c.content_sha256.slice(0, 12)}…
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={verify}
            className="flex items-center gap-1 rounded-md border border-slate-700 bg-slate-800/70 px-2 py-1 text-[10px] font-semibold text-slate-300 transition hover:border-cyan-500/50 hover:text-cyan-300"
            title="Verify HMAC attestation"
          >
            <BadgeCheck size={11} />
            {state === "idle" && "verify"}
            {state === "checking" && "…"}
            {state === "valid" && <span className="text-emerald-400">valid ✓</span>}
            {state === "invalid" && <span className="text-rose-400">invalid ✗</span>}
          </button>
          {c.uri && (
            <a
              href={c.uri}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-cyan-300"
            >
              <Link2 size={10} /> source
            </a>
          )}
        </div>
      </div>
      {c.snippet && (
        <p className="mt-1.5 line-clamp-2 text-[10.5px] leading-snug text-slate-500">
          {c.snippet}
        </p>
      )}
    </li>
  );
}

interface Props {
  running: boolean;
  answer: string;
  citations: Citation[];
  meta: AnswerMeta | null;
  grade: GradeInfo | null;
  grounding: GroundingInfo | null;
  audit: { support_ratio?: number; sentences?: number; supported?: number; passed?: boolean } | null;
  error: string | null;
  lastMs: number | null;
  onRun: (q: string, mode: string) => void;
  onStop: () => void;
}

export default function ChatPanel({
  running, answer, citations, meta, grade, grounding, audit, error, lastMs,
  onRun, onStop,
}: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("auto");

  const submit = () => {
    if (!query.trim() || running) return;
    onRun(query.trim(), mode);
  };

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <Card title="Query Composer" icon={Link2} bodyClassName="p-3 space-y-2.5">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          }}
          rows={3}
          placeholder="Ask the knowledge mesh…  (⌘/Ctrl+Enter to run)"
          className="w-full resize-none rounded-lg border border-slate-700/70 bg-slate-950/80 p-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/60 focus:outline-none"
        />
        <div className="flex items-center gap-2">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="rounded-lg border border-slate-700/70 bg-slate-950/80 px-2 py-1.5 text-xs text-slate-300 focus:outline-none"
            title="GraphRAG search mode"
          >
            <option value="auto">mode · auto</option>
            <option value="local">mode · local (entities)</option>
            <option value="global">mode · global (communities)</option>
          </select>
          {running ? (
            <Button variant="danger" onClick={onStop} className="ml-auto">
              <span className="flex items-center gap-1.5">
                <Square size={11} /> stop
              </span>
            </Button>
          ) : (
            <Button onClick={submit} disabled={!query.trim()} className="ml-auto">
              <span className="flex items-center gap-1.5">
                <Play size={11} /> run graph
              </span>
            </Button>
          )}
        </div>
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-[11px] text-rose-300">
            <TriangleAlert size={13} className="mt-0.5 shrink-0" />
            <span className="break-all">{error}</span>
          </div>
        )}
      </Card>

      <Card
        title="Answer"
        icon={FileText}
        className="min-h-[200px] flex-1"
        bodyClassName="p-3"
        actions={
          <>
            {lastMs !== null && <Badge tone="slate">{Math.round(lastMs)} ms</Badge>}
            {meta && (
              <Badge tone={meta.degraded ? "amber" : "emerald"}>
                {meta.degraded ? "degraded" : "grounded"}
              </Badge>
            )}
          </>
        }
      >
        {!answer && !running && (
          <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 text-center text-slate-600">
            <BadgeCheck size={22} />
            <p className="text-[11px] leading-relaxed">
              The canvas lights up as agents execute.
              <br />
              Ask a question to start the orchestration graph.
            </p>
          </div>
        )}
        {answer && <AnswerBody text={answer} streaming={running} />}
        {meta && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-800 pt-2">
            <Badge tone="cyan">route · {meta.route}</Badge>
            <Badge tone="violet">llm · {meta.provider}</Badge>
            {typeof meta.confidence === "number" && (
              <Badge tone={grade?.passed ? "emerald" : "rose"}>
                confidence · {meta.confidence.toFixed(2)}
              </Badge>
            )}
            {typeof meta.grounding_score === "number" && (
              <Badge tone="emerald">grounding · {meta.grounding_score.toFixed(2)}</Badge>
            )}
            {typeof audit?.support_ratio === "number" && (
              <Badge tone={audit.passed ? "emerald" : "amber"}>
                audit · {((audit.support_ratio ?? 0) * 100).toFixed(0)}% supported
              </Badge>
            )}
            {meta.web_used && <Badge tone="amber">web fallback</Badge>}
            {meta.reformulations > 0 && (
              <Badge tone="amber">{meta.reformulations} rewrite(s)</Badge>
            )}
          </div>
        )}
        {grounding && !grounding.passed && (
          <div className="mt-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-200">
            Grounding {grounding.score.toFixed(2)} &lt; {grounding.threshold} — unsupported:{" "}
            {grounding.aspects.filter((a) => !a.supported).map((a) => a.aspect).join(", ") || "—"}
          </div>
        )}
      </Card>

      <Card
        title={`Citations · ${citations.length}`}
        icon={BadgeCheck}
        className="max-h-[32vh] shrink-0"
        bodyClassName="p-2"
      >
        {citations.length === 0 ? (
          <p className="p-3 text-[11px] text-slate-600">
            No citations yet — every answer ships with HMAC-attested source chunks.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {citations.map((c) => (
              <CitationRow key={`${c.index}-${c.chunk_id}`} c={c} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

