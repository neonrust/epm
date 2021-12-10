#include "term.h"

#include <fmt/core.h>
#include <string>

using namespace std::string_literals;

extern std::FILE *g_log;



namespace term
{

void App::apply_resize(std::size_t new_width, std::size_t new_height)
{
	if(new_width == _width and new_height == _height)
		return;

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

	_output_buffer.reserve(_width*_height*2);  // a ball-part figure ;)
}

void App::debug_print(std::size_t x, std::size_t y, Color fg, Color bg, Style st, const std::string &s)
{
	if(y >= _height)
		return;

	auto &row = _cells[y];
	auto cx = x;

	//std::u8string u8s;
	//u8s.resize(s.size());
	//::mbrtoc8(u8s.data(), s.c_str(), s.size(), nullptr);

	std::size_t next_virtual { 0 };

	for(const auto ch: s)
	{
		if(x >= _width)
			break;

		auto &cell = row[cx];

		if((cell.is_virtual = next_virtual > 0) == true)
		{
			cell.dirty = true;
			next_virtual--;
			cx++;
			continue;
		}

		cell.dirty |= ch != cell.ch or cell.fg != fg or cell.bg != bg or cell.style != st;

		std::strncpy(cell.fg, fg.c_str(), sizeof(cell.fg));
		std::strncpy(cell.bg, bg.c_str(), sizeof(cell.bg));
		std::strncpy(cell.style, st.c_str(), sizeof(cell.style));

		cell.ch = (wchar_t)ch;  // TODO: one utf-8 "character"

		//auto width = 1u; // TODO: width of 'ch'?
		//   - impossible to know, as it's the terminal's decision how to render it.
		//   - can't use CPR because nothing has been written to the terminal yet
		//   - in theory, a test could be performed, computing the width of *all* characters (and caching the result) :)
		//   - or just trust wcswidth() ?
		auto width = ::wcswidth(&cell.ch, 1);
		if(width > 1)
			next_virtual = static_cast<std::size_t>(width - 1);

		cx += static_cast<std::size_t>(width);
	}
}

void App::clear()
{
	_output_buffer.append(fmt::format(esc::ed, 2));

//	for(auto &row: _cells)
//		for(auto &cell: row)
//			cell.dirty = true;

//	_refresh_needed++;
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
				if(not cell.is_virtual)
					draw_cell(cx, cy, cell, not (cx == prev_x + 1));
				prev_x = cx;
			}
		}
	}

	_refresh_needed = 0;
}


void App::draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed)
{
	static const auto style { esc::cup + esc::csi + "4{:s};3{:s};{:s}m" };

	if(move_needed)
		_output_buffer.append(fmt::format(esc::cup, x, y));
	_output_buffer.append(fmt::format(style, cell.bg, cell.fg, "0"/*cell.style*/));
	_output_buffer.append(fmt::format("{}", "a"));
	//else
	//	fmt::print(cell_fmt_style, cell.bg, cell.fg, cell.style, cell.ch);
}


} // NS: term
