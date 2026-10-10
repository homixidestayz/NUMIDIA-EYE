import { useEffect, useMemo, useRef, useState } from "react";
import type { Detection, WilayaCollection } from "../types";
import { wilayaCode } from "../geo";

interface Props {
  wilayas: WilayaCollection | null;
  detections: Detection[];
  onClose: () => void;
  onPick: (code: string) => void;
}

interface Row {
  code: string;
  name: string;
  nameAr: string;
  count: number;
}

/** Fold accents, punctuation and the French article prefixes Algerian wilaya
 *  names carry, so "Bejaia", "bejaia", "Béjaïa" and "Wilaya of Bejaia" all land
 *  on the same row. A miss here reads as "this wilaya does not exist".
 *
 *  Explicit \u escapes: combining marks are invisible in source and an editor
 *  or encoding pass will happily mangle a literal range. */
function normalise(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/(^|\s)(wilaya|daïet|el|ait|ad)(\s|$)/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export default function SearchModal({ wilayas, detections, onClose, onPick }: Props) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const rows = useMemo<Row[]>(() => {
    const counts = new Map<string, number>();
    for (const d of detections) {
      if (d.wilaya_code == null) continue;
      counts.set(String(d.wilaya_code), (counts.get(String(d.wilaya_code)) ?? 0) + 1);
    }
    return (wilayas?.features ?? []).map((f) => {
      const code = wilayaCode(f);
      return {
        code,
        name: f.properties.shapeName,
        nameAr: f.properties.shapeNameAr,
        count: counts.get(code) ?? 0,
      };
    });
  }, [wilayas, detections]);

  const results = useMemo(() => {
    const raw = q.trim();
    const needle = normalise(raw);
    if (!needle) {
      return [...rows].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    }
    return rows
      .filter((r) => {
        // Normalise both sides. Matching a folded needle against an unfolded
        // name means "bejaia" never finds "Béjaïa".
        const name = normalise(r.name);
        // Codes are zero-padded ("09"), so accept "9" as well as "09".
        const codeHit = /^\d{1,2}$/.test(raw) && r.code === raw.padStart(2, "0");
        return codeHit || name === needle || name.includes(needle);
      })
      .sort((a, b) => {
        // Exact hits first, then wilayas with detections, then alphabetical.
        const ea = normalise(a.name) === needle ? 0 : 1;
        const eb = normalise(b.name) === needle ? 0 : 1;
        return ea - eb || b.count - a.count || a.name.localeCompare(b.name);
      })
      .slice(0, 50);
  }, [rows, q]);

  useEffect(() => {
    setActive(0);
  }, [q]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(".search-item.active");
    // jsdom has no scrollIntoView; guard rather than let a cosmetic scroll
    // become a crash that takes the whole modal down.
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [active]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      onPick(results[active].code);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-box" onClick={(e) => e.stopPropagation()} onKeyDown={onKey}>
        <div className="search-input">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.5" y2="16.5" />
          </svg>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Jump to a wilaya — try Blida, Timimoun or 9"
            aria-label="Search wilayas"
          />
          <span className="search-hint">esc</span>
        </div>

        <div className="search-results" ref={listRef}>
          {results.length === 0 ? (
            <div className="search-empty">
              No wilaya matches “{q}”. {rows.length} wilayas loaded.
            </div>
          ) : (
            results.map((r, i) => (
              <button
                key={r.code}
                type="button"
                className={`search-item ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => onPick(r.code)}
              >
                <span className="code">{r.code}</span>
                <span className="nm">{r.name}</span>
                {r.nameAr ? <span className="nm-ar" lang="ar" dir="rtl">{r.nameAr}</span> : null}
                <span className="ct">
                  {r.count > 0 ? `${r.count} det.` : "no detections"}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}