import React from 'react';

interface BrandMarkProps {
  size?: number;
  className?: string;
}

/* A flat, square mark in university blue: an institutional service icon,
   not a product logo. Sigma because it stays legible at small sizes and is
   the one symbol every course in a statistics-heavy programme shares. */
export const BrandMark: React.FC<BrandMarkProps> = ({ size = 32, className = '' }) => (
  <div
    className={`shrink-0 rounded-md bg-accent-800 dark:bg-accent-600 text-white flex items-center justify-center ${className}`}
    style={{ width: size, height: size }}
    aria-hidden="true"
  >
    <span className="font-semibold leading-none" style={{ fontSize: size * 0.55 }}>
      Σ
    </span>
  </div>
);
