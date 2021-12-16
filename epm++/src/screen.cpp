#include "screen.h"

#include <string_view>

#include <sys/ioctl.h>


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
[[maybe_unused]] static constexpr auto cup { "\x1b[{1:d};{0:d}H"sv };
[[maybe_unused]] static constexpr auto ed  { "\x1b[{}J"sv }; // erase lines: 0 = before cursor, 1 = after cursor, 2 = entire screen
[[maybe_unused]] static constexpr auto el  { "\x1b[{}K"sv }; // erase line:  0 = before cursor, 1 = after cursor, 2 = entire line

[[maybe_unused]] static constexpr auto fg_bg { "\x1b[3{:s};4{:s}m"sv };
[[maybe_unused]] static constexpr auto style { "\x1b[{}m"sv };
[[maybe_unused]] static constexpr auto clear_screen { "\x1b[2J"sv }; // ed[2]


} // NS: esc


Screen::Screen(int fd) :
	_fd(fd)
{

}



void Screen::print(std::size_t x, std::size_t y, const std::string_view s, const Color fg, const Color bg, const Style style)
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

void Screen::clear(Color fg, Color bg) // TODO: fg & bg colors?
{
	_back_buffer.clear(fg, bg);

	_cursor_x = 0;
	_cursor_y = 0;
	_out(fmt::format(esc::cup, _cursor_x, _cursor_y));

	// these are more an optimization...
	// clearing only the back buffer will result in the correct screen content.
	//_front_buffer.clear(fg, bg);

	//if(fg != color::Default and bg != color::Default)
	//	_output_buffer.append(fmt::format(esc::fg_bg, escify(fg), escify(bg)));

	//_output_buffer.append(esc::clear_screen);
}

void Screen::update()
{
	// compare '_back_buffer' and '_front_buffer',
	//   write the difference to the output buffer (such that '_front_buffer' becomes identical to '_back_buffer')

	const auto size = _back_buffer.size();

	move_cursor(0, 0);

	for(std::size_t cy = 0; cy < size.height; ++cy)
	{
		for(std::size_t cx = 0; cx < size.width; ++cx)
		{
			auto &back_cell = _back_buffer.cell(cx, cy);
			auto &front_cell = _front_buffer.cell(cx, cy);

			if(back_cell != front_cell)
				draw_cell(cx, cy, back_cell);
			else
				++_cursor_x;
		}
	}

	flush_buffer();

	// the terminal content is now in synch with back buffer, we can copy back -> front

	// since the rows are pointers, we need to copy row by row
	auto biter = _back_buffer._rows.begin();
	auto fiter = _front_buffer._rows.begin();
	while(biter != _back_buffer._rows.end())
		*(*fiter++) = *(*biter++);
}

void Screen::set_size(Size size)
{
	_output_buffer.reserve(size.width*size.height*4);  // an attempt at an over-estimate :)

	_back_buffer.set_size(size);
	_front_buffer.set_size(size);
}


void Screen::draw_cell(std::size_t x, std::size_t y, const Cell &cell)
{
	move_cursor(x, y);

	_out(fmt::format(esc::fg_bg, escify(cell.bg), escify(cell.fg)));
	_out(fmt::format(esc::style, escify(cell.style)));

	if(cell.ch == 0)
	{
		_out(" "sv);
		++_cursor_x;
	}
	else
	{
		_out(fmt::format("{:c}"sv, char(cell.ch)));
		_cursor_x += cell.width;  // store the width, or call wcswidth() again ?
	}

}

Size Screen::get_terminal_size()
{
	::winsize size { 0, 0, 0, 0 };

	if(::ioctl(_fd, TIOCGWINSZ, &size) < 0)
		return { 0, 0 };

	return { std::size_t(size.ws_col), std::size_t(size.ws_row) };
}

void Screen::_out(const std::string_view text)
{
	_output_buffer.append(text);
}

Pos Screen::move_cursor(std::size_t x, std::size_t y)
{
	const Pos prev_pos { _cursor_x, _cursor_y };
	if(x != _cursor_x or y != _cursor_y)
	{
		_out(fmt::format(esc::cup, x, y));
		_cursor_x = x;
		_cursor_y = y;
	}
	return prev_pos;
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
