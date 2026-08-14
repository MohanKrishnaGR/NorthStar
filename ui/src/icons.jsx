import React from "react";

// Inline SVG source icons — self-contained (no CDN), theme-aware via
// currentColor. Brand marks for the two platforms, typed file badges for
// the file formats.

export function GitHubIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor"
         aria-label="GitHub" role="img">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>
    </svg>
  );
}

export function LinkedInIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor"
         aria-label="LinkedIn" role="img">
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.07 2.07 0 1 1 0-4.13 2.07 2.07 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.55C0 23.22.79 24 1.77 24h20.45c.98 0 1.78-.78 1.78-1.73V1.72C24 .77 23.2 0 22.22 0z"/>
    </svg>
  );
}

/** Generic document glyph with a small format label (CSV, JSON, TXT, …). */
export function FileBadgeIcon({ label, size = 18 }) {
  return (
    <svg width={size} height={size * 1.15} viewBox="0 0 20 23"
         aria-label={`${label} file`} role="img">
      <path d="M3 1h9l5 5v15a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 2 21V2.5A1.5 1.5 0 0 1 3.5 1z"
            fill="none" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M12 1v5h5" fill="none" stroke="currentColor" strokeWidth="1.4"/>
      <text x="10" y="18" textAnchor="middle" fontSize="6.2" fontWeight="700"
            fontFamily="inherit" fill="currentColor">{label}</text>
    </svg>
  );
}

/** Icon for a source_type (dock tabs) or a hints-row kind. */
export function SourceIcon({ kind, size = 18 }) {
  switch (kind) {
    case "github_json": case "github": return <GitHubIcon size={size} />;
    case "linkedin_json": case "linkedin": return <LinkedInIcon size={size} />;
    case "recruiter_csv": case "csv": return <FileBadgeIcon label="CSV" size={size} />;
    case "ats_json": case "json": return <FileBadgeIcon label="JSON" size={size} />;
    case "notes_txt": case "txt": return <FileBadgeIcon label="TXT" size={size} />;
    case "resume": return <FileBadgeIcon label="PDF" size={size} />;
    case "derived": return <FileBadgeIcon label="ƒ" size={size} />;
    default: return <FileBadgeIcon label="?" size={size} />;
  }
}
