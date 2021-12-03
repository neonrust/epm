#include "term.h"

#include "event.h"

#include <iostream>
#include <tuple>
#include <string>
#include <thread>
#include <variant>
#include <fmt/core.h>

#include <unistd.h>

extern std::FILE *g_log;

using namespace std::string_view_literals;
using namespace std::chrono_literals;


namespace term
{

std::variant<Event, int> parse_esc(std::function<bool (char &)> next);
std::variant<Event, int> parse_mouse(std::function<bool(char &)> next);

std::string safe(const std::string &s)
{
	auto res= s;
	auto found = res.find("\x1b");
	while(found != std::string::npos)
	{
		res.replace(found, 1, "\\e");
		found = res.find("\x1b", found);
	}
	return res;
}

std::vector<std::string_view> split(const std::string &s, const std::string &sep)
{
	std::vector<std::string_view> parts;

	std::size_t start { 0 };
	std::size_t end { s.find(sep) };

	while(end != std::string::npos)
	{
		parts.push_back({ s.begin() + int(start), s.begin() + int(end) });
		start = end + sep.size();

		end = s.find(sep, start);
	}
	parts.push_back({ s.begin() + int(start), s.end() });

	return parts;
}

Event App::read_input() const
{
	//constexpr long max_read { 16 };

	std::string all;

	auto next = [&all](char &c) -> bool {
		if(std::cin.rdbuf()->in_avail() == 0)
			return false;

		std::cin.read(&c, 1);
		all += c;

		return bool(std::cin);
	};


	// wait for data to become available
	// TODO: timeout?
	while(std::cin.rdbuf()->in_avail() == 0)
		std::this_thread::sleep_for(std::chrono::milliseconds(10));

	fmt::print(g_log, "{} bytes available\n", std::cin.rdbuf()->in_avail());

//	std::string in { max_read, '\0' };

//	// read everything available
//	std::size_t num_read { 0 };
//	while(num_read < max_read and std::cin.rdbuf()->in_avail() > 0)
//	{
//		if(not std::cin.read(&in[num_read++], 1) or std::cin.eof())
//			return { .eof = true };
//	}
//	in.resize(num_read);

//	if(std::cin.rdbuf()->in_avail() > 0)
//		clear();

	char c { '\0' };

//	while(next(c))
//		;
//	fmt::print(g_log, "sequence: '{}'\n", safe(all));
//	return {};

	next(c);

	if(c == '\x1b') // an escape sequence
	{
		if(not next(c))
			return { .key = key::ESCAPE };

		const auto res = parse_esc(next);
		if(not std::holds_alternative<Event>(res))
			return { .text = all };  // TODO: error code?

		return std::get<Event>(res);
	}
	else
	{
		switch(c)
		{
		case '\x09': return { .key = key::TAB };
		case '\x0a': // fallthrough
		case '\x0d': return { .key = key::ENTER };
		case '\x7f': return { .key = key::BACKSPACE };
		case '\xc2':
		{
			if(not next(c))
				return { .text = all };  // TODO: error code?

			if(c == '\x8d')
			{
				return {
					.key = key::ENTER,
					.key_modifiers = key::ALT,
				};
			}
			break;
		}
		case '\xc3':
		{
			if(not next(c))
				return { .text = all };  // TODO: error code?

			if(c >= '\xa1' and c <= '\xba')
			{
				return {
					.key = key::Key(c + 'a' - '\xa1'),
					.key_modifiers = key::ALT,
				};
			}
		}
		// TODO: more keys?
		}
	}

	fmt::print(g_log, "unhandled input: '{}' ({})\n", safe(all), all.size());

	return { .text = all };
}

std::variant<Event, int> parse_esc(std::function<bool(char&)> next)
{
	fmt::print(g_log, "parse_esc...\n");

	char c { '\0' };

	if(not next(c))
		return -1;

//	fmt::print(g_log, "  c: {}\n", c);

	if(c >= 'a' and c <= 'z')
	{
		return Event{
			.key_modifiers = key::ALT,
			.text = std::string(&c, 1),
		};
	}
	else if(c == '\x0d')
	{
		return Event{
			.key = key::ENTER,
			.key_modifiers = key::ALT,
		};
	}
	else if(c == '<')
		return parse_mouse(next);

	char c1 { '\0' };
	if(not next(c1))
		return -1;

	if(c1 == '[') // CSI
	{
		char c2 { '\0' };
		if(not next(c2))
			return -1;

		if(c2 >= '0' and c2 <= '9')
		{
			char c3 { '\0' };
			if(not next(c3))
				return -1;

			if(c3 == '~')
			{
				switch(c2)
				{
				case '1': // fallthrough
				case '7': return Event{ .key = key::HOME };
				case '4': // fallthrough
				case '8': return Event{ .key = key::END };
				case '2': return Event{ .key = key::INSERT };
				case '3': return Event{ .key = key::DELETE };
				case '5': return Event{ .key = key::PAGE_UP };
				case '6': return Event{ .key = key::PAGE_DOWN };
				default: return -1; // TODO: error code?
				}
			}
			else if(c3 == ';')
			{

				if(c2 == '1')
				{
					char c3 { '\0' };
					char c4 { '\0' };
					if(not next(c3) or not next(c4))
						return -1; // TODO: error code?

					if(c3 == '5')
					{
						if(c4 >= 'A' and c4 <= 'D')  // Ctrl + arrow keys
						{
							return Event{
								.key = key::Key(c4 - 'A' + int(key::ARROW_LEFT)),
								.key_modifiers = key::Modifier::CTRL,
							};
						}
					}
				}
				return -1; // TODO: error code?
			}
			else if(c3 >= '0' and c3 <= '9')
			{
				char c4 { '\0' };
				if(not next(c4))
					return -1; // TODO: error code?

				if(c4 == '~')
				{
					if(c2 == '1' and c3 >= '5' and c3 <= '9')
						return Event{ .key = key::Key(c3 - '5' + int(key::F5)) }; // F5 - F8
					else if(c2 == '2' and c3 >= '0' and c3 <= '4')
						return Event{ .key = key::Key(c3 - '0' + int(key::F9)) }; // F9 - F12
				}
			}
		}
		else if(c2 >= 'A' and c2 <= 'D')
			return Event{ .key = key::Key(c2 - 'A' + int(key::ARROW_UP)) };
		else if(c2 == 'H')
			return Event{ .key = key::HOME };
		else if(c2 == 'F')
			return Event{ .key = key::END };
	}
	else
	{
		if(c1 >= 'A' and c1 <= 'D') // arrow keys
			return Event{ .key = key::Key(c1 - 'A' + int(key::ARROW_UP)) };
	}

	return -1;
}

std::variant<Event, int> parse_mouse(std::function<bool(char &)> next)
{
	fmt::print(g_log, "parse_mouse...\n");

	// '\e[<0;63;16M'  (button1 | no modifiers ; X ; Y ; pressed)
	// '\e[<0;63;16m'  (button1 | no modifiers ; X ; Y ; released)

	char c { '\0' };

	// read until 'M' or 'm' (max 11 chars; 2 + 1 + 3 + 1 + 3 + 1)
	std::string seq;
	for(int idx = 0; idx < 11 and next(c); idx++)
	{
		seq += c;
		if(c == 'M' or c == 'm')
			break;
	}

	if(seq.empty())
		return -1;

	const auto tail = seq[seq.size() - 1];

	// at least 6 chars
	if(seq.size() < 6 or (tail != 'M' and tail != 'm'))
		return -1;

	// cut off 'M'/'m'
	seq.resize(seq.size() - 1);

	// split by ';'
	const auto parts = split(seq, ";");
	if(parts.size() != 3)
		return -1;

	fmt::print(g_log, "  seq: {:02x} {} {} {}\n", std::stoi(parts[0].data()), parts[1], parts[2], tail);

	int buttons_modifiers = std::stoi(parts[0].data());
	const int mouse_x = std::stoi(parts[1].data());
	const int mouse_y = std::stoi(parts[2].data());

	const auto movement = (buttons_modifiers & 0x20) > 0;

	auto button_pressed = not movement and tail == 'M';
	auto button_released = not movement and tail == 'm';

	int mouse_button = 0;
	int mouse_wheel = 0;

	if(not movement)
	{
		// what about mouse buttons 8 - 11 ?
		if(buttons_modifiers >= 128)
			mouse_button = (buttons_modifiers & ~0x80) + 5;
		else if(buttons_modifiers >= 64)
		{
			mouse_button = (buttons_modifiers & ~0x40) + 3;
			mouse_wheel = -(mouse_button - 3)*2 + 1;  // -1 or +1
			// same as wheel?
			button_pressed = button_released = false;
		}
		else
			mouse_button = (buttons_modifiers & 0x0f);
	}

	key::Modifier mods { key::NoMod };
	if((buttons_modifiers & 0x04) > 0)
		mods = key::Modifier(mods | key::SHIFT);
	if((buttons_modifiers & 0x08) > 0)
		mods = key::Modifier(mods | key::ALT);
	if((buttons_modifiers & 0x10) > 0)
		mods = key::Modifier(mods | key::CTRL);

	if(movement)
	{
		fmt::print(g_log, "  mouse move: {},{}\n", mouse_x, mouse_y);
		return Event{
			.key_modifiers = mods,
			.mouse = {
				.position = { mouse_x, mouse_y },
			},
		};
	}
	else
	{
		mouse_button += 1;
		if(button_pressed)
		{
			fmt::print(g_log, "  button  pressed: {} mods: {:03b}  @ {},{}\n", mouse_button, mods, mouse_x, mouse_y);
			return Event{
				.key_modifiers = mods,
				.mouse = {
					.button_pressed = mouse_button,
					.position = { mouse_x, mouse_y },
				},
			};
		}
		else if(button_released)
		{
			fmt::print(g_log, "  button released: {} mods: {:03b}  @ {},{}\n", mouse_button, mods, mouse_x, mouse_y);
			return Event{
				.key_modifiers = mods,
				.mouse = {
					.button_released = mouse_button,
					.position = { mouse_x, mouse_y },
				},
			};
		}
		else if(mouse_wheel != 0)
		{
			fmt::print(g_log, "      wheel moved: {} mods: {:03b}  @ {},{}\n", mouse_wheel, mods, mouse_x, mouse_y);
			return Event{
				.key_modifiers = mods,
				.mouse = {
					.wheel_moved = mouse_wheel,
					.position = { mouse_x, mouse_y },
				},
			};
		}
	}

//	if(c1 == '0')
//	{
//		char c2 { '\0' };
//		if(not next(c2))
//			return -1; // TODO: error code?

//		fmt::print(g_log, "  c2: {}\n", c2);

//		if(c2 == 'M' or c2 == 'm' or c2 == ';') // mouse buttons and/or motion: CSI 'M' mb mx my
//		{
//			const auto pressed = c2 == 'M';

//			unsigned char mb { '\0' };
//			if(not next((char&)mb))
//				return -1;
//			unsigned char mx { '\0' };
//			if(not next((char&)mx))
//				return -1;
//			unsigned char my { '\0' };
//			if(not next((char&)my))
//				return -1;

//			int button = { 0 };
//			unsigned char buttons = (mb & 0xc3);
//			fmt::print(g_log, "buttons: {:x}\n", buttons);
//			if(buttons & 0x80) // buttons 8 - 11
//				button = 8 + int(buttons & 0x03) - 128;
//			else if(buttons & 0x40) // buttons 6 - 7
//				button = 6 + int(buttons & 0x03) - 64;
//			else
//				button = int(buttons & 0x03);

//			return Event{
//				.key_modifiers = Modifier(buttons << 2),
//				.mouse = {
//					.button_pressed = pressed? button: 0,
//					.position { mx, my },
//				},
//			};
//		}
//	}
		//	else
//	if(key_view.starts_with(esc::mouse_click) and key_view.find('M') != std::string_view::npos)
//	{
//		mouse_event = "mouse_click";
//		key_view.remove_prefix(esc::mouse_click.size());
//	}
//	else if (key_view.starts_with(esc::mouse_release) and key_view.ends_with('m')) {
//		mouse_event = "mouse_release";
//		key_view.remove_prefix(4);
//	}
//	else if(key_view.starts_with(esc::mouse_wheel_up))
//	{
//		mouse_event = "mouse_wheel_up";
//		key_view.remove_prefix(esc::mouse_wheel_up.size());
//	}
//	else if(key_view.starts_with(esc::mouse_wheel_down))
//	{
//		mouse_event = "mouse_wheel_down";
//		key_view.remove_prefix(esc::mouse_wheel_down.size());
//	}
//	else
//		in.clear();

//	// Get column and line position of mouse and check for any actions mapped to current position
//	if(not in.empty())
//	{
//		try
//		{
//			const auto delim = key_view.find(';');

//			std::get<0>(mouse_pos) = static_cast<std::size_t>(std::stoi((std::string)key_view.substr(0, delim)));
//			std::get<1>(mouse_pos) = static_cast<std::size_t>(std::stoi((std::string)key_view.substr(delim + 1, key_view.find('M', delim))));
//		}
//		catch (const std::invalid_argument &)
//		{
//			mouse_event.clear();
//		}
//		catch (const std::out_of_range &)
//		{
//			mouse_event.clear();
//		}

//		in = mouse_event;
//	}

	return -1;
}

} // NS: term
