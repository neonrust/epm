#include "keycodes.h"

#include <vector>
#include <fmt/core.h>

#include <assert.h>

extern std::FILE *g_log;


namespace key
{

std::string to_string(Key k, Modifier m)
{
	std::string key_name;
	switch(k)
	{
	case BACKSPACE:   key_name = "BACKSPACE"; break;
	case TAB:         key_name = "TAB"; break;
	case ENTER:       key_name = "ENTER"; break;
	case UP:          key_name = "UP"; break;
	case DOWN:        key_name = "DOWN"; break;
	case RIGHT:       key_name = "RIGHT"; break;
	case LEFT:        key_name = "LEFT"; break;
	case HOME:        key_name = "HOME"; break;
	case INSERT:      key_name = "INSERT"; break;
	case DELETE:      key_name = "DELETE"; break;
	case END:         key_name = "END"; break;
	case PAGE_UP:     key_name = "PAGE_UP"; break;
	case PAGE_DOWN:   key_name = "PAGE_DOWN"; break;
	case ESCAPE:      key_name = "ESCAPE"; break;
	case NUMPAD_5:    key_name = "NUMPAD_5"; break;
	default: break;
	}
	if(k >= F1 and k <= F12)
		key_name = fmt::format("F{}", k - F1 + 1);
	if(k >= A and k <= Z)
		key_name = fmt::format("{:c}", 'A' + k - A);

	std::vector<std::string> mod_names;
	if((m & SHIFT) > 0)
		mod_names.push_back("SHIFT");
	if((m & ALT) > 0)
		mod_names.push_back("ALT");
	if((m & CTRL) > 0)
		mod_names.push_back("CTRL");

	std::string result;
	for(const auto &mod: mod_names)
	{
		if(not result.empty())
			result += "+";
		result += mod;
	}
	if(not result.empty())
		result += "+";

	result += key_name;

	return result;
}

Key key_from_string(const std::string &name)
{
	if(name.size() == 1 and name[0] >= 'A' and name[0] <= 'Z')
		return Key(name[0] - 'A' + A);
	if(name[0] == 'F')
	{
		if(name.size() == 2) // F1 .. F9
			return Key(name[1] - '1' + F1);
		if(name.size() == 3) // F10 .. F12
			return Key(name[2] - '0' + F10);
	}
	if(name == "BACKSPACE")  return  BACKSPACE;
	if(name == "TAB")        return  TAB;
	if(name == "ENTER")      return  ENTER;
	if(name == "UP")         return  UP;
	if(name == "DOWN")       return  DOWN;
	if(name == "RIGHT")      return  RIGHT;
	if(name == "LEFT")       return  LEFT;
	if(name == "HOME")       return  HOME;
	if(name == "INSERT")     return  INSERT;
	if(name == "DELETE")     return  DELETE;
	if(name == "END")        return  END;
	if(name == "PAGE_UP")    return  PAGE_UP;
	if(name == "PAGE_DOWN")  return  PAGE_DOWN;
	if(name == "ESCAPE")     return  ESCAPE;
	if(name == "NUMPAD_5")   return  NUMPAD_5;

	fmt::print(g_log, "unknown key: '{}'\n", name);
	assert(false);
	return None;
}

Modifier modifier_from_list(const std::vector<std::string> &v)
{
	key::Modifier mods { key::NoMod };

	for(const auto &name: v)
	{
		if(name == "SHIFT")
			mods = key::Modifier(mods | key::SHIFT);
		else if(name == "ALT")
			mods = key::Modifier(mods | key::ALT);
		else if(name == "CTRL")
			mods = key::Modifier(mods | key::CTRL);
	}
	return mods;
}


} // NS: key
