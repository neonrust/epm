#include "term.h"

#include <fmt/core.h>
#include <string>

using namespace std::string_literals;

extern std::FILE *g_log;



namespace term
{

void App::resize_cells(std::size_t new_width, std::size_t new_height)
{
	if(new_width == _width and new_height == _height)
		return;

	fmt::print(g_log, "screen resized: {}x{} -> {}x{}\n", new_width, new_height, _width, _height);

	if(new_height != _height)
	{
		_cells.resize(new_height);

		if(new_height > _height)
		{
			auto iter = _cells.begin() + int(_height);
			for(auto row = _height; row < new_height; ++row)
				iter->resize(new_width);
		}
	}

	auto iter = _cells.begin();
	// only the "old" rows (if it has grown)
	auto rows = new_height > _height? _height: new_height;
	for(std::size_t row = 0; row < rows; ++row)
		iter->resize(new_width);

	_width = new_width;
	_height = new_height;

	// TODO: emit 'resize' event (to be received by event loop)
}

void App::refresh()
{
	auto cy = 0u;
	for(auto row_iter = _cells.begin(); row_iter != _cells.end(); row_iter++, cy++)
	{
		auto &row = *row_iter;

		std::size_t prev_x { 0 };
		auto cx = 0u;

		for(auto col_iter = row.begin(); col_iter != row.end(); col_iter++, cx++)
		{
			auto &cell = *col_iter;

			if(cell.dirty)
			{
				cell.dirty = false;

				draw_cell(cx, cy, cell, not (cx == prev_x + 1));
				prev_x = cx;
			}
		}
	}
	_refresh_needed = 0;
}


void App::draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed)
{
	static const auto cell_fmt_move_style { esc::cup + esc::csi + "4{:s};3{:s};{:s}m{:c}" };

	// TODO: move to x, y
	// TODO: write cell contents
	//   possibly into an "execution buffer" ?

	(void)move_needed;
	//if(move_needed) // TODO: can we also skip fg/bg/style if they're the same as previous cell?
	    fmt::print(cell_fmt_move_style, x, y, cell.bg, cell.fg, "0"/*cell.style*/, "a");
	//else
	//	fmt::print(cell_fmt_style, cell.bg, cell.fg, cell.style, cell.ch);
}


} // NS: term
