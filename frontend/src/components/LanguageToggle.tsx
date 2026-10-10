import { LANGS, useI18n } from '../i18n';

/* Two short labels side by side rather than a menu: with only English and
   German there is nothing to open, and the current choice stays visible. */
export function LanguageToggle() {
  const { lang, setLang, t } = useI18n();
  return (
    <div role="group" aria-label={t.langSwitch} className="flex items-center h-9 p-0.5 rounded-lg border border-[var(--border)]">
      {LANGS.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => setLang(option.id)}
          aria-pressed={lang === option.id}
          title={option.name}
          lang={option.id}
          className={`h-full px-2 rounded-md font-mono text-[11.5px] font-medium transition-colors cursor-pointer ${
            lang === option.id
              ? 'bg-[var(--bg-inset)] text-[var(--text)]'
              : 'text-[var(--text-muted)] hover:text-[var(--text)]'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
