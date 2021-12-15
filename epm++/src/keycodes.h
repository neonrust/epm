#pragma once

#include <string>
#include <vector>

namespace term
{

namespace key
{

enum Key
{
	None = 0,
	BACKSPACE = 1000,
	TAB,
	ENTER,
	UP,
	DOWN,
	RIGHT,
	LEFT,
	HOME,
	INSERT,
	DELETE,
	END,
	PAGE_UP,
	PAGE_DOWN,
	ESCAPE,
	NUMPAD_5,
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
	A = 'A',
	B,
	C,
	D,
	E,
	F,
	G,
	H,
	I,
	J,
	K,
	L,
	M,
	N,
	O,
	P,
	Q,
	R,
	S,
	T,
	U,
	V,
	W,
	X,
	Y,
	Z,
};

enum Modifier
{
	NoMod = 0,
	SHIFT = 1 << 0,
	ALT   = 1 << 1,
	CTRL  = 1 << 2,
};

std::string to_string(Key k, Modifier m);

Key key_from_string(const std::string_view s);
Modifier modifier_from_list(const std::vector<std::string> &v);

} // NS: key

} // NS: term
