# Docs for AI tools

Every build of this site also writes the documentation as plain Markdown, for language models and
the tools built on them (coding assistants, chat with your docs, retrieval pipelines). They follow
the [llms.txt](https://llmstxt.org/) convention.

| File | What it holds |
| --- | --- |
| [`llms.txt`](https://shoal.readthedocs.io/en/latest/llms.txt) | An index: what Shoal is, then a link to the Markdown copy of every guide page, the roadmap, the coverage page and every API reference page |
| [`llms-full.txt`](https://shoal.readthedocs.io/en/latest/llms-full.txt) | All of those pages in one file, to give a model the whole documentation at once |
| A page's URL followed by `index.md` | That page alone as Markdown, for example [`guide/bot/index.md`](https://shoal.readthedocs.io/en/latest/guide/bot/index.md) |

The files are rebuilt from the same pages as the site, so they always match the version you are
reading: `/en/latest/` follows `main`, and each release has its own version on Read the Docs.

`llms-full.txt` includes the full API reference and is large (a few megabytes). For a model with a
small context window, give it `llms.txt` and let it fetch only the pages it needs.
