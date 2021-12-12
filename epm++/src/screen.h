#pragma once

#include <cstdint>

#include "cell.h"


namespace term
{

struct Screen
{
	void set(std::size_t x, std::size_t y, const Cell &c);


private:
	ScreenBuffer _buffer;
};

} // NS: term
