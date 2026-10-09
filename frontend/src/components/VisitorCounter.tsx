import React, { useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import { getVisitorCount } from '../api/client';

export const VisitorCounter: React.FC = () => {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    getVisitorCount().then((data) => setCount(data.unique_visitors)).catch(() => setCount(null));
  }, []);

  // Nothing to show if the fetch failed or hasn't resolved yet.
  if (count === null) return null;

  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[11px] text-[var(--text-muted)]"
      title="Unique visitors since launch"
    >
      <Users className="w-3.5 h-3.5" />
      {count.toLocaleString()}
    </span>
  );
};
