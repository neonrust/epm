#pragma once

#include "cell.h"
#include "size.h"


namespace term
{

namespace color
{

struct Sampler
{
	virtual Color sample(Pos pos) const = 0;
};

struct Gradient : public Sampler
{
	Gradient(std::initializer_list<Color> colors, float rotation=0);
	Color sample(Pos pos) const override;
};

} // NS: color

} // NS: term
