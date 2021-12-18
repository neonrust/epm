#pragma once

#include "screen.h"

namespace term
{

namespace color
{
struct Sampler;
}

struct Rectangle
{
	Pos top_left;
	Size size;
};


struct Canvas
{
	Canvas(Screen &scr) : _scr(scr) {};

	inline void clear() { _scr.clear(); };
	inline Size size() const { return _scr.size(); };

	void fill(Rectangle rect, Color c);
	void fill(Rectangle rect, const color::Sampler *s, float fill_angle=0);


private:
	Screen &_scr;
};

} // NS: term
