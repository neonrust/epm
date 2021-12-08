#pragma once

#include "keycodes.h"

#include <string>
#include <tuple>
#include <variant>


namespace term
{

// unused fields are 0 or empty


namespace event
{

enum ButtonAction
{
	NoAction       = 0,
	ButtonPressed  = 1,
	ButtonReleased = 2,
};

struct Key
{
	key::Key key;
	key::Modifier modifiers { key::NoMod };
};
struct Char
{
	std::uint32_t codepoint;

	std::u8string to_string() const
	{
		auto cp = codepoint;

		std::size_t len { 0 };
		char8_t first { 0 };

		if(cp < 0x80)
		{
			first = 0;
			len = 1;
		}
		else if(cp < 0x800)
		{
			first = 0xc0;
			len = 2;
		}
		else if(cp < 0x10000)
		{
			first = 0xe0;
			len = 3;
		}
		else if(cp <= 0x10FFFF)
		{
			first = 0xf0;
			len = 4;
		}
		else
			return u8"";

		std::u8string s;
		s.resize(len);

		for(int idx = int(len - 1); idx > 0; --idx)
		{
			s[std::size_t(idx)] = static_cast<char8_t>((cp & 0x3f) | 0x80);
			cp >>= 6;
		}
		s[0] = static_cast<char8_t>(cp | first);

		return std::u8string(s, len);
	}
};
struct MouseButton
{
	int button;
	bool pressed;  // false: released
	int x;
	int y;
	key::Modifier modifiers { key::NoMod };
};
struct MouseWheel
{
	int delta { 0 };
	int x;
	int y;
	key::Modifier modifiers { key::NoMod };
};
struct MouseMove
{
	int x;
	int y;
	key::Modifier modifiers { key::NoMod };
};
struct Resize
{
	std::size_t x { 0 };  // only applicable for sub-surfaces
	std::size_t y { 0 };  // only applicable for sub-surfaces
	std::size_t width;
	std::size_t height;

	struct {
		std::size_t x { 0 };  // only applicable for sub-surfaces
		std::size_t y { 0 };  // only applicable for sub-surfaces
		std::size_t width { 0 };
		std::size_t height { 0 };
	} old {};
};
// TODO: others?


using Event = std::variant<Key, Char, MouseButton, MouseWheel, MouseMove, Resize>;

//struct Event
//{
//	key::Key key { key::None };
//	key::Modifier key_modifiers { key::NoMod };
//	std::string text {};

//	// https://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
//	struct {
//		ButtonAction button_action { NoAction };
//		int button      { 0 };              // buttons numbering is 1-based, 1-11
//		int wheel_moved { 0 };          // -1 or +1
//		std::tuple<int, int> position { -1, -1 };
//	} mouse {};

//	bool eof { false };
//};

} // NS: event

} // NS: term
