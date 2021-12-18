#include "samplers.h"

#include <cmath>
#include <algorithm>

#include <assert.h>




namespace term
{

namespace color
{

[[maybe_unused]] static constexpr auto deg2rad = std::numbers::pi_v<float>/180.f;

LinearGradient::LinearGradient(std::initializer_list<Color> colors) :
	 _colors(colors)
{
	assert(_colors.size() > 0);

	// strip special bits, to avoid strange behaviour
	std::for_each(_colors.begin(), _colors.end(), [](auto &c) {
		c = c & ~color::special_mask;
	});
}

Color LinearGradient::sample(float u, float v, float angle) const
{
	assert(u >= 0.f and u <= 1.f and v >= 0.f and v <= 1.f);

	angle = std::fmod(std::fmod(angle, 360.f) + 360.f, 360.f); // ensure in range [0, 360]

	if(_colors.size() == 1)
		return _colors.front();

	// rotate the vector 'uv' by -_rotation degrees
	auto degrees = angle;

	if(degrees >= 270)
	{
		degrees = 360 - degrees;
		v = 1.f - v;
	}
	else if(degrees >= 180)
	{
		degrees = degrees - 180;
		u = 1.f - u;
		v = 1.f - v;
	}
	else if(degrees >= 90)
	{
		degrees = 180 - degrees;
		u = 1.f - u;
	}

	auto radians = degrees*deg2rad;

	auto alpha = u*std::cos(-radians) - v*std::sin(-radians);

	if(alpha == 0.f)
		return _colors.back();

	// this is definitely not the correct way to do it...
	alpha *= std::max(std::abs(std::sin(-radians)), std::abs(std::cos(-radians)));


	const auto idx = alpha*static_cast<float>(_colors.size() - 1);
	const auto idx0 = static_cast<std::size_t>(std::floor(idx));

	const auto blend = idx - float(idx0);
	assert(blend >= 0 and blend <= 1);

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

	const auto r = static_cast<std::uint32_t>(color0r - blend*(color0r - color1r));
	const auto g = static_cast<std::uint32_t>(color0g - blend*(color0g - color1g));
	const auto b = static_cast<std::uint32_t>(color0b - blend*(color0b - color1b));

	auto res = Color(r << 16 | g << 8 | b);
//	fmt::print(g_log, "gradient: {:.2f},{:.2f} -> {:.2f}/{:.2f} -> [{}] #{:06x}; [{}] #{:06x} -> #{:06x}\n", u, v, alpha, blend, idx0, color0, idx0 + 1, color1, res);

	return res;
}

} // NS: color

} // NS: term
