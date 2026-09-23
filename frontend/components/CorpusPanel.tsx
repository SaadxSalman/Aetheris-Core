"use client";
/* Corpus manager: document list + ingest form + reset. */
import { DatabaseZap, FileUp, Layers, Trash2 } from "lucide-react";
import { useState } from "react";
import { apiDelete, apiPost } from "@/lib/api";
import type { CorpusDoc } from "@/lib/types";
import { Badge, Button, Card } from "./ui";

export default function CorpusPanel({
  docs,
  onChanged,
}: {
  docs: CorpusDoc[];
  onChanged: () => void;
}) {
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("manual");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const ingest = async () => {
    if (!title.trim() || !text.trim() || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      const report = await apiPost<{ chunks: number; entities: number; communities: number }>(
        "/api/ingest",
        { title: title.trim(), text, source, uri: null },
      );
      setMsg({
        ok: true,
        text: `Ingested ${report.chunks} chunks · ${report.entities} entities · ${report.communities} communities`,
      });
      setTitle("");
      setText("");
      onChanged();
    } catch (e: any) {
      setMsg({ ok: false, text: String(e?.message ?? e) });
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!confirm("Wipe the entire corpus (documents, vectors, graph, communities)?")) return;
    setBusy(true);
    try {
      await apiDelete("/api/corpus");
      setMsg({ ok: true, text: "Corpus wiped." });
      onChanged();
    } catch (e: any) {
      setMsg({ ok: false, text: String(e?.message ?? e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="Corpus Manager"
      icon={DatabaseZap}
      actions={
        <Button variant="danger" onClick={reset} disabled={busy} title="Wipe corpus">
          <span className="flex items-center gap-1">
            <Trash2 size={11} /> reset
          </span>
        </Button>
      }
      bodyClassName="p-2 space-y-3"
    >
      <div className="space-y-1.5">
        <div className="flex gap-1.5">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Document title"
            className="min-w-0 flex-1 rounded-lg border border-slate-700/70 bg-slate-950/80 px-2 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/60 focus:outline-none"
          />
          <input
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="source"
            className="w-24 rounded-lg border border-slate-700/70 bg-slate-950/80 px-2 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/60 focus:outline-none"
          />
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder={"Paste Markdown/text…\n\n# Heading\nContent gets breadcrumb-injected before embedding."}
          className="w-full resize-none rounded-lg border border-slate-700/70 bg-slate-950/80 p-2 text-xs leading-relaxed text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/60 focus:outline-none"
        />
        <Button onClick={ingest} disabled={busy || !title.trim() || !text.trim()} className="w-full">
          <span className="flex items-center justify-center gap-1.5">
            <FileUp size={12} /> {busy ? "ingesting…" : "ingest → chunk → embed → graph"}
          </span>
        </Button>
        {msg && (
          <p className={msg.ok ? "text-[11px] text-emerald-400" : "text-[11px] text-rose-400"}>
            {msg.text}
          </p>
        )}
      </div>

      <div className="border-t border-slate-800 pt-2">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <Layers size={11} /> documents · {docs.length}
          </span>
        </div>
        <ul className="space-y-1">
          {docs.map((d) => (
            <li
              key={d.id}
              className="rounded-lg border border-slate-700/40 bg-slate-900/40 px-2 py-1.5"
              title={d.uri ?? d.id}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11.5px] font-medium text-slate-200">
                  {d.title}
                </span>
                <Badge tone="cyan">{d.chunk_count} chunks</Badge>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[9.5px] text-slate-600">
                <span>{d.source}</span>
                <span className="font-mono">{String(d.sha256).slice(0, 10)}…</span>
              </div>
            </li>
          ))}
          {docs.length === 0 && (
            <li className="p-3 text-center text-[11px] text-slate-600">Corpus is empty.</li>
          )}
        </ul>
      </div>
    </Card>
  );
}
