#include "term.h"

#include <fmt/core.h>
#include <string>
#include <cstring>

using namespace std::string_literals;

extern std::FILE *g_log;



namespace term
{

void App::debug_print(std::size_t x, std::size_t y, const std::string &s, const Color fg, const Color bg, const Style st)
{
	if(y >= _height)
		return;

	auto &row = _cell_rows[y];
	auto cx = x;

	//std::u8string u8s;
	//u8s.resize(s.size());
	//::mbrtoc8(u8s.data(), s.c_str(), s.size(), nullptr);

	std::size_t next_virtual { 0 };

	for(const auto ch: s)
	{
		if(cx >= _width)
			break;

		auto &cell = (*row)[cx];

		if(next_virtual > 0)
		{
			--next_virtual;
			cell.is_virtual = true;
			cell.dirty = true;
			++cx;
			continue;
		}

		const auto diff = ch != cell.ch or std::strcmp(cell.fg, fg) != 0 or std::strcmp(cell.bg, bg) != 0 or std::strcmp(cell.style, st) != 0;
		if(diff)
		{
			cell.dirty = true;
			++_refresh_needed;

			std::strncpy(cell.fg, fg, sizeof(cell.fg));
			std::strncpy(cell.bg, bg, sizeof(cell.bg));
			std::strncpy(cell.style, st, sizeof(cell.style));

			cell.ch = (wchar_t)ch;  // TODO: one utf-8 "character"

			//auto width = 1u; // TODO: width of 'ch'?
			//   - impossible to know, as it's the terminal's decision how to render it.
			//   - can't use CPR because nothing has been written to the terminal yet
			//   - in theory, a test could be performed, computing the width of *all* characters (and caching the result) :)
			//   - or just trust wcswidth() ?
			auto width = 1;//::wcswidth(&cell.ch, 1);
			if(width > 1)
				next_virtual = static_cast<std::size_t>(width - 1);

			cx += static_cast<std::size_t>(width);
		}
		else
			++cx;
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

void App::apply_resize(std::size_t new_width, std::size_t new_height)
{
	if(new_width == _width and new_height == _height)
		return;

	const bool entire_screen = _width == 0 and _height == 0;

	fmt::print(g_log, "resize: {}x{} -> {}x{}\n", _width, _height, new_width, new_height);

	_output_buffer.reserve(new_width*new_height*2);  // a ball-part figure ;)

	const auto before = _output_buffer.size();

	if(new_height != _height)
	{
		if(new_height < _height)
			_cell_rows.resize(new_height); // rows "outside" will be deallocated by shared_ptr
		else
		{
			for(auto idx = _height; idx < new_height; ++idx)
			{
				auto new_row = std::make_shared<CellRow>(new_width, Cell{});
				fmt::print(g_log, "resize:   adding row {} ({})\n", idx, new_row->size());
				_cell_rows.push_back(new_row);

				// set dirty flag for all new rows (and the previously bottom-most row)
				if(not entire_screen)
					for(auto cell_iter = new_row->begin(); cell_iter != new_row->end(); ++cell_iter)
						cell_iter->dirty = true;
			}
		}
	}

	// if the entire screen, we already did the req work above
	if(not entire_screen and new_width != _width)
	{
		auto row_iter = _cell_rows.begin();
		// if it has grown, resize only the "old" rows (new rows are sized upon creation, above), otherwise all rows
		const auto num_rows = new_height > _height? _height: new_height;
		for(std::size_t row = 0; row < num_rows; ++row)
		{
			(*row_iter)->resize(new_width);

			// if wider, set dirty flag for all the new columns
			if(new_width > _width)
			{
				for(auto cell_iter = (*row_iter)->begin() + int(_width - 1); cell_iter != (*row_iter)->end(); ++cell_iter)
					cell_iter->dirty = true;
			}
		}
	}

	if(entire_screen)
		_output_buffer.append(fmt::format(esc::ed, 2));
	else
	{
		if(new_height > _height)
		{
			for(auto idx = _height - 1; idx < new_height; ++idx)
			{
				fmt::print(g_log, "resize:   clearing row {}\n", idx);
				_output_buffer.append(fmt::format(esc::cup + esc::el, idx, 0, 0));
			}
		}
		if(new_width > _width)
		{
			fmt::print(g_log, "resize:   clearing columns {}-eol\n", _width);
			for(auto idx = 0u; idx < new_height; ++idx)
				_output_buffer.append(fmt::format(esc::cup + esc::el, idx, _width, 0));
		}
	}

	_width = new_width;
	_height = new_height;

	const auto after = _output_buffer.size();
	fmt::print(g_log, "resize:   added {} bytes to out buf\n", after - before);
}

void App::render()
{
	fmt::print(g_log, "render:  refresh needed: {}\n", _refresh_needed);

	const auto before = _output_buffer.size();

	auto cells_rendered = 0u;

	auto cy = 0u;
	for(auto row_iter = _cell_rows.begin(); row_iter != _cell_rows.end(); row_iter++, cy++)
	{
		auto &row = *row_iter;

		std::size_t prev_x { 0 };
		Cell prev_cell;
		auto cx = 0u;

		for(auto col_iter = row->begin(); col_iter != row->end(); col_iter++, cx++)
		{
			auto &cell = *col_iter;

			if(cell.dirty)
			{
				cell.dirty = false;

				if(not cell.is_virtual)
				{
					const bool non_adjacent = not (cx == prev_x + 1);
					const bool diff_style = std::strcmp(cell.fg, prev_cell.fg) != 0 or std::strcmp(cell.bg, prev_cell.bg) != 0 or std::strcmp(cell.style, prev_cell.style) != 0;

					draw_cell(cx, cy, cell, non_adjacent, diff_style);
					++cells_rendered;
					prev_cell = cell;
				}
				prev_x = cx;
			}
		}
	}

	const auto after = _output_buffer.size();

	fmt::print(g_log, "render:  cells rendered: {} ; {} bytes added to out buf\n", cells_rendered, after - before);

	_refresh_needed = 0;
}


void App::draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed, bool style_needed)
{
	static const auto style { esc::csi + "4{:s};3{:s};{:s}m" };

	if(move_needed)
		_output_buffer.append(fmt::format(esc::cup, y, x));

	if(style_needed)
		_output_buffer.append(fmt::format(style, cell.bg, cell.fg, cell.style));

	if(cell.ch == 0)
		_output_buffer.append(" ");
	else
		_output_buffer.append(fmt::format("{:c}", char(cell.ch)));
}

} // NS: term
