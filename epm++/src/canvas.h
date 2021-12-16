#pragma once

#include "screen.h"

namespace term
{

namespace color
{
struct Sampler;
}


struct Canvas
{
	Canvas(Screen &scr) : _scr(scr) {};

	void fill_rectangle(Pos top_left, Size size, Color c);
	void fill_rectangle(Pos top_left, Size size, const color::Sampler *s);


private:
	Screen &_scr;
};

} // NS: term
