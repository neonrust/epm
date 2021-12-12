#pragma once

#include <vector>
#include <memory>

#include "cell.h"

namespace term
{

struct ScreenBuffer
{
	void set_size(std::size_t w, std::size_t h);
	void clear(Color fg=color::Unchanged, Color bg=color::Unchanged);

	const Cell &cell(std::size_t x, std::size_t y) const;


private:
	using CellRow = std::vector<Cell>;
	using CellRowRef = std::unique_ptr<CellRow>;

	std::vector<CellRowRef> _rows;

	std::size_t _width;
	std::size_t _height;
};

} // NS: term
