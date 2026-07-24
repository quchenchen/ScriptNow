# Login product showcase design QA

## Comparison target

- Source visual truth: the existing ScriptNow login screen selected in the in-app browser annotation for `http://127.0.0.1:5174/login?next=/`, including its two-column hero, warm editorial typography, ink-green palette, login card, SVG mark, and day/night controls.
- Implementation: the same route after extending the page with independent Novel and Script chapters, workflow, product capabilities, and a closing login action.
- Viewport and density: 1280 × 720 CSS px, device scale factor 1. Implementation captures are 1280 × 720 PNG.
- State: unauthenticated Creator login; Chinese UI; both light and dark theme surfaces reviewed.
- Implementation evidence:
  - `design-qa-assets/login-desktop-dark.png`
  - `design-qa-assets/login-desktop-light.png`
  - `design-qa-assets/login-domain-novel.png`
  - `design-qa-assets/login-domain-script.png`
  - `design-qa-assets/login-workflow.png`

## Full-view comparison

The original first-screen composition is preserved: editorial story statement on the left and a focused login card on the right. The extension continues the same serif/sans hierarchy, green/rust/ivory palette, fine borders, restrained radii, and generous spacing. Novel and Script are intentionally presented as separate full-width chapters rather than sibling cards.

## Focused-region comparison

- Hero: SVG mark, eyebrow, title wrapping, supporting copy, form density, and theme/language controls retain the existing visual hierarchy.
- Domain chapters: Novel uses a light editorial field; Script uses a dark cinematic field. Each has its own icon, headline, description, and full viewport rhythm.
- Workflow: fixed deep ink-green background avoids semantic-token inversion in dark mode; ivory copy and rust waypoints meet the intended contrast.
- Motion: reveal, cue, hover, and pulse effects are subtle and disabled under `prefers-reduced-motion`.

## Required fidelity surfaces

- Fonts and typography: existing Georgia/Inter system is preserved; display headings remain serif with responsive `clamp()` sizing and readable wrapping.
- Spacing and layout rhythm: sections use a shared 1180 px content measure; independent domain chapters have full-width, near-viewport-height presentation; responsive breakpoints collapse without narrow columns.
- Colors and tokens: existing brand palette is preserved. Workflow uses a fixed dark brand surface to prevent the earlier pale-cyan dark-theme regression.
- Image quality and assets: the existing real ScriptNow SVG mark and Phosphor icon library are used; there are no placeholders or improvised raster assets.
- Copy and content: copy describes actual product concepts—separate Novel/Script domains, candidates, adoption, graph/timeline, revision, and Agent roles—without implementation jargon.

## Interaction and runtime verification

- Login fields and submit action remain present.
- “了解 ScriptNow” anchors to the product story.
- Closing “进入 ScriptNow” returns the viewport to the login card.
- Theme switching works.
- Browser console contains only Vite connection debug messages; no page errors.
- Creator production build passed.
- Frontend suite passed: 19 files, 46 tests.

## Comparison history

1. Earlier P1: Novel and Script appeared as paired cards, implying a shared product domain. Fixed by splitting them into two independent full-width chapters.
2. Earlier P1: workflow background inherited a theme-dependent semantic green and became pale cyan in dark mode. Fixed with a stable deep ink-green surface and explicit foreground colors.
3. Earlier P2: dynamic translation-key construction failed strict TypeScript checking. Fixed with explicit typed title/body keys.
4. Post-fix browser evidence confirms independent domain chapters, stable workflow contrast, preserved login hierarchy, and error-free runtime.

## Follow-up polish

- P3: consider adding a real product screenshot or authored illustration only after a dedicated visual-art direction is approved; current page deliberately stays typographic.
- P3: add automated viewport screenshot coverage for 390 px mobile width.

final result: passed
