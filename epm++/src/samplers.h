#pragma once

#include "cell.h"
#include "size.h"


namespace term
{

namespace color
{

struct Sampler
{
	virtual Color sample(Pos pos) = 0;
};

struct Gradient : public Sampler
{
	Color sample(Pos pos) override;
};

} // NS: color

} // NS: term
