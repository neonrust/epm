#pragma once

#include "keycodes.h"

#include <string>
#include <tuple>


namespace term
{

// unused fields are 0 or empty

struct Event
{
	key::Key key { key::None };
	key::Modifier key_modifiers { key::NoMod };
	std::string text {};

	// https://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
	struct {
		int button_pressed  { 0 };   // buttons numbering is 1-based, 1-11
		int button_released { 0 };   // buttons numbering is 1-based, 1-11
		int wheel_moved { 0 };          // -1 or +1
		std::tuple<int, int> position { -1, -1 };
	} mouse {};

	bool eof { false };
};

} // NS: term
