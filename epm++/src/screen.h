#pragma once

#include <cstdint>

#include "cell.h"
#include "screen-buffer.h"
#include "size.h"

namespace term
{

struct Screen
{
	Screen(int fd);

	inline void clear() { clear(color::Default, color::Default); }
	void clear(Color fg=color::Unchanged, Color bg=color::Unchanged);

	inline void print(const std::string_view s, const Color fg, const Color bg, const Style style) { print(_cursor_x, _cursor_y, s, fg, bg, style); }
	void print(std::size_t x, std::size_t y, const std::string_view s, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	Pos move_cursor(std::size_t x, std::size_t y);
	void set_cell(std::size_t x, std::size_t y, wchar_t ch, std::size_t width, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	void update();

	void set_size(Size size);
	inline Size size() const { return _back_buffer.size(); }
	Size get_terminal_size();


private:
	void draw_cell(const Cell &cell);
	void _out(const std::string_view text);
	void flush_buffer();

private:
	int _fd { 0 };
	ScreenBuffer _back_buffer;
	ScreenBuffer _front_buffer;

	std::size_t _cursor_x;
	std::size_t _cursor_y;

	std::string _output_buffer;
};

} // NS: term
