# Differences from the official TMLR template, and what was done about each

The submission PDF is built from `manuscript/main.md` by `analysis/scripts/make_pdf_source.py`,
pandoc and `template.tex`, on the vendored official style (`tmlr.sty`, `tmlr.bst`, `fancyhdr.sty`,
pinned in `VENDORED.json`). The style files being byte-identical to the official ones does not by
itself show that the page is the one the official template produces: `template.tex` loads further
packages, and pandoc writes the body. This file records a comparison of the two paths, measured
rather than inferred, and the treatment of every difference found.

## How it was measured (2026-09-30)

- **The official kit**: `JmlrOrg/tmlr-style-file` at `7bf90efe3a0debbba703c05c43f3ff7e4d4a2992`.
  The SHA-256 of `LICENSE`, `fancyhdr.sty`, `tmlr.bst` and `tmlr.sty` in that commit match
  `VENDORED.json`, checked in the comparison run itself.
- **The toolchain**: the runner and packages of `.github/workflows/submission-pdf.yml` (ubuntu-24.04,
  TeX Live 2023/Debian `2023.20240207-1`, pdfTeX 1.40.25, pandoc 3.5, poppler 24.02.0).
- **What was built**: (i) the official sample `main.tex`, as shipped; (ii) one short common
  document -- headings of three levels, paragraphs, a list, a table, a figure, two citations, a
  first-page footnote and an appendix -- set twice: once written as the official sample writes a
  paper (its preamble, `\section`, `\caption`, `table` with its title above, natbib), and once as
  `main.md` is written, through `make_pdf_source.py`, pandoc and `template.tex`. Both builds of the
  common document are anonymous (`tmlr.sty` without an option). The figure body is the same
  `\input` in both, so only the typesetting around it differs. Comparing the sample with the
  manuscript directly would not separate a difference of layout from a difference of content.
- **What was read**: `pdfinfo` (page size), `pdffonts`, `pdftotext -bbox-layout` (the position and
  height of every line), `pdftotext` (the text as the checks read it), page images, and the `.aux`.
- **Where**: a temporary workflow on a scratch branch that is not merged. Runs `36698620092`
  (before any treatment), `36700025717` and `36700400337` (after). The PDFs are not byte-reproducible
  across these runs (no fixed `SOURCE_DATE_EPOCH` there); their digests are recorded with each run:
  common document by this repository's path, before `8115bbe7…` / after `c8db784e…`.

## The differences, and the treatment of each

The rule applied: a difference in the page size, the margins, the body typeface, the running header
or the title block is corrected without exception (the venue rejects a submission that "alters the
formatting, font, or layout"). Headings and captions follow the official form. A difference that
stays within how the content of the body is set may remain, with the reason written down.

| Item | Official path | This repository, before | Treatment | After |
|---|---|---|---|---|
| Document class and style | `\documentclass[10pt]{article}`, `\usepackage{tmlr}` | the same (`[preprint]` for the named build) | none needed | the same |
| Page size | US letter, 612 × 792 pt | the same | none needed | the same |
| Text block | body lines from x = 72.0 to 540.0 pt (6.5 in) | the same | none needed | the same |
| Running header | "Under review as submission to TMLR" at y = 25.9 pt, with its rule | the same, at the same place | none needed | the same |
| Title block | title at y = 81.9 pt; "Anonymous authors" / "Paper under double-blind review" at 126.4 / 138.3 pt; abstract box x = 107.9–504.1 pt | the same | none needed | the same |
| Body typeface | Latin Modern 10 pt (LMRoman10, LMSans10-Bold headings) | the same | none needed | the same |
| Section numbers | set by LaTeX: "1", then the title ("1 Introduction", "1.1 …", "A …") | written into the heading text and LaTeX numbering switched off: "1. Introduction" as one string | `make_pdf_source.py` takes main.md's numbers off the headings and LaTeX numbers them; the build stops if a main.md number is not the one LaTeX will assign (`number_headings`), and `check_pdf_text.py --aux` compares main.md's numbers with the ones LaTeX recorded | number and title at the official positions (x = 72.0 / 91.7 pt for a section) |
| Figure caption | `\caption`: "Figure 1: …", 10 pt, full text width, below the figure | a paragraph in the figure: "**Figure 1.** …", 9 pt (`\small`) | the caption goes through `\caption` (`caption.lua`); the figure body stays `\small`, as the figures are drawn for it | "Figure 1: …" at 10 pt, x = 72.0–540.0 pt, as official |
| Table title | "Table 1: …" above the table, 10 pt, centred | tables carried no title | a pandoc `Table:` caption is set by longtable at the official caption size and width (`template.tex` patches `\LT@makecaption`); `check_pdf_text.py --aux` compares LaTeX's table numbers with the titles in main.md. main.md gives its tables titles in the revision of the text | "Table 1: …" at 10 pt, x = 242.9–369.1 pt, as official |
| Floats and the bibliography | a float may be carried past the start of the References (in the common document the table and the figure were set after the References had begun) | the same risk (`[tbp]` floats) | `\FloatBarrier` (placeins) before the bibliography; `check_pdf_text.py` fails if a main-text caption is set after the References | every main-text float before the References |
| Table body | `tabular`, centred, 10 pt | `longtable` at `\footnotesize`, columns weighted to the page width | **kept**. The manuscript's tables are wide and their cells are long; `\footnotesize` and weighted columns are what keep them on the page (`check_pdf_text.py` checks that their right-hand columns survive). This is how the body's content is set, not the page | unchanged |
| Lists | LaTeX `itemize` spacing | pandoc's tight list (no space between items) | **kept**: it is how a tight markdown list is set, and it changes no margin or typeface | unchanged |
| Reference list | entries typed by kind (`@article`: journal in italics) | every entry `@misc` generated from the References section of main.md; identifiers set with `\url` | **kept**. The official sample leaves the format of references open ("any style is acceptable as long as it is used consistently"); the style file is the official `tmlr.bst`, and generating the entries from main.md keeps one bibliography | unchanged |
| Appendices | `\appendix` without a page break | `\clearpage\appendix` | **kept**: it only decides where the appendices begin, after the References | unchanged |
| Link borders | `hyperref` defaults (coloured boxes, on screen only) | `hyperref` with `hidelinks` | **kept**: not printed, and no part of the layout | unchanged |
| Further packages | none beyond `hyperref`, `url` | `glyphtounicode`, `amsmath`/`amssymb`, `longtable`/`booktabs`/`array`/`calc`, `etoolbox`, `footnotehyper`, `seqsplit`, `tikz`, `placeins`, and character definitions | **kept**: each is needed by something the body carries (symbols, tables, footnotes in tables, long tokens, figures, floats); none changes the page, the margins or the fonts, as the rows above measure | -- |

**Vertical positions.** `tmlr.sty` sets `\flushbottom`, so the vertical glue of a full page stretches
or shrinks with what the page carries. Two builds whose pages carry different content therefore
differ by a few points in the vertical position of a heading. That is the official style at work,
not a difference of template, and it is why the comparison was made on a common document.

## What the checks now hold

- `make_pdf_source.py` stops on a heading or a figure whose main.md number is not the one LaTeX will
  assign.
- `check_pdf_text.py --aux` compares main.md's section, figure and table numbers with the ones LaTeX
  recorded in the `.aux` (run by `submission-pdf.yml` on every build).
- `check_pdf_text.py` fails if a main-text figure caption is set after the References, or is not in
  the PDF in LaTeX's form ("Figure 2:").
- `check_pdf_text.py --self-test` (run by `compendium.yml` on both operating systems) fixes the
  page-budget and `.aux` judgements with cases that each must return a named diagnostic.
