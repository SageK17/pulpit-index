# The Pulpit Index

Sermons of fifteen great preachers, from Augustine to Billy Graham, sorted by subject (love, friendship, hatred and enemies, forgiveness and 20 more). Each sermon has sourced context, a note on where the preacher was in life when they gave it, and, where the text is in the public domain, the full sermon to read, mark verse by verse and listen to.

- **Public site (GitHub Pages):** https://sagek17.github.io/pulpit-index/
- **claude.ai version:** https://claude.ai/artifact/Qo3GgniXbejRK2Rptypo3S (private; share it from the page's Share menu)
- **Offline copy:** open `dist/index.html` in any browser. Everything is inside that one file, including the full texts. Friends and shared notes only work on the live site.

## What's in it

| | |
|---|---|
| Preachers | 15, each with a sourced life timeline (stages and dated events) |
| Sermons | 209, filed under 24 subjects |
| Life notes | 195 sermons placed in the preacher's life (the rest are undated) |
| Full texts | 111, public domain, checked word for word against their sources |
| Recordings | 107 links to legitimate audio (LibriVox, MLJ Trust, King Institute, BGEA and others) |

## How it was checked

Every sermon, timeline and life note went through two passes: one agent researched it from primary archives and scholarly editions, and a second independently re-checked every date, place, Bible text and link, correcting or removing anything it could not confirm. Full texts were downloaded programmatically and compared against the source (and, for Edwards, against scans of the printed pages); texts with OCR errors or modernised spelling were removed rather than shown.

Sermons still in copyright (C. S. Lewis, Martin Luther King Jr., Billy Graham, Martyn Lloyd-Jones, and English translations of Bonhoeffer) are summarised in original words with links to authorised sources. Their texts are not reproduced.

## Features

- Browse by subject or preacher, and search everything (⌘K)
- Each preacher's life shown stage by stage, with their sermons placed on a lifeline
- Reader with numbered sentence "verses", five highlight colours, notes, bookmarks, copy with reference, text size, themes (Light, Sepia, Dark, Black), typefaces and line spacing
- Listen: reads the text aloud with the device's voices, highlighting each verse as it goes
- Friends: add friends by code and share notes that appear beside the verse in their reader (live site only)
- Motion: page transitions, staggered entrances and highlight sweeps, all turned off when the device asks for reduced motion

## Project layout

```
template.html        the whole app (HTML, CSS, JS); build.py injects the data
build.py             merges the data below into data/sermons.json and dist/
extract.py           copies research results from workflow journals into data/
data/verified/       fact-checked sermons + preacher profiles, one file per preacher
data/life/           fact-checked life timelines
data/lifectx/        fact-checked "where they were in life" notes per sermon
data/audio/          confirmed recording links per sermon
data/texts-raw/      verbatim public-domain texts, one file per sermon
data/sermons.json    the merged dataset (generated)
dist/index.html      standalone site with texts inlined (generated)
dist/index.artifact.html + dist/texts/   the version published to claude.ai (generated)
docs/                GitHub Pages build (generated); Friends there use Firebase
firebase-adapter.js  Friends backend for the GitHub Pages build (Google sign-in + Firestore)
firestore.rules      Firestore security rules: shared notes readable only by mutual friends
```

Friends on GitHub Pages switch on when `firebase-config.json` (the Firebase web app config, which is public by design) is present at build time. The claude.ai build uses the page's own database and sign-in instead.

## Rebuild

```bash
python3 build.py
```

Then open `dist/index.html`, or serve `dist/` to test the published layout:

```bash
python3 -m http.server 8905 --directory dist
```
