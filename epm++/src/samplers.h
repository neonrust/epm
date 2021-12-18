#pragma once

#include "cell.h"
#include "size.h"

#include <vector>


namespace term
{

namespace color
{

struct Sampler
{
	virtual Color sample(float u, float v) const = 0;
};

struct Constant : public Sampler
{
	inline Constant(Color c) : _c(c) {};

	inline Color sample(float, float) const override { return _c; }

private:
	Color _c;
};

struct Gradient : public Sampler
{
	Gradient(std::initializer_list<Color> colors, float rotation=0);
	Color sample(float u, float v) const override;

private:
	std::vector<Color> _colors {};
	float _rotation { 0 };
};

} // NS: color

} // NS: term
