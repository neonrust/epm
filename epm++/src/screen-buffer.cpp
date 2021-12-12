#include "screen-buffer.h"

#include <fmt/core.h>

#include <assert.h>

extern std::FILE *g_log;


namespace term
{

void ScreenBuffer::set_size(std::size_t new_width, std::size_t new_height)
{
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
			fmt::print(g_log, "resize:   adding row {} ({})\n", idx, new_row->size());
			_rows[idx] = std::move(new_row);
		}
	}

	if(not initial and new_width != _width)  // if initial (re)size, we already did the required work above
	{
		auto row_iter = _rows.begin();
		// if taller: resize only the "old" rows; new rows are sized upon creation, above. if not, all rows
		const auto num_rows = new_height > _height? _height: new_height;
		for(std::size_t row = 0; row < num_rows; ++row)
			(*row_iter)->resize(new_width);
	}

	_width = new_width;
	_height = new_height;
}

void ScreenBuffer::clear(Color fg, Color bg)
{
	for(auto &row: _rows)
	{
		for(auto &cell: *row)
		{
			if(fg != color::Unchanged)
				cell.fg = fg;
			if(bg != color::Unchanged)
				cell.bg = bg;
			cell.style = style::Normal;
			cell.ch = '\0';
		}
	}
}

const Cell &ScreenBuffer::cell(std::size_t x, std::size_t y) const
{
	assert(x < _width and y < _height);

	return _rows[y]->operator[](x);
}




} // NS: term
