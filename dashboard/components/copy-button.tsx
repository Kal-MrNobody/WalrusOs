"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface CopyButtonProps {
  text: string;
  className?: string;
}

export function CopyButton({ text, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={copy}
      className={cn(
        "inline-flex items-center justify-center rounded p-0.5 transition-colors",
        copied
          ? "text-emerald-400"
          : "text-slate-500 hover:text-slate-300",
        className
      )}
      title="Copy to clipboard"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

export function TruncatedId({
  value,
  chars = 8,
  className,
}: {
  value: string;
  chars?: number;
  className?: string;
}) {
  if (!value) return <span className={cn("text-slate-600", className)}>—</span>;
  const display = value.length > chars + 3
    ? `${value.slice(0, chars)}…`
    : value;
  return (
    <span className={cn("inline-flex items-center gap-1 font-mono text-xs", className)}>
      <span title={value}>{display}</span>
      <CopyButton text={value} />
    </span>
  );
}
