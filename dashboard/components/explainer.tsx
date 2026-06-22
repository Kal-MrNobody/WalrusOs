import { Info } from "lucide-react";

interface ExplainerProps {
  title: string;
  children: React.ReactNode;
}

export function Explainer({ title, children }: ExplainerProps) {
  return (
    <div className="mb-6 rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-4 text-indigo-200">
      <div className="flex items-center gap-2 font-semibold text-indigo-300 mb-2">
        <Info className="h-5 w-5" />
        {title}
      </div>
      <div className="text-sm leading-relaxed text-indigo-200/90">
        {children}
      </div>
    </div>
  );
}
