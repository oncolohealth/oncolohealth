# OncoloHealth website

A static site: `index.html` (what OncoloHealth is) and `contribute.html` (researchers share a model or dataset by link). No build step and no server code; any static host works.

## Deploy

- **Your own domain:** upload the `site/` folder to the host behind the domain (Netlify, Vercel, Cloudflare Pages, or any web server). For GitHub Pages with a custom domain, add a `CNAME` file containing the domain.
- **GitHub Pages:** publish the `site/` folder from the repository settings. Pages on a private repository needs a paid GitHub plan.

## Where contributions go

Set `submitMode` in `config.js`:

| Mode | What happens | You set |
|---|---|---|
| `download` (default) | The contributor saves the submission file and emails it to you | `contactEmail` |
| `github` | A prefilled issue opens on the repository. It only works once the repository is public | `githubRepo` |
| `endpoint` | The form POSTs the JSON to a form backend such as Formspree | `endpoint` |

## Reviewing a contribution

```bash
python -m cancer_workbench catalog contribute submission.json
python -m cancer_workbench catalog contributions
```

`contribute` applies the same checks as the form and the catalog schema, then writes the record to `catalog/contributions/<id>.json` as `cataloged`, with review `pending`, no inference permission and no adapter. Nothing is downloaded. A maintainer moves a reviewed record into `catalog/models.json` or `catalog/datasets.json` by hand.
