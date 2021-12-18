#include "canvas.h"

#include "samplers.h"

#include <fmt/core.h>

extern std::FILE *g_log;


namespace term
{

void Canvas::fill(Rectangle rect, Color c)
{
	color::Constant cc(c);
	fill(rect, &cc);
}

void Canvas::fill(Rectangle rect, const color::Sampler *s)
{
	rect.size.width = std::max(1ul, rect.size.width);
	rect.size.height = std::max(1ul, rect.size.height);

	// TODO: _scr.iterator(rect) ?

	auto num_filled { 0u };

	const auto size = _scr.size();

	(void)s;
//	fmt::print(g_log, "fill:  y: {} -> {}\n", rect.top_left.y, rect.top_left.y + rect.size.height - 1);

	for(auto y = rect.top_left.y; y <= rect.top_left.y + rect.size.height - 1 and y < size.height; y++)
	{
//		fmt::print(g_log, "fill row {}:  x: {} -> {}\n", y, rect.top_left.x, rect.top_left.x + rect.size.width - 1);
		for(auto x = rect.top_left.x; x <= rect.top_left.x + rect.size.width - 1 and x < size.width; x++)
		{
			const float u = static_cast<float>(x - rect.top_left.x) / float(rect.size.width);
			const float v = static_cast<float>(y - rect.top_left.y) / float(rect.size.height);

//			Color c(0x002800 * (y - rect.top_left.y) | (0xf0 - (0x20 * (x - rect.top_left.x))) | 0x280000 * (x - rect.top_left.x));
			_scr.set_cell({ x, y }, '\0', 1, color::Unchanged, s->sample(u, v));
			++num_filled;
		}
	}

	fmt::print(g_log, "fill: {} cells\n", num_filled);
}


} // NS: term
