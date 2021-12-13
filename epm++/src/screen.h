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

	void debug_print(std::size_t x, std::size_t y, const std::string &s, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	void update();

	void set_size(Size size);

private:
	void draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed, bool style_needed);

private:
	int _fd { 0 };
	ScreenBuffer _back_buffer;
	ScreenBuffer _front_buffer;

	std::string _output_buffer;
};

} // NS: term
