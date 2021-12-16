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

void ScreenBuffer::clear(Color fg, Color bg)
{
	for(auto &row: _rows)
	{
		for(auto &cell: *row)
		{
			cell.ch = '\0';
			if(fg != color::Unchanged)
				cell.fg = color::Default;
			if(bg != color::Unchanged)
				cell.bg = color::Default;
			cell.style = style::Default;
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

ScreenBuffer &ScreenBuffer::operator = (const ScreenBuffer &src)
{
	// since the rows are pointers, we need to copy row by row

	assert(src.size().operator == (size()));

	auto iter = _rows.begin();
	auto src_iter = src._rows.begin();

	while(iter != _rows.end())
		*(*iter++) = *(*src_iter++);

	return *this;
}

void ScreenBuffer::set_size(Size new_size)
{
	const auto &[new_width, new_height] = new_size;

	if(new_width == _width and new_height == _height)
		return;

	const bool initial = _width == 0 and _height == 0;

	fmt::print(g_log, "resize: {}x{} -> {}x{}\n", _width, _height, new_width, new_height);

	_rows.resize(new_height); // if shorter, rows "outside" will be deallocated by the unique_ptr

	if(new_height > _height)
	{
		// if initial (re)size, this will be all rows
		for(auto idx = _height; idx < new_height; ++idx)
		{
			auto new_row = std::make_unique<CellRow>(new_width, Cell{});
			//fmt::print(g_log, "resize:   adding row {} ({})\n", idx, new_row->size());
			_rows[idx] = std::move(new_row);
		}
	}

	if(not initial and new_width != _width)  // if initial (re)size, we already did the required work above
	{
		auto row_iter = _rows.begin();
		// if taller: resize only the "old" rows; new rows are sized upon creation, above. if not, all rows
		const auto num_rows = new_height > _height? _height: new_height;
		for(std::size_t row = 0; row < num_rows; ++row)
		{
			//fmt::print(g_log, "resize:   resizing row {}: {} -> {}\n", row, (*row_iter)->size(), new_width);
			(*row_iter)->resize(new_width);
		}
	}

	_width = new_width;
	_height = new_height;
}


} // NS: term
