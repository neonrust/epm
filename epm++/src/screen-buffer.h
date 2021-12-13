#pragma once

#include <vector>
#include <memory>

#include "cell.h"

namespace term
{

struct Size
{
	std::size_t width;
	std::size_t height;
};

struct ScreenBuffer
{
	void set_size(std::size_t w, std::size_t h);

	inline Size size() const { return { _width, _height }; };

//	void clear(Color fg=color::Unchanged, Color bg=color::Unchanged);
	void clear();

	const Cell &cell(std::size_t x, std::size_t y) const;
	void set_cell(std::size_t x, std::size_t y, wchar_t ch, std::size_t width, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

private:
	using CellRow = std::vector<Cell>;
	using CellRowRef = std::unique_ptr<CellRow>;

	std::vector<CellRowRef> _rows;

	std::size_t _width;
	std::size_t _height;
};

} // NS: term
