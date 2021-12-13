#include "screen-buffer.h"

#include <fmt/core.h>

#include <assert.h>

extern std::FILE *g_log;


namespace term
{

//void ScreenBuffer::clear(Color fg, Color bg)
//{
//	for(auto &row: _rows)
//	{
//		for(auto &cell: *row)
//		{
//			if(fg != color::Unchanged)
//				cell.fg = fg;
//			if(bg != color::Unchanged)
//				cell.bg = bg;
//			cell.style = style::Default;
//			cell.ch = '\0';
//		}
//	}
//}

void ScreenBuffer::clear()
{
	for(auto &row: _rows)
	{
		for(auto &cell: *row)
		{
			cell.fg = color::Default;
			cell.bg = color::Default;
			cell.style = style::Default;
			cell.ch = '\0';
		}
	}
}

const Cell &ScreenBuffer::cell(std::size_t x, std::size_t y) const
{
	assert(x < _width and y < _height);

	return _rows[y]->operator[](x);
}

void ScreenBuffer::set_cell(std::size_t x, std::size_t y, wchar_t ch, std::size_t width, Color fg, Color bg, Style style)
{
	assert(x < _width and y < _height and width <= 2);

	auto &cell = _rows[y]->operator[](x);


	cell.ch = ch;
	cell.width = static_cast<std::uint_fast8_t>(width);

	if(fg != color::Unchanged)
		cell.fg = fg;
	if(bg != color::Unchanged)
		cell.bg = bg;
	if(style != style::Unchanged)
		cell.style = style;

}




} // NS: term
