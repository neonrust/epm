#pragma once

#include <vector>
#include <memory>

#include "cell.h"
#include "size.h"

namespace term
{

struct ScreenBuffer
{
	friend struct Screen;

	void set_size(Size size);
	inline Size size() const { return { _width, _height }; };

	inline void clear() { clear(color::Default, color::Default); }
	void clear(Color fg=color::Unchanged, Color bg=color::Unchanged);

	const Cell &cell(std::size_t x, std::size_t y) const;
	void set_cell(Pos pos, wchar_t ch, std::size_t width, Color fg=color::Default, Color bg=color::Default, Style style=style::Default);

	ScreenBuffer &operator = (const ScreenBuffer &that);

private:
	using CellRow = std::vector<Cell>;
	using CellRowRef = std::unique_ptr<CellRow>;

	std::vector<CellRowRef> _rows;

	std::size_t _width { 0 };
	std::size_t _height { 0 };
};

} // NS: term
