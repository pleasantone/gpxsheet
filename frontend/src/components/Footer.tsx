// Site footer: links out to the project's GitHub repo, issue tracker, docs and
// PyPI package. Rendered at the bottom of every phase (sits below the flex-1
// <main>, so it stays pinned to the bottom on short pages).
const LINKS = [
  { label: "Docs", href: "https://gpxsheet.readthedocs.io", icon: DocsIcon },
  { label: "Issues", href: "https://github.com/pleasantone/gpxsheet/issues", icon: IssuesIcon },
  { label: "GitHub", href: "https://github.com/pleasantone/gpxsheet", icon: GitHubIcon },
  { label: "PyPI", href: "https://pypi.org/project/gpxsheet/", icon: PyPIIcon },
];

export function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white px-4 py-4">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-3 sm:flex-row sm:justify-between">
        <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
          {LINKS.map(({ label, href, icon: Icon }) => (
            <a
              key={label}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-brand"
            >
              <Icon className="h-4 w-4" />
              {label}
            </a>
          ))}
        </nav>
        <p className="text-xs text-slate-400">
          GPXSheet · open source under the AGPL-3.0 license
        </p>
      </div>
    </footer>
  );
}

type IconProps = { className?: string };

function GitHubIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className={className} fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

function IssuesIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className={className} fill="currentColor">
      <path d="M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" />
      <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0ZM1.5 8a6.5 6.5 0 1 1 13 0 6.5 6.5 0 0 1-13 0Z" />
    </svg>
  );
}

function DocsIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className={className} fill="currentColor">
      <path d="M0 1.75A.75.75 0 0 1 .75 1h4.253c1.227 0 2.317.59 3 1.501A3.743 3.743 0 0 1 11.006 1h4.245a.75.75 0 0 1 .75.75v10.5a.75.75 0 0 1-.75.75h-4.507a2.25 2.25 0 0 0-1.591.659l-.622.621a.75.75 0 0 1-1.06 0l-.622-.621A2.25 2.25 0 0 0 5.258 13H.75a.75.75 0 0 1-.75-.75Zm7.251 10.324.001-4.823-.027-2.034a2.25 2.25 0 0 0-2.25-2.241H1.5v9h3.758a3.75 3.75 0 0 1 1.993.574ZM8.755 4.75l-.001 7.322a3.75 3.75 0 0 1 1.992-.572H14.5v-9h-3.495a2.25 2.25 0 0 0-2.25 2.25Z" />
    </svg>
  );
}

function PyPIIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className={className} fill="currentColor">
      <path d="M2 2.75A.75.75 0 0 1 2.75 2h6.5a.75.75 0 0 1 .53.22l4 4c.141.14.22.331.22.53v6.5a.75.75 0 0 1-.75.75h-2v-1.5h1.25V7.5H9.25a.75.75 0 0 1-.75-.75V3.5h-5v2H2Zm8 1.31 1.69 1.69H10ZM2 7.75A.75.75 0 0 1 2.75 7h4.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-.75.75h-4.5a.75.75 0 0 1-.75-.75Zm1.5.75v4h3v-4Z" />
    </svg>
  );
}
