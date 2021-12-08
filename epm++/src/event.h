#pragma once

#include "keycodes.h"

#include <string>
#include <tuple>
#include <variant>


namespace term
{

// unused fields are 0 or empty

enum ButtonAction
{
	NoAction       = 0,
	ButtonPressed  = 1,
	ButtonReleased = 2,
};

struct KeyEvent
{
	key::Key key;
	key::Modifier key_modifiers { key::NoMod };
};
struct TextEvent
{
	char8_t text;
};
struct MouseMoveEvent
{
	int x;
	int y;
};
struct MouseButtonEvent
{
	int button;
	bool pressed;  // false: released
	int x;
	int y;
};
struct SurfaceSizeEvent
{
	int x { 0 };
	int y { 0 };
	int width;
	int height;
};
// TODO: others?


//using Event = std::variant<KeyEvent, TextEvent, MouseMoveEvent, MouseButtonEvent, SurfaceSizeEvent>;

struct Event
{
	key::Key key { key::None };
	key::Modifier key_modifiers { key::NoMod };
	std::string text {};

	// https://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
	struct {
		ButtonAction button_action { NoAction };
		int button      { 0 };              // buttons numbering is 1-based, 1-11
		int wheel_moved { 0 };          // -1 or +1
		std::tuple<int, int> position { -1, -1 };
	} mouse {};

	bool eof { false };
};

} // NS: term
