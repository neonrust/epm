#pragma once

namespace key
{

enum Key
{
	None = 0,
	BACKSPACE = 1000,
	TAB,
	ENTER,
	ARROW_UP,
	ARROW_DOWN,
	ARROW_RIGHT,
	ARROW_LEFT,
	HOME,
	INSERT,
	DELETE,
	END,
	PAGE_UP,
	PAGE_DOWN,
	ESCAPE,
	F1,
	F2,
	F3,
	F4,
	F5,
	F6,
	F7,
	F8,
	F9,
	F10,
	F11,
	F12,
};

enum Modifier
{
	NoMod = 0,
	SHIFT = 1 << 0,
	ALT   = 1 << 1,
	CTRL  = 1 << 2,
};

} // NS: term
