-- pandoc filter for the APA 7 .docx: set the cells of every table in paragraph styles of their own.
--
-- pandoc writes a cell of a pipe table as one paragraph in the style Compact, which the lists
-- outside tables use too, and the size and spacing of a table were left to the table style. Word
-- did not apply the table style's paragraph and run formatting to those paragraphs: the cells came
-- out in twelve point, double spaced, the heading row not bold, with words broken inside columns
-- sized for ten point (seen in Word on 2026-10-04; LibreOffice applied the table style and showed
-- none of it). This filter puts each cell's paragraph in "Table Heading" (the heading row) or
-- "Table Text" (the other rows), which the reference document defines with the size, the spacing,
-- the weight and the keeping with the next paragraph themselves (make_docx_source.py), so that the
-- cells do not depend on how a reader applies a table style. A Div with a custom style sets the
-- style of the paragraphs in it, not of a cell's plain text, so the plain text becomes a paragraph.
--
-- A cell of a pipe table holds one line of inline text; anything else stops the build.

local function restyle(cell, style)
  local content
  if #cell.contents == 0 then
    content = {}
  elseif #cell.contents == 1 and cell.contents[1].t == "Plain" then
    content = cell.contents[1].content
  else
    error("a table cell holds something other than one line of text")
  end
  cell.contents = { pandoc.Div({ pandoc.Para(content) }, { ["custom-style"] = style }) }
  return cell
end

function Table(t)
  if #t.foot.rows ~= 0 then
    error("a table has a foot, which the .docx does not set")
  end
  for _, row in ipairs(t.head.rows) do
    for i, cell in ipairs(row.cells) do
      row.cells[i] = restyle(cell, "Table Heading")
    end
  end
  for _, body in ipairs(t.bodies) do
    if #body.head ~= 0 then
      error("a table body has heading rows of its own, which the .docx does not set")
    end
    for _, row in ipairs(body.body) do
      for i, cell in ipairs(row.cells) do
        row.cells[i] = restyle(cell, "Table Text")
      end
    end
  end
  return t
end
