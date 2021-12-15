#pragma once

#include <iostream>
#include <optional>

#include "event.h"

namespace term
{

struct Input
{
	Input(std::istream &s);

	std::vector<event::Event> read();

private:
	bool setup_keys(const std::string &filename);

private:
	std::istream &_in;

	struct KeySequence
	{
		std::string sequence;
		key::Modifier mods;
		key::Key key;
	};
	std::vector<KeySequence> _key_sequences;
};

} // NS: term
