#include "screen.h"

#include <string_view>

using namespace std::literals::string_view_literals;


namespace term
{

namespace esc
{

[[maybe_unused]] static constexpr auto esc { "\x1b"sv };
[[maybe_unused]] static constexpr auto csi { "\x1b["sv };

[[maybe_unused]] static constexpr auto cuu { "\x1b[{:d}A"sv };
[[maybe_unused]] static constexpr auto cud { "\x1b[{:d}B"sv };
[[maybe_unused]] static constexpr auto cuf { "\x1b[{:d}C"sv };
[[maybe_unused]] static constexpr auto cub { "\x1b[{:d}D"sv };
[[maybe_unused]] static constexpr auto cup { "\x1b[{:d};{:d}H"sv };  // y; x
[[maybe_unused]] static constexpr auto ed  { "\x1b[{}J"sv }; // erase lines: 0 = before cursor, 1 = after cursor, 2 = entire screen
[[maybe_unused]] static constexpr auto el  { "\x1b[{}K"sv }; // erase line:  0 = before cursor, 1 = after cursor, 2 = entire line

} // NS: esc


Screen::Screen(int fd) :
	_fd(fd)
{

}

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

void Screen::update()
{
	// TODO: compare '_back_buffer' and '_front_buffer'
	//   write the diference to 'out' (such that '_front_buffer' becomes identical to '_back_buffer')

	auto size = _back_buffer.size();

	for(std::size_t cy = 0; cy < size.height; ++cy)
	{
		std::size_t prev_x { 0 };

		for(std::size_t cx = 0; cx < size.width; ++cx)
		{
			auto &back_cell = _back_buffer.cell(cx, cy);
			auto &front_cell = _front_buffer.cell(cx, cy);


			if(back_cell == front_cell)
				cx += back_cell.width;  // store it, or call wcswidth() again ?
			else
			{
				const bool non_adjacent = not (cx == prev_x + 1);
				const bool diff_style = back_cell.fg != front_cell.fg or back_cell.bg != front_cell.bg or back_cell.style != front_cell.style;

				draw_cell(cx, cy, back_cell, non_adjacent, diff_style);
				prev_x = cx;
			}
		}
	}

	flush_buffer();

	// terminal is now in synch with back buffer, we can copy it to the front buffer

	// since the rows are pointers, we need to copy each row separately
	auto biter = _back_buffer._rows.begin();
	auto fiter = _front_buffer._rows.begin();
	while(biter != _back_buffer._rows.end())
		*(*fiter++) = *(*biter++);
}

void Screen::set_size(Size size)
{
	_output_buffer.reserve(size.width*size.height*2);  // a nice, round estimate :)

	_back_buffer.set_size(size);
	_front_buffer.set_size(size);
}


void Screen::draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed, bool style_needed)
{
	static constexpr auto color_style { "\x1b[4{:s};3{:s};{:s}m"sv };

	if(move_needed)
		_output_buffer.append(fmt::format(esc::cup, y, x));

	if(style_needed)
		_output_buffer.append(fmt::format(color_style, escify(cell.bg), escify(cell.fg), escify(cell.style)));

	if(cell.ch == 0)
		_output_buffer.append(" ");
	else
		_output_buffer.append(fmt::format("{:c}", char(cell.ch)));
}

void Screen::flush_buffer()
{
	if(not _output_buffer.empty())
	{
		::write(_fd, _output_buffer.c_str(), _output_buffer.size());
		_output_buffer.clear();
	}
}


} // NS: term
