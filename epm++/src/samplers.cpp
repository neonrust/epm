#include "samplers.h"

#include <cmath>
#include <algorithm>

#include <assert.h>




namespace term
{

namespace color
{

[[maybe_unused]] static constexpr auto deg2rad = std::numbers::pi_v<float>/180.f;

Gradient::Gradient(std::initializer_list<Color> colors, float rotation) :
	 _colors(colors),
	 _rotation(std::fmod(std::fmod(rotation, 360.f) + 360.f, 360.f))  // ensure in range [0, 360]
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

	// rotate the vector 'uv' by -_rotation degrees

	if(_colors.size() == 1)
		return _colors.front();

	auto degrees = _rotation;

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

	auto rot_u = u*std::cos(-radians) - v*std::sin(-radians);
	auto rot_v = u*std::sin(-radians) + v*std::cos(-radians);

	fmt::print(g_log, "rot_uv: {:.2f},{:.2f}\n", rot_u, rot_v);

	auto alpha = std::min(1.f, std::max(0.f, rot_u));

	auto uv_len = std::sqrt(rot_u*rot_u + rot_v*rot_v);

	rot_u *= 1.f / uv_len;
	rot_v *= 1.f / uv_len;

	//auto alpha = rot_u

	assert(alpha >= 0 and alpha <= 1);

	if(alpha == 0.f)
		return _colors.back();

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
