#pragma once

#include "keycodes.h"

#include <string>
#include <tuple>


namespace term
{

// unused fields are 0 or empty

enum ButtonAction
{
	NoAction       = 0,
	ButtonPressed  = 1,
	ButtonReleased = 2,
};

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
