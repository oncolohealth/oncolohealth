# OncoloHealth website

This directory contains the website's static files. `index.html` is the entry point; `catalog.json`, the stylesheets, scripts, and image files must be served alongside it with their relative paths preserved. There is no build step or package installation.

## Preview locally

From this directory, run:

```sh
python3 -m http.server 8000
```

Open `http://localhost:8000/`. Use an HTTP server rather than opening `index.html` directly: the catalog is loaded with `fetch()`.

## Publish

Configure your static host to publish the contents of this directory as its web root. Use `index.html` as the default document, serve `.webp`, `.svg`, `.js`, `.css`, and `.json` with their normal content types, and enable HTTPS. The site uses hash-based navigation, so it does not require server-side routes for its pages. If the host builds from this repository, set its output or publish directory to `website` and leave the build command empty.

Connect the intended domain using the chosen host's domain and DNS instructions. The domain, DNS records, and hosting provider are deliberately not configured in this repository.

## Behavior and dependencies

- Dataset and model information comes from the bundled `catalog.json` snapshot; changes to the research repository do not automatically refresh it.
- The quote flow currently prepares a brief for the visitor to copy and send through the linked contact method. It does not submit to a server; `data-quote-endpoint` is empty. A production submission service would require a separately configured endpoint and review of its privacy and security behavior.
- Fonts load from Google Fonts, with system fallbacks. Research links and contact links lead to external services. Animation libraries are bundled in `fx/vendor/`.
- Image sources, credits, and licenses are available from “Image sources & licenses” in the site footer. Preserve them, including the attribution and share-alike notices for applicable research images, when publishing or reusing the assets. Bundled third-party libraries retain their license notices.
- Review the research claims, dataset access conditions, image rights, and contact details before public release; these are a snapshot and may change.
