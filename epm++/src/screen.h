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
	void clear(Color bg, Color fg=color::Unchanged);

	inline void print(const std::string_view s, const Color fg, const Color bg, const Style style) { print(_cursor.position, s, fg, bg, style); }
	void print(Pos pos, const std::string_view s, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	Pos cursor_move(Pos pos);
	void set_cell(Pos pos, wchar_t ch, std::size_t width, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	void update();

	void set_size(Size size);
	inline Size size() const { return _back_buffer.size(); }
	Size get_terminal_size();


private:
	void draw_cell(const Cell &cell);
	void _out(const std::string_view text);
	void cursor_style(Style style);
	void cursor_color(Color fg, Color bg);
	void flush_buffer();

private:
	int _fd { 0 };
	ScreenBuffer _back_buffer;
	ScreenBuffer _front_buffer;

	struct Cursor
	{
		Pos position { 0, 0 };
		Color fg { color::Default };
		Color bg { color::Default };
		Style style { style::Default };
	} _cursor;

	//Pos _cursor { 0, 0 };

	std::string _output_buffer;
};

} // NS: term
