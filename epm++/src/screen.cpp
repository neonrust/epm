#include "screen.h"

namespace term
{

void Screen::debug_print(std::size_t x, std::size_t y, const std::string &s, const Color fg, const Color bg, const Style style)
{
	auto size = _back_buffer.size();

	if(y >= size.height)
		return;

	auto cx = x;

	//std::u8string u8s;
	//u8s.resize(s.size());
	//::mbrtoc8(u8s.data(), s.c_str(), s.size(), nullptr);

//	std::size_t next_virtual { 0 };

	for(const auto ch: s)
	{
		if(cx >= size.width)
			break;

		wchar_t wch = ch;
		const auto width = wch > 20? static_cast<std::size_t>(::wcswidth(&wch, 1)): 1u;

		_back_buffer.set_cell(cx, y, ch, width, fg, bg, style);

		//auto width = 1u; // TODO: width of 'ch'?
		//   - impossible to know, as it's the terminal's decision how to render it.
		//   - can't use CPR because nothing has been written to the terminal yet
		//   - in theory, a test could be performed, computing the width of *all* characters (and caching the result) :)
		//   - or just trust wcswidth() ?

		cx += static_cast<std::size_t>(width);
	}
}

void Screen::flush(Output &out)
{
	// TODO: compare '_back_buffer' and '_front_buffer'
	//   write the diference to 'out' (such that '_front_buffer' becomes identical to '_back_buffer')

	auto size = _back_buffer.size();

	for(std::size_t cy = 0; cy < size.height; ++cy)
	{
		for(std::size_t cx = 0; cx < size.width; ++cx)
		{
			auto &back_cell = _back_buffer.cell(cx, cy);
			auto &front_cell = _front_buffer.cell(cx, cy);


			if(back_cell == front_cell)
				cx += back_cell.width;
			else
			{
				// TODO: write back_cell to 'out'
			}
		}
	}

	(void)out;
}


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


} // NS: term
