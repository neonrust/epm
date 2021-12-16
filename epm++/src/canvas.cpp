#include "canvas.h"

#include "samplers.h"


namespace term
{

void Canvas::fill_rectangle(Pos top_left, Size size, Color c)
{
	for(auto y = top_left.y; y <= top_left.y + size.height; y++)
	{
		for(auto x = top_left.x; x <= top_left.x + size.width; x++)
			_scr.set_cell(x, y, ' ', 1, color::Unchanged, c);
	}
}

void Canvas::fill_rectangle(Pos top_left, Size size, color::Sampler &s)
{
	for(auto y = top_left.y; y <= top_left.y + size.height; y++)
	{
		for(auto x = top_left.x; x <= top_left.x + size.width; x++)
			_scr.set_cell(x, y, ' ', 1, color::Unchanged, s.sample({ x - top_left.x, y - top_left.y }));
	}
}



} // NS: term
