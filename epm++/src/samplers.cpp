#include "samplers.h"

#include <cmath>

#include <assert.h>


namespace term
{

namespace color
{

Gradient::Gradient(std::initializer_list<Color> colors, float rotation) :
	 _colors(colors),
	 _rotation(rotation)
{
	assert(_colors.size() > 0);

	// strip special bits, to avoid strange behaviour
	std::for_each(_colors.begin(), _colors.end(), [](auto &c) {
		c = c & ~color::special_mask;
	});
}

Color Gradient::sample(float u, float v) const
{
	assert(u >= 0.f and u <= 1.f and v >= 0.f and v <= 1.f);

	// TODO: rotate the vector 'uv' by -_rotation degrees
	//   and sample the colors using the rotated 'u'

	if(_colors.size() == 1)
		return _colors.front();

	const auto radians = _rotation*std::numbers::pi_v<float>/180.f;

	const auto alpha = u*std::cos(radians) + v*std::sin(radians);

	if(alpha == 0.f)
		return _colors.back();

	const auto idx = alpha*static_cast<float>(_colors.size() - 1);
	const auto idx0 = static_cast<std::size_t>(std::floor(idx));

	const auto blend = idx - float(idx0);

	const auto color0 = _colors[idx0];
	if(idx0 == _colors.size() - 1)
		return color0;

	const auto color1 = _colors[idx0 + 1];

	const auto color0r = color::red_part(color0);
	const auto color0g = color::green_part(color0);
	const auto color0b = color::blue_part(color0);

	const auto color1r = color::red_part(color1);
	const auto color1g = color::green_part(color1);
	const auto color1b = color::blue_part(color1);

	const auto r = static_cast<std::uint8_t>(color0r - blend*(color0r - color1r));
	const auto g = static_cast<std::uint8_t>(color0g - blend*(color0g - color1g));
	const auto b = static_cast<std::uint8_t>(color0b - blend*(color0b - color1b));

	return Color(r << 16 | g << 8 || b);
}



} // NS: color

} // NS: term
