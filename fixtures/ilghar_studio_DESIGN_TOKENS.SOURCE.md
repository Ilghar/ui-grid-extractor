# Source of ilghar_studio_DESIGN_TOKENS.json

Copied unchanged from `site/DESIGN_TOKENS.json` in the cultural-typographic-ai-evaluation repository
(identical copy in abstention-routing-harness). Its own `source` field records the origin:
the ilghar.studio website source, `src/styles.css`, read 2026-10-25.

Every colour in `light` and `dark` was checked against the hex values in that `src/styles.css`.
The file holds colours, fonts, shadows and motion only. It has no spacing tokens;
spacing is checked against Tailwind's default 4px step (see README).

## Correction, 2026-10-31

The copy above carried three retired dark values. They now match the ilghar.studio site
`src/styles.css` on the PR #1 branch (website-ops/github-pages-migration, 1dc87d0, round 3):

| dark token | was | now |
|---|---|---|
| subtle | #9a8a9c | #cbbdce |
| accent_fg | #2c262f | #4a434c |
| line | #4a424c | #a394ae |

Light `accent_fg` stays #fffafc, the value that stylesheet uses (`--accent-fg`, line 13).
No other value changed.
