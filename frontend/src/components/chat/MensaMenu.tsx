import React, { useState } from 'react';
import { ChevronDown, ExternalLink, Info, UtensilsCrossed } from 'lucide-react';
import { MensaMeal, MensaMenu as Menu, MensaPayload } from '../../types';
import { mensaImageUrl } from '../../api/client';
import { useI18n } from '../../i18n';

/* The canteen meals an answer was written from, as the Studierendenwerk
   publishes them: photo, prices, diet pictograms, allergens and additives.
   Nothing here comes from the answer model. */

const chip =
  'inline-flex items-center gap-1 h-6 px-2 rounded text-[11px] leading-none border whitespace-nowrap';

const Pictograms: React.FC<{ meal: MensaMeal; size?: 'sm' | 'md' }> = ({ meal, size = 'md' }) => (
  <span className="inline-flex items-center gap-1">
    {meal.pictogram_labels.map((p) => (
      <img
        key={p.code}
        src={mensaImageUrl(p.icon)}
        alt={p.label}
        title={p.label}
        loading="lazy"
        className={size === 'sm' ? 'h-4 w-auto' : 'h-6 w-auto'}
      />
    ))}
  </span>
);

const Codes: React.FC<{ meal: MensaMeal }> = ({ meal }) => {
  const { t } = useI18n();
  const allergens = meal.labels.filter((l) => l.kind === 'allergen');
  const additives = meal.labels.filter((l) => l.kind === 'additive');
  const notes = meal.labels.filter((l) => l.kind === 'note');
  if (!allergens.length && !additives.length && !notes.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {allergens.map((l) => (
        <span
          key={l.code}
          title={`${t.mensaAllergens}: ${l.label}`}
          className={`${chip} bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-500/10 dark:border-rose-500/30 dark:text-rose-300`}
        >
          {l.label}
        </span>
      ))}
      {additives.map((l) => (
        <span
          key={l.code}
          title={`${t.mensaAdditives}: ${l.label}`}
          className={`${chip} bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/30 dark:text-amber-300`}
        >
          ({l.code}) {l.label}
        </span>
      ))}
      {notes.map((l) => (
        <span key={l.code} className={`${chip} bg-[var(--bg-subtle)] border-[var(--border)] text-[var(--text-muted)]`}>
          {l.label}
        </span>
      ))}
    </div>
  );
};

const MealCard: React.FC<{ meal: MensaMeal }> = ({ meal }) => {
  const { t } = useI18n();
  const { students, employees, guests } = meal.prices;
  return (
    <article className="flex flex-col rounded-lg border border-[var(--border)] bg-[var(--bg)] overflow-hidden">
      {meal.image ? (
        <img
          src={mensaImageUrl(meal.image)}
          alt={meal.name}
          loading="lazy"
          className="w-full aspect-[4/3] object-cover bg-[var(--bg-subtle)]"
        />
      ) : (
        <div className="w-full aspect-[4/3] flex items-center justify-center bg-[var(--bg-subtle)] text-[var(--text-faint)]">
          <UtensilsCrossed className="w-8 h-8" aria-hidden />
        </div>
      )}
      <div className="flex flex-col flex-1 p-3">
        <div className="flex items-start justify-between gap-2">
          <h4 className="text-[14px] font-semibold leading-snug text-[var(--text)]">{meal.name}</h4>
          <Pictograms meal={meal} />
        </div>
        {meal.counter && (
          <p className="mt-0.5 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">{meal.counter}</p>
        )}
        <Codes meal={meal} />
        <div className="mt-auto pt-3">
          <p className="whitespace-nowrap">
            <span className="font-mono text-[16px] font-semibold text-[var(--text)] tabular-nums">
              {students ? `${students} €` : '-'}
            </span>
            <span className="ml-1.5 text-[11px] text-[var(--text-muted)]">{t.mensaPriceStudents}</span>
          </p>
          {employees && guests && (
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)] tabular-nums">{t.mensaPriceOthers(employees, guests)}</p>
          )}
        </div>
      </div>
    </article>
  );
};

const SideList: React.FC<{ meals: MensaMeal[] }> = ({ meals }) => {
  const { t } = useI18n();
  if (!meals.length) return null;
  return (
    <div className="mt-3">
      <h4 className="text-[12px] font-semibold text-[var(--text-secondary)] mb-1">{t.mensaSides}</h4>
      <ul className="divide-y divide-[var(--border)] border-y border-[var(--border)]">
        {meals.map((m, i) => (
          <li key={`${m.name}-${i}`} className="flex items-center justify-between gap-3 py-1.5 text-[13px]">
            <span className="flex items-center gap-2 min-w-0">
              <Pictograms meal={m} size="sm" />
              <span className="truncate text-[var(--text)]" title={m.labels.map((l) => l.label).join(', ')}>
                {m.name}
              </span>
            </span>
            <span className="font-mono text-[12px] text-[var(--text-muted)] tabular-nums shrink-0">
              {m.prices.students ? `${m.prices.students} €` : ''}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

const Legend: React.FC<{ menu: Menu }> = ({ menu }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const { codes, pictograms } = menu.legend;
  if (!codes.length && !pictograms.length) return null;
  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text)] cursor-pointer"
      >
        <Info className="w-3.5 h-3.5" aria-hidden />
        {t.mensaLegend}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      {open && (
        <dl className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
          {pictograms.map((p) => (
            <div key={p.code} className="flex items-center gap-2">
              <dt>
                <img src={mensaImageUrl(p.icon)} alt="" className="h-4 w-auto" />
              </dt>
              <dd className="text-[var(--text-secondary)]">{p.label}</dd>
            </div>
          ))}
          {codes.map((c) => (
            <div key={c.code} className="flex items-center gap-2">
              <dt className="font-mono text-[var(--text-muted)] w-8 shrink-0">({c.code})</dt>
              <dd className="text-[var(--text-secondary)]">{c.label}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
};

const OneMenu: React.FC<{ menu: Menu; filtered: boolean; allergyFilter: boolean }> = ({ menu, filtered, allergyFilter }) => {
  const { t, lang } = useI18n();
  const day = new Date(`${menu.date}T12:00:00`).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  const mains = menu.meals.filter((m) => !m.side);
  const sides = menu.meals.filter((m) => m.side);
  return (
    <section className="mt-1">
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
        <h3 className="text-[14px] font-semibold text-[var(--text)]">
          {menu.location} <span className="font-normal text-[var(--text-muted)]">· {day}</span>
        </h3>
        <a
          href={menu.official_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[12px] text-accent-700 dark:text-accent-300 hover:underline"
        >
          {t.mensaOfficial}
          <ExternalLink className="w-3 h-3" aria-hidden />
        </a>
      </header>
      {filtered && !menu.meals.length && <p className="text-[13px] text-[var(--text-muted)]">{t.mensaNoMatch}</p>}
      {mains.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {mains.map((m, i) => (
            <MealCard key={`${m.name}-${i}`} meal={m} />
          ))}
        </div>
      )}
      <SideList meals={sides} />
      {menu.notes.map((n) => (
        <p key={n} className="mt-2 text-[12px] text-[var(--text-muted)]">
          {n}
        </p>
      ))}
      {allergyFilter && <p className="mt-2 text-[12px] text-amber-800 dark:text-amber-300">{t.mensaAllergyHint}</p>}
      <Legend menu={menu} />
    </section>
  );
};

export const MensaMenuCards: React.FC<{ data: MensaPayload }> = ({ data }) => {
  const { t } = useI18n();
  const allergyFilter = data.wishes.some((w) => /^without /i.test(w));
  return (
    <div className="px-4 sm:px-5 pb-4 space-y-5">
      {data.wishes.length > 0 && (
        <p className="text-[12px] text-[var(--text-muted)]">
          {t.mensaFilteredFor}: {data.wishes.join(', ')}
        </p>
      )}
      {data.menus.map((menu) => (
        <OneMenu key={`${menu.location}-${menu.date}`} menu={menu} filtered={data.wishes.length > 0} allergyFilter={allergyFilter} />
      ))}
    </div>
  );
};
