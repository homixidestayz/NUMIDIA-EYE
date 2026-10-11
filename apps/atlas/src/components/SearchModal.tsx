import { useEffect, useMemo, useRef, useState } from "react";
import type { Detection, WilayaCollection } from "../types";
import { wilayaCode } from "../geo";
import { useI18n } from "../i18n";

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
 *  Arabic has to survive the same pass. Wilaya names carry both
 *  (shapeName / shapeNameAr), and the Arabic placeholder advertises an Arabic
 *  search — so a query has to fold to something meaningful in either script.
 *  Dropping every non-[a-z0-9] character turned an Arabic query into an empty
 *  string, which silently fell through to "show all 69".
 *
 *  Explicit \u escapes: combining marks are invisible in source and an editor
 *  or encoding pass will happily mangle a literal range. */
export function normalise(s: string): string {
  const once = s
    .toLowerCase()
    .normalize("NFD")
    // Latin accents and Arabic tashkeel both live in the combining ranges.
    .replace(/[̀-ًͯ-ٰٟ]/g, "")
    // Letter variants a typist will not distinguish: أإآٱ → ا, ى → ي, ة → ه.
    .replace(/[آأإٱ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    // Article folding is Latin-only; it cannot affect an Arabic string.
    // Note "daiet" is already unfolded by the accent strip above, so the
    // pattern must be spelled without the diaeresis or it never matches.
    .replace(/(^|\s)(wilaya|daiet|of|el|ait|ad)(\s|$)/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
  /* Repeat the article pass. One pass stops after the first article, because
   * that match consumes the space the next one anchors on: "wilaya of bejaia"
   * would otherwise leave a stray "of" behind. */
  let out = once;
  for (let pass = 0; pass < 4; pass++) {
    const next = out.replace(/(^|\s)(wilaya|daiet|of|el|ait|ad)(\s|$)/g, " ");
    const squashed = next.replace(/\s+/g, " ").trim();
    if (squashed === out) break;
    out = squashed;
  }
  return out;
}

export default function SearchModal({ wilayas, detections, onClose, onPick }: Props) {
  const { t, dir } = useI18n();
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
        // Arabic is a first-class query, not a fallback: the Arabic UI
        // advertises "جرّب البليدة", so that exact string has to find Blida.
        const nameAr = normalise(r.nameAr);
        // Codes are zero-padded ("09"), so accept "9" as well as "09".
        const codeHit = /^\d{1,2}$/.test(raw) && r.code === raw.padStart(2, "0");
        return (
          codeHit ||
          name === needle ||
          name.includes(needle) ||
          nameAr === needle ||
          nameAr.includes(needle)
        );
      })
      .sort((a, b) => {
        // Exact hits first, then wilayas with detections, then alphabetical.
        const ea = normalise(a.name) === needle || normalise(a.nameAr) === needle ? 0 : 1;
        const eb = normalise(b.name) === needle || normalise(b.nameAr) === needle ? 0 : 1;
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
      <div className="search-box" dir={dir} onClick={(e) => e.stopPropagation()} onKeyDown={onKey}>
        <div className="search-input">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.5" y2="16.5" />
          </svg>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t.jumpPlaceholder}
            aria-label={t.searchLabel}
          />
          <span className="search-hint">esc</span>
        </div>

        <div className="search-results" ref={listRef}>
          {results.length === 0 ? (
            <div className="search-empty">
              {t.searchNoMatchPre} “{q}”. {rows.length} {t.searchLoadedSuf}
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
                  {r.count > 0 ? `${r.count} ${t.searchDet}` : t.searchNoDet}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}