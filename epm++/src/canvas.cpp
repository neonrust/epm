#include "canvas.h"

#include "samplers.h"


namespace term
{

void Canvas::fill_rectangle(Pos top_left, Size size, Color c)
{
	if(size.width == 0 or size.height == 0)
		return;

	for(auto y = top_left.y; y <= top_left.y + size.height - 1; y++)
	{
		for(auto x = top_left.x; x <= top_left.x + size.width - 1; x++)
			_scr.set_cell({ x, y }, ' ', 1, color::Unchanged, c);
	}
}

void Canvas::fill_rectangle(Pos top_left, Size size, const color::Sampler *s)
{
	if(size.width == 0 or size.height == 0)
		return;

	for(auto y = top_left.y; y <= top_left.y + size.height - 1; y++)
	{
		for(auto x = top_left.x; x <= top_left.x + size.width - 1; x++)
		{
			const float u = static_cast<float>(x - top_left.x) / float(size.width);
			const float v = static_cast<float>(y - top_left.y) / float(size.height);

			_scr.set_cell({ x, y }, ' ', 1, color::Unchanged, s->sample(u, v));
		}
	}
}


} // NS: term
