#pragma once

#include <cstdint>

#include "cell.h"
#include "screen-buffer.h"

namespace term
{

struct Output;

struct Screen
{
	void debug_print(std::size_t x, std::size_t y, const std::string &s, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	void flush(Output &out);


private:
	ScreenBuffer _back_buffer;
	ScreenBuffer _front_buffer;
};

} // NS: term
