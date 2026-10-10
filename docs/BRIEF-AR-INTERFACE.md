# Brief — complete the Arabic interface in `apps/atlas`

**Status:** partially implemented. `Header`, `Sidebar` and `SearchModal` were converted.
`DetailPanel`, `Timeline`, `App` and the remaining `Sidebar` fallbacks were not.
**Ship half-done, the UI is worse than not shipping it at all** — a reader cannot tell
which parts are deliberate.

Read `apps/atlas/src/i18n.tsx` first. The `Dict` type is derived from `dict.en`, so
adding an English key will fail typecheck until Arabic has it. Keep that property.

## Non-negotiable: this is a language change, not a content change

1. **Translate, do not reword.** An Arabic string must mean what the English says —
   not more, not less, not more confident.
2. **Never soften a caveat.** These carry the project's honesty guarantees and must
   survive translation intact:
   - "Not a fire-spread model" / "Not a fire-spread model and not a forecast."
   - "Not confirmed wildfires."
   - "Not a validated Algerian wildfire detector… Do not claim coverage of all
     Algerian wildfires, national validation, or universal wildfire-vs-flare separation."
   - The incident grouping note: an empty list is *not* an absence of fires.
3. **`Unavailable` is load-bearing.** It means *"the upstream was asked and declined"*
   and is deliberately distinct from `Loading…` and from a numeric zero. Translate it
   to a single unambiguous Arabic phrase and use it consistently everywhere. Do not
   substitute a word that could also mean "zero" or "none".
4. **Do not alter any number, identifier, verdict or dataset.** Only strings change.
   `priority.level` values (`LOW`/`MODERATE`/`HIGH`/`CRITICAL`), satellite codes,
   FRP figures, coordinates and API payloads stay exactly as they are.

## Layout rule (already decided, do not revisit)

Map and timeline stay **left-to-right** — conventional for map applications.
Only text panels flip to RTL. Keep the `dir` attribute on text panels, not on the map.

## Fonts

Both already self-hosted; add no network requests.
`Plus Jakarta Sans` for Latin, `IBM Plex Sans Arabic` for Arabic, already in the
`--font` stack. Keep it that way.

## Exact strings still hardcoded

### `DetailPanel.tsx` — the largest gap

Literal `"Unavailable"` at lines ~17, 20, 31, 100, 105, 157, 160, 176.
Every one must come from the dictionary.

Visible labels: `Grouping status`, `Priority — rule-based`, `Verification state`,
`Status`, `Evaluated`, `Detection`, `Wilaya`, `Coordinates`, `Acquired`, `Satellite`,
`Brightness Ti4`, `FIRMS confidence`, `State`, `Model`, `Threshold`, `Calibrated`,
`Environment at incident`, `Refresh environment`, `Run AI verification`,
`Loading environmental context…`, the three environment `Band` labels and their
`note` captions, `Not calibrated — this is a model score, not a literal probability
of fire.`, and the priority-`note` explaining that no dataset contributes.

Keep `priority.methodology`, factor names (`thermal_intensity` etc.), factor
`evidence` sentences, and the verifier `message` **exactly as the API returns them.**
Those are English data from a versioned pipeline. Wrap them, do not translate them,
and do not pretend they are localised.

### `Timeline.tsx`

`Replay` / `Stop`, `on map`, `in range`, `shown`, `loaded`, the pill `title`s, the
aria-labels `Move window start` / `Move window end` / `Pan the time window`, and the
footnote *"Replay steps through recorded detections. Times are Algeria local (UTC+1).
Not a fire-spread model and not a forecast."*

### `App.tsx`

`No detections in view` and its sentence, `Fire Radiative Power`, `Historical
observation`, the `Fires` layer-toggle label, and `Cannot reach the API.`

Leave `uv run uvicorn numidia_api.app:app --port 8010` as literal monospace — it is a
shell command, not prose.

### `Sidebar.tsx`

`"Unavailable"` at lines ~22, 91, 94. The layer labels were converted but these three
fallbacks were missed.

### Leave literal

`Ctrl`, `Ctrl K`, `esc`, `NUMIDIA EYE`, the SVG aria-labels, the uvicorn command, and
every API-sourced string.

## Tests

1. Keep all **63 existing `apps/atlas` tests passing**, plus `apps/web` (98) and the
   backend (256). Do not weaken or delete a test to make this work.
2. Extend `i18n.test.tsx` with a guard that makes partial translation impossible:
   render the full `<App/>` inside `I18nProvider` in Arabic mode and assert that none
   of the English user-facing strings above appear in the DOM. A test that catches
   regressions is worth more than the strings themselves.
3. Assert `dir="rtl"` is set on text panels and **not** on the map container.
4. Assert switching back to English restores the original strings exactly.

## Then

Update `docs/FEATURE-STATUS.md` item **6.1** ("English and Arabic interface"), currently
marked **PARTIAL** / "met by `apps/web` only". Once `apps/atlas` is genuinely complete it
is no longer partial — state precisely what is covered and what stays English, and say
why (API-sourced strings are English by design).

`apps/site` remains **English-only by explicit requirement**. Do not add Arabic there.