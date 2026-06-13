// Build Markdown / HTML day-card exports from the shared display model, so the
// copied/downloaded text matches the on-screen cards exactly (same sections,
// same units). Pretty JSON comes straight from the raw data.

import type { DayCardView } from "./dayCardModel";
import type { DayCardData } from "./types";

export function buildMarkdown(views: DayCardView[]): string {
  const out: string[] = [];
  for (const v of views) {
    out.push(`## ${v.title}`);
    if (v.date) out.push(`* ${v.date}`);
    out.push(`* ${v.stats}`);
    for (const line of v.lines) out.push(`* ${line.text}`);
    if (v.hint) out.push(`* _${v.hint}_`);
    if (v.warnings.length) {
      out.push("");
      out.push("### Warnings");
      for (const w of v.warnings) out.push(`- ${w.level === "warning" ? "⚠" : "·"} ${w.message}`);
    }
    if (v.attributions.length) {
      out.push("");
      out.push(`*Sources: ${v.attributions.join("; ")}*`);
    }
    out.push("");
  }
  return out.join("\n").trimEnd() + "\n";
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function buildHtml(views: DayCardView[]): string {
  const body: string[] = [];
  for (const v of views) {
    body.push('<section class="daycard">');
    body.push(`<h2>${esc(v.title)}${v.date ? ` <span class="date">${esc(v.date)}</span>` : ""}</h2>`);
    body.push(`<p class="stats">${esc(v.stats)}</p>`);
    if (v.lines.length) {
      body.push("<ul>");
      for (const line of v.lines) body.push(`<li>${esc(line.icon)} ${esc(line.text)}</li>`);
      body.push("</ul>");
    }
    if (v.hint) body.push(`<p class="hint">${esc(v.hint)}</p>`);
    if (v.warnings.length) {
      body.push("<h3>Warnings</h3><ul>");
      for (const w of v.warnings) {
        body.push(`<li>${w.level === "warning" ? "⚠" : "·"} ${esc(w.message)}</li>`);
      }
      body.push("</ul>");
    }
    if (v.attributions.length) {
      body.push(`<p class="sources">Sources: ${esc(v.attributions.join("; "))}</p>`);
    }
    body.push("</section>");
  }
  const title = views[0]?.title ?? "Day cards";
  const css =
    "body{font-family:system-ui,sans-serif;color:#1e293b;max-width:48rem;margin:2rem auto;padding:0 1rem}" +
    "section.daycard{border:1px solid #e2e8f0;border-radius:.75rem;padding:1rem;margin-bottom:1rem}" +
    "h2{font-size:1.1rem;margin:0 0 .25rem}.date{color:#94a3b8;font-weight:400;font-size:.9rem}" +
    ".stats{color:#475569;margin:.25rem 0}ul{margin:.5rem 0;padding-left:1.25rem}li{margin:.15rem 0}" +
    ".hint{color:#94a3b8;font-style:italic}.sources{color:#94a3b8;font-size:.75rem;margin-top:.5rem}";
  return `<!doctype html>\n<html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${css}</style></head>\n<body>\n${body.join("\n")}\n</body></html>\n`;
}

export function buildJson(data: DayCardData[]): string {
  return JSON.stringify(data, null, 2);
}
