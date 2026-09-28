import React, { useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import { getVisitorCount } from '../api/client';

export const VisitorCounter: React.FC = () => {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    getVisitorCount().then((data) => setCount(data.unique_visitors)).catch(() => setCount(null));
  }, []);

  // Nothing to show if the fetch failed or hasn't resolved yet - same
  // reasoning as VersionBadge: no corner tag reading "null visitors".
  if (count === null) return null;

  return (
    <div
      className="fixed bottom-3 left-3 z-40 flex items-center gap-1 px-2.5 py-1 rounded-full glass-well text-[10px] font-mono font-bold text-[var(--text-muted)] border border-[var(--border)] shadow-sm"
      title="Unique visitors since launch"
    >
      <Users className="w-3 h-3" />
      <span>{count.toLocaleString()}</span>
    </div>
  );
};
