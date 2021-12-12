#pragma once

#include <cstdint>
#include <fmt/core.h>

extern std::FILE *g_log;

namespace term
{

constexpr std::size_t max_color_seq_len { 16 };  // e.g. "8;5;r;g;b"
constexpr std::size_t max_style_seq_len { 8 };   // e.g. "1;2;3"

using Style = std::uint8_t;
using Color = std::uint32_t;

namespace color
{

enum
{
	Default =   0x01000000,
	Unchanged = 0x02000000,
};

static constexpr Color special_mask { 0xff000000 };

}

namespace style
{
enum Bit
{
	Normal     = 0,
	Default    = Normal,
	Intense    = 1 << 0,   // can't be combined with 'Faint'
	Bold       = Intense,
	Faint      = 1 << 1,   // can't be combined with 'Intense'
	Dim        = Faint,
	Italic     = 1 << 2,
	Underline  = 1 << 3,
	Overstrike = 1 << 4,
	// dimnishing returns for remaining styles... and not widely supported.
};

}

inline Style operator | (style::Bit a, style::Bit b)
{
	return static_cast<Style>(static_cast<std::uint8_t>(a) | static_cast<std::uint8_t>(b));
}

struct Cell
{
	inline ~Cell()
	{
		fmt::print(g_log, "~Cell\n");
	}

	Color fg     { color::Default };
	Color bg     { color::Default };
	Style style  { style::Default };
	wchar_t ch   { '\0' };     // a single UTF-8 character
};


} // NS: term
