-- pandoc filter for the TMLR build: hand a figure's caption to \caption.
--
-- make_pdf_source.py writes each figure's caption, with its "**Figure N.**" label taken off, into a
-- div of class tmlr-caption. This filter converts the div's one paragraph to LaTeX with pandoc's own
-- writer -- so code spans, emphasis and citations in the caption are set as they are everywhere
-- else -- and passes it to \caption, followed by \label. LaTeX then numbers the figure and sets
-- "Figure N:" as the official style does (manuscript/tmlr/TEMPLATE-DIFF.md), and the label puts the
-- number LaTeX assigned into the .aux, where check_pdf_text.py --aux compares it with main.md.
--
-- Anything other than exactly one paragraph and a label is an error, not a best effort: a caption
-- that lost its text or its label would otherwise build.

function Div(el)
  if not el.classes:includes("tmlr-caption") then
    return nil
  end
  if #el.content ~= 1 or el.content[1].t ~= "Para" then
    error("a tmlr-caption div must hold exactly one paragraph")
  end
  local label = el.attributes["label"]
  if label == nil or label == "" then
    error("a tmlr-caption div carries no label")
  end
  local latex = pandoc.write(pandoc.Pandoc({ pandoc.Plain(el.content[1].content) }), "latex")
  latex = latex:gsub("%s+$", "")
  if latex == "" then
    error("a tmlr-caption div converts to no text")
  end
  return pandoc.RawBlock("latex", "\\caption{" .. latex .. "}\\label{" .. label .. "}")
end
