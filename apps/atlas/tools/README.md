# Browser harness

A manual, dependency-free pass over the running app. `npm test` proves the
dictionary is complete and that `dir` lands on the right elements; it cannot
tell you the Arabic UI actually *looks* right, which is how the attribution row
shipped with its label welded to its licence text.

## Running it

```powershell
# terminal 1 — API
uv run uvicorn numidia_api.app:app --port 8010

# terminal 2 — app
npm run dev -- --port 5600

# terminal 3 — headless Chrome (SwiftShader; the harness has no GPU)
chrome --headless=new --remote-debugging-port=9222 --use-angle=swiftshader `
       --enable-unsafe-swiftshader --window-size=1600,1000 about:blank
```

Then:

```powershell
node tools/ar-pass.mjs
```

Screenshots land in `%TEMP%\opencode\shots`. Read them. They are the point.

## Why it is built the way it is

Every rule below was learned from a check that passed while measuring nothing:

- **`Network.enable` before `Network.setCacheDisabled`.** The other order serves
  stale JS, and a real fix looks like it did nothing.
- **Wait on conditions, never on a sleep.** `waitFor` polls for a painted
  feature count or a rendered incident row. Sampling 200 ms after the map handle
  appears measures nothing.
- **Trust the DOM over the screenshot.** A pass reported the time-axis pills
  running right-to-left in Arabic mode; computed `direction` on `.tl` was `ltr`
  and the pills ran in DOM order. The screenshot was wrong, the code was right.
- **React tracks input values on the element.** `input.value = x` is invisible
  to `onChange`. Use the native `HTMLInputElement.prototype` setter, or the
  search "filters" to nothing and reports all 69 rows.

## What it checks

Console errors, computed `direction` per region, `document.fonts` for both
faces, horizontal overflow and clipped text in every panel, Arabic search
round-trip, and the disclaimer strings that must not be softened in translation.