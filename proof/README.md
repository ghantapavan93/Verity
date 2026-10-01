# The static proof page

`proof/index.html` is the always-online fallback for the live link: one real run walked down from its
status to its exact model input, the measurements behind the product with their denominators, and the
screenshots under `img/`, taken from the production build of this checkout. Every number on it comes
from the record (`docs/DEMO-PROOF.md`, `docs/GOLDENS.md`, `docs/CUAD.md`, `docs/RETRIEVAL.md`,
`docs/DATA-EVIDENCE.md`); when a recording changes, the page is edited by hand to match, never the other
way round.

It is plain HTML with no scripts and no external requests, so it can be hosted anywhere. The intended
home is Cloudflare Pages at `proof.pavankg.dev`, where static requests are free and the custom domain
sits in the same zone as the live workbench.

## Publishing (Pavan's account)

Either upload the folder in the dashboard: Workers & Pages → Create → Pages → Upload assets → project
`verity-proof` → drag `proof/` → then Custom domains → `proof.pavankg.dev`.

Or from this checkout, once `wrangler login` has been run:

```bash
npx wrangler pages deploy proof --project-name verity-proof
```

## Refreshing the screenshots

With the production build running on 3900 and the API on 8000 (`deploy\up.ps1 -Local`):

```bash
node proof/shots.mjs proof/img
```
