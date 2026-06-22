"use client";

import { useEffect, useRef, useState } from "react";
import { CheckSquare, Plus, X, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Task } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Constants ─────────────────────────────────────────────────────────────────

type Column = "pending" | "in_progress" | "review" | "done";
const COLUMNS: { key: Column; label: string; color: string; bg: string }[] = [
  { key: "pending",     label: "Pending",     color: "text-slate-400",   bg: "bg-slate-800/60"   },
  { key: "in_progress", label: "In Progress", color: "text-blue-400",    bg: "bg-blue-900/20"    },
  { key: "review",      label: "Review",      color: "text-amber-400",   bg: "bg-amber-900/20"   },
  { key: "done",        label: "Done",        color: "text-emerald-400", bg: "bg-emerald-900/20" },
];

const PRIORITY_LABEL: Record<number, string> = { 1: "Critical", 2: "High", 3: "Medium", 4: "Low" };
const PRIORITY_COLOR: Record<number, string> = {
  1: "text-red-400", 2: "text-orange-400", 3: "text-amber-400", 4: "text-slate-500",
};
const PRIORITY_DOT: Record<number, string> = {
  1: "bg-red-500", 2: "bg-orange-500", 3: "bg-amber-400", 4: "bg-slate-600",
};

// ── Task Card ─────────────────────────────────────────────────────────────────

function TaskCard({
  task,
  onDragStart,
  onDragEnd,
}: {
  task: Task;
  onDragStart: (e: React.DragEvent, task: Task) => void;
  onDragEnd: () => void;
}) {
  return (
    <div
      draggable
      onDragStart={e => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      className="group cursor-grab active:cursor-grabbing rounded-lg border border-slate-800
                 bg-slate-950 p-3 hover:border-slate-700 transition-colors select-none"
    >
      <div className="flex items-start gap-2">
        <span className={cn("mt-0.5 h-2 w-2 rounded-full shrink-0", PRIORITY_DOT[task.priority] ?? "bg-slate-600")} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 leading-snug">{task.title}</p>
          {task.description && (
            <p className="mt-1 text-xs text-slate-500 line-clamp-2">{task.description}</p>
          )}
        </div>
      </div>

      <div className="mt-2.5 flex items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1">
          {(task.tags ?? []).slice(0, 3).map(t => (
            <span key={t} className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">{t}</span>
          ))}
        </div>
        <span className={cn("text-[10px] font-medium shrink-0", PRIORITY_COLOR[task.priority])}>
          {PRIORITY_LABEL[task.priority] ?? "—"}
        </span>
      </div>

      {task.assigned_to_name && (
        <div className="mt-2 pt-2 border-t border-slate-800/60 text-[11px] text-slate-600">
          → {task.assigned_to_name}
        </div>
      )}
    </div>
  );
}

// ── New Task Modal ────────────────────────────────────────────────────────────

function NewTaskModal({ onClose, onCreate }: {
  onClose: () => void;
  onCreate: (task: Partial<Task>) => Promise<void>;
}) {
  const [title, setTitle]       = useState("");
  const [desc, setDesc]         = useState("");
  const [priority, setPriority] = useState(3);
  const [tags, setTags]         = useState("");
  const [saving, setSaving]     = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      await onCreate({
        title: title.trim(),
        description: desc.trim(),
        priority,
        tags: tags ? tags.split(",").map(t => t.trim()).filter(Boolean) : [],
        status: "pending",
      });
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <form onSubmit={submit}
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 space-y-4 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">New Task</h2>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 font-medium">Title</label>
            <input value={title} onChange={e => setTitle(e.target.value)} required
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2
                         text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-violet-600"
              placeholder="Task title…" />
          </div>
          <div>
            <label className="text-xs text-slate-400 font-medium">Description</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3}
              className="mt-1 w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2
                         text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-violet-600"
              placeholder="Optional description…" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 font-medium">Priority</label>
              <select value={priority} onChange={e => setPriority(Number(e.target.value))}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2
                           text-sm text-slate-100 focus:outline-none focus:border-violet-600">
                <option value={1}>1 — Critical</option>
                <option value={2}>2 — High</option>
                <option value={3}>3 — Medium</option>
                <option value={4}>4 — Low</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 font-medium">Tags (comma-separated)</label>
              <input value={tags} onChange={e => setTags(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2
                           text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-violet-600"
                placeholder="ml, research, …" />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-300 hover:text-white">
            Cancel
          </button>
          <button type="submit" disabled={saving || !title.trim()}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white
                       hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed">
            {saving ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TasksPage() {
  const [tasks, setTasks]       = useState<Task[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [showModal, setModal]   = useState(false);
  const [dragging, setDragging] = useState<Task | null>(null);
  const [overCol, setOverCol]   = useState<Column | null>(null);

  useEffect(() => {
    api.tasks.list()
      .then(setTasks)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  function onDragStart(e: React.DragEvent, task: Task) {
    setDragging(task);
    e.dataTransfer.effectAllowed = "move";
  }

  function onDrop(col: Column) {
    if (!dragging || dragging.status === col) { setDragging(null); setOverCol(null); return; }
    const prev = [...tasks];
    setTasks(tasks.map(t => t.id === dragging.id ? { ...t, status: col } : t));
    api.tasks.updateStatus(dragging.id, col)
      .catch(() => { setTasks(prev); setError("Failed to update task status"); });
    setDragging(null);
    setOverCol(null);
  }

  async function onCreate(body: Partial<Task>) {
    const created = await api.tasks.create(body);
    const newTask: Task = {
      id:               created.id,
      workspace_id:     "",
      title:            body.title ?? "",
      description:      body.description ?? "",
      created_by:       "",
      created_by_name:  "",
      assigned_to:      null,
      assigned_to_name: null,
      status:           "pending",
      priority:         body.priority ?? 3,
      tags:             body.tags ?? [],
      notes:            "",
      created_at:       new Date().toISOString(),
      updated_at:       new Date().toISOString(),
      completed_at:     null,
    };
    setTasks(prev => [...prev, newTask]);
  }

  const byCol = (col: Column) => tasks.filter(t => t.status === col);

  return (
    <div className="flex flex-col gap-5 h-full">
      <div className="flex items-center justify-between border-b border-slate-800 pb-4 shrink-0">
        <div className="flex items-center gap-3">
          <CheckSquare className="h-6 w-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Tasks</h1>
            <p className="text-sm text-slate-500">{tasks.length} total · drag to reorder</p>
          </div>
        </div>
        <button onClick={() => setModal(true)}
          className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-sm
                     font-medium text-white hover:bg-violet-500 transition-colors">
          <Plus className="h-4 w-4" /> New Task
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400 shrink-0">
          <AlertCircle className="h-4 w-4 shrink-0" /> {error}
        </div>
      )}

      {/* Kanban columns */}
      <div className="flex gap-4 flex-1 overflow-x-auto pb-4 min-h-0">
        {COLUMNS.map(col => (
          <div key={col.key}
            className={cn(
              "flex flex-col gap-2 rounded-xl border p-3 min-w-[240px] flex-1 transition-colors duration-150",
              overCol === col.key
                ? "border-violet-600/60 bg-violet-900/10"
                : "border-slate-800 bg-slate-900/40"
            )}
            onDragOver={e => { e.preventDefault(); setOverCol(col.key); }}
            onDragLeave={() => setOverCol(null)}
            onDrop={() => onDrop(col.key)}
          >
            <div className="flex items-center justify-between px-1 pb-1 border-b border-slate-800">
              <span className={cn("text-xs font-semibold uppercase tracking-wider", col.color)}>
                {col.label}
              </span>
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-500 tabular-nums">
                {loading ? "—" : byCol(col.key).length}
              </span>
            </div>

            <div className="flex flex-col gap-2 overflow-y-auto flex-1 pr-0.5">
              {loading
                ? [...Array(2)].map((_, i) => (
                  <div key={i} className="h-20 animate-pulse rounded-lg border border-slate-800 bg-slate-900" />
                ))
                : byCol(col.key).map(task => (
                  <TaskCard key={task.id} task={task}
                    onDragStart={onDragStart} onDragEnd={() => setDragging(null)} />
                ))
              }
              {!loading && byCol(col.key).length === 0 && (
                <div className="flex-1 flex items-center justify-center py-8 text-xs text-slate-700">
                  Drop here
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {showModal && <NewTaskModal onClose={() => setModal(false)} onCreate={onCreate} />}
    </div>
  );
}
