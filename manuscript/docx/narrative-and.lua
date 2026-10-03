-- pandoc filter for the APA 7 .docx: write "and", not "&", between the authors of a narrative citation.
--
-- APA 7 joins two authors with "&" inside parentheses and with "and" in running text: "(Hoenig &
-- Heisey, 2001)", but "Hoenig and Heisey (2001)" (Publication Manual, 8.17). The APA style of the CSL
-- project (apa.csl, vendored beside this file) is a CSL 1.0 style with one name form for both, and
-- pandoc's citeproc sets the narrative citation from it with the ampersand. This filter runs after
-- citeproc (manuscript/docx/pandoc.yaml lists it second) and replaces the ampersand in the citations
-- that citeproc set in narrative form, and nowhere else.
--
-- What comes out is held, citation by citation, in manuscript/docx/citations-apa.tsv, which
-- check_docx_text.py compares with the .docx.

function Cite(el)
  if #el.citations ~= 1 or el.citations[1].mode ~= "AuthorInText" then
    return nil
  end
  local replaced = 0
  el.content = el.content:walk({
    Str = function(s)
      if s.text == "&" then
        replaced = replaced + 1
        return pandoc.Str("and")
      end
      return nil
    end,
  })
  if replaced > 1 then
    error("a narrative citation carries more than one ampersand: " .. el.citations[1].id)
  end
  return el
end
