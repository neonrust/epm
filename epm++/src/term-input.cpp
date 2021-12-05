#include "term.h"

#include "event.h"

#include <iostream>
#include <tuple>
#include <string>
#include <thread>
#include <variant>
#include <fstream>
#include <fmt/core.h>
#include <nlohmann/json.hpp>

#include <unistd.h>
#include <signal.h>
#include <unordered_set>

//extern "C" {
//#include <tkbd.h>
//}

extern std::FILE *g_log;

using namespace std::string_view_literals;
using namespace std::chrono_literals;


namespace term
{

static constexpr char _ = '\0';

std::variant<Event, int> parse_esc(std::function<bool (char &, char)> next);
std::variant<Event, int> parse_csi(std::function<bool(char &, char)> next);
std::variant<Event, int> parse_mouse(const std::string_view &in, std::size_t &eaten);

std::string safe(const std::string &s);
std::string hex(const std::string &s);
std::vector<std::string_view> split(const std::string &s, const std::string &sep);

bool App::init_input()
{
	std::ifstream fp("keys.json");
	if(not fp)
		return false;

	nlohmann::json keys = keys.parse(fp, nullptr, true, true);

	assert(keys.is_array());

	_key_sequences.reserve(keys.size());

	std::unordered_set<std::string> seen_sequences;

	for(const auto &iter: keys.items())
	{
		const auto &item = iter.value();
		assert(item.is_object());
		assert(item.contains("seq"));
		assert(item.contains("key"));

		key::Modifier mods { key::NoMod };
		if(item.contains("mods"))
			mods = key::modifier_from_list(item["mods"].get<std::vector<std::string>>());
		const auto key = key::key_from_string(item["key"].get<std::string>());

		auto seq_str = item["seq"].get<std::string>();
		if(seen_sequences.find(seq_str) != seen_sequences.end())
			fmt::print(g_log, "\x1b[41;97;1msequence '{}' already mapped\x1b[m\n", seq_str);
		seen_sequences.insert(seq_str);

		std::size_t start { 0 };
		std::string seq;
		while(start < seq_str.size())
		{
			auto pos = seq_str.find("|x", start); // e.g.: |x1b
			if(pos != std::string::npos)
			{
				if(pos > start)
					seq += seq_str.substr(start, pos - start);

				auto value = std::stoi(seq_str.substr(pos + 2, 2), nullptr, 16);
				seq += char(value);
				start += 4;
			}
			else
			{
				seq += seq_str.substr(start);
				break;
			}
		}

		_key_sequences.push_back({
			.sequence = seq,
			.mods = mods,
			.key = key,
		});
	}

	// sort, longest sequence first
	std::sort(_key_sequences.begin(), _key_sequences.end(), [](const auto &A, const auto &B) {
		return A.sequence.size() > B.sequence.size();
	});

	return true;
}

void App::shutdown_input()
{
//	::tkbd_detach(&_input_stream);
}

Event App::read_input() const
{
	//constexpr long max_read { 16 };

	// wait for data to become available
	// TODO: timeout?
	while(std::cin.rdbuf()->in_avail() == 0)
		std::this_thread::sleep_for(std::chrono::milliseconds(10));

	std::string in;
	in.resize(std::size_t(std::cin.rdbuf()->in_avail()));
	std::cin.read(in.data(), int(in.size()));

	auto revert = [](const std::string &chars) {
		for(auto iter = chars.rbegin(); iter != chars.rend(); iter++)
			std::cin.putback(*iter);
	};

//	struct tkbd_seq seq;
//	int ok = ::tkbd_read(&_input_stream, &seq);
//	if(not ok)
//	{
//		fmt::print(g_log, "failed to read input! {} ({})", std::strerror(errno), errno);
//		return {};
//	}

//	if(seq.type == TKBD_MOUSE)
//		fmt::print(g_log, "mouse @ {},{}\n", seq.x, seq.y);
//	else if(seq.type == TKBD_KEY)
//		fmt::print(g_log, "key {:04x}  mod: {:02x}  ch: {:c}\n", seq.key, seq.mod, seq.ch);

//	if(seq.type == TKBD_KEY and seq.key == TKBD_KEY_C and seq.mod == TKBD_MOD_CTRL)
//	{
//		fmt::print(g_log, "got Ctrl+C\n");
//		raise(SIGINT);
//	}

/*
	std::string all;
	const std::size_t available = static_cast<std::size_t>(std::cin.rdbuf()->in_avail());
	std::size_t consumed { 0 };

	auto revert = [&consumed](char c) {
//		if(c < 32)
//			fmt::print(g_log, "reverted: 0x{:02x}\n", (int)c);
//		else
//			fmt::print(g_log, "reverted: '{}'\n", c);
		std::cin.putback(c);
		consumed--;
	};
	auto next = [&all, &consumed, available, &revert](char &c, char expected) -> bool {
		if(consumed == available) // don't consume more then initially available
			return false;
		if(std::cin.rdbuf()->in_avail() == 0)
			return false;

		std::cin.read(&c, 1);
		consumed++;

		if(expected != '\0' and c != expected)
		{
			revert(c);
			return false;
		}

		all += c;

		return bool(std::cin);
	};
*/

	//fmt::print(g_log, "\x1b[2m{} bytes available\x1b[m\n", std::cin.rdbuf()->in_avail());

//	char c { '\0' };


#if !defined(NDEBUG)
	// this is just for logging the entire sequence
//	while(next(c, _))
//		;
	fmt::print(g_log, "\x1b[97;1m// {}  {}\n", safe(in), hex(in));
	//for(auto iter = all.rbegin(); iter != all.rend(); iter++)
	//	revert(*iter);
	//all.clear();
	//fmt::print(g_log, "------------------------------------------------------\n");
#endif


	if(in.size() >= 14 and in.starts_with("\x1b[<"))
	{
		fmt::print(g_log, "parse mouse sequence\n");
		//std::size_t eaten { 0 };
		//auto event = parse_mouse(in, eaten);
		return {};
	}

	for(const auto &kseq: _key_sequences)
	{
		if(in.starts_with(kseq.sequence))
		{
			// put the rest of the read chars
			revert(in.substr(kseq.sequence.size()));

			return {
				.key = kseq.key,
				.key_modifiers = kseq.mods,
			};
		}
	}

	// TODO: parse utf-8 character

	fmt::print(g_log, "couldn't parse input: '{}' ({})\n", safe(in), in.size());
	return {};

/*
	next(c, _);

	if(c == '\x1b') // an escape sequence
	{
		if(not next(c, _))
			return { .key = key::ESCAPE };

//		fmt::print(g_log, "  c: \\e{}\n", c);

		revert(c);

		const auto res = parse_esc(next);

		if(not std::holds_alternative<Event>(res))
		{
			fmt::print(g_log, "\x1b[41;97;1mFailed to decode control sequence: '{}' ({})\n", safe(all), all.size());
			return {};  // TODO: error code?
		}

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
			if(not next(c, _))
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
			if(not next(c, _))
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
		fmt::print(g_log, "  c: {}\n", c);
	}

	fmt::print(g_log, "unhandled input: '{}' ({})\n", safe(all), all.size());
	return { .text = all };
*/
}



/*
std::variant<Event, int> parse_esc(std::function<bool(char&, char)> next)
{
	fmt::print(g_log, "parse_esc...\n");

	char c0 { '\0' };

	if(not next(c0, _))
		return -1;

	fmt::print(g_log, "  esc: {}\n", c0);

	if(c0 >= 'a' and c0 <= 'z')
	{
		return Event{
			.key = key::Key(key::A + c0 - 'a'),
			.key_modifiers = key::ALT,
		};
	}
	else if(c0 == '\x0d')
	{
		return Event{
			.key = key::ENTER,
			.key_modifiers = key::ALT,
		};
	}
	else if(c0 >= 'A' and c0 <= 'D') // arrow keys
		return Event{ .key = key::Key(c0 - 'A' + int(key::UP)) };
	else if(c0 == 'O')
	{
		char c1 { '\0' };
		if(not next(c1, _))
			return -1;

		fmt::print(g_log, "  esc: {}{}\n", c0, c1);

		if(c1 >= 'P' and c1 <= 'S') // F1 - F4
			return Event{ .key = key::Key(c1 - 'P' + int(key::F1)) };

		return -1;
	}
	else if(c0 == '[') // CSI
		return parse_csi(next);

	return -1;
}

std::variant<Event, int> parse_csi(std::function<bool(char &, char)> next)
{
	fmt::print(g_log, "parse_csi...\n");

	// NOTE: this is a stupendous mess! Do something about this, please...

	char c1;
	if(not next(c1, _))
		return -1;

	fmt::print(g_log, "  csi: {}\n", c1);

	if(c1 == '<')
		return parse_mouse(next);

	else if(c1 >= 'A' and c1 <= 'D')  // arrow keys
		return Event{ .key = key::Key(c1 - 'A' + int(key::UP)) };
	else if(c1 == 'H')
		return Event{ .key = key::HOME };
	else if(c1 == 'F')
		return Event{ .key = key::END };
	else if(c1 >= '0' and c1 <= '9')
	{
		char c2 { '\0' };
		if(not next(c2, _))
			return -1;

		fmt::print(g_log, "  csi: {}{}\n", c1, c2);

		if(c1 == '1')
		{
			char c3 { '\0' };
			if(not next(c3, _))
				return -1;

			fmt::print(g_log, "  csi: {}{}{}\n", c1, c2, c3);

			if(c3 == '~')
			{
				// \e[1[5789]~
				switch(c2)
				{
				case '5': return Event{ .key = key::F5 };
				case '7': return Event{ .key = key::F6 };
				case '8': return Event{ .key = key::F7 };
				case '9': return Event{ .key = key::F8 };
				}
			}
			else if(c2 == ';')
			{
				// \e[1;5[QRST]

				char c4 { '\0' };
				if(not next(c4, _))
					return -1;

				fmt::print(g_log, "  csi: {}{}{}{}\n", c1, c2, c3, c4);

				if(c4 >= 'P' and c4 <= 'S')
				{
					return Event{
						.key = key::Key(c4 - 'P' + int(key::F1)),
						.key_modifiers = key::CTRL,
					};
				}
				return -1;
			} // c2 == ';'
			else if(c3 == ';')
			{
				// \e[1[5789];5~

				char c4 { '\0' };
				if(not next(c4, _))
					return -1;

				fmt::print(g_log, "  csi: {}{}{}{}\n", c1, c2, c3, c4);

				if(c4 == '5')
				{
					char c5 { '\0' };
					if(not next(c5, '~'))
						return -1;

					switch(c2)
					{
					case '5': return Event{ .key = key::F5, .key_modifiers = key::CTRL };
					case '7': return Event{ .key = key::F6, .key_modifiers = key::CTRL };
					case '8': return Event{ .key = key::F7, .key_modifiers = key::CTRL };
					case '9': return Event{ .key = key::F8, .key_modifiers = key::CTRL };
					}
					return -1;
				}
			} // c3 == ';'
		} // c1 == '1'
		else if(c1 == '2')
		{
			if(c2 == '~')
				return Event{ .key = key::INSERT };

			char c3 { '\0' };
			if(not next(c3, _))
				return -1;

			if(c3 != ';' and c3 != '5' and c3 != '~')
				return -1;

			fmt::print(g_log, "  csi: {}{}{}\n", c1, c2, c3);

			key::Key k;
			switch(c2)
			{
			case '0': k = key::F9; break;
			case '1': k = key::F10; break;
			case '2': k = key::F11; break;
			case '3': k = key::F12; break;
			default: return -1;
			}

			char c4 { '\0' };
			if(not next(c4, _))
				return -1;

			if(c4 == '~')
				return Event{ .key = k };
			else if(c4 == '5')
			{
				char c5 { '\0' };
				if(not next(c5, '~'))
					return -1;

				return Event{ .key = k, .key_modifiers = key::CTRL };
			}
		} // c1 == '2'

		if(c2 == '~')
		{
			switch(c1)
			{
			case '1': // fallthrough
			case '7': return Event{ .key = key::HOME };
			case '4': // fallthrough
			case '8': return Event{ .key = key::END };
			//case '2': return Event{ .key = key::INSERT }; // handled above
			case '3': return Event{ .key = key::DELETE };
			case '5': return Event{ .key = key::PAGE_UP };
			case '6': return Event{ .key = key::PAGE_DOWN };
			default: return -1; // TODO: error code?
			}
		} // c2 == '~'
		else if(c2 == ';')
		{
			if(c1 == '1')
			{
				char c3 { '\0' };
				char c4 { '\0' };
				if(not next(c3, _) or not next(c4, _))
					return -1; // TODO: error code?

				fmt::print(g_log, "  csi: {}{}{}{}\n", c1, c2, c3, c4);

				if(c3 == '5')
				{
					if(c4 >= 'A' and c4 <= 'D')  // Ctrl + arrow keys
					{
						return Event{
							.key = key::Key(c4 - 'A' + int(key::UP)),
							.key_modifiers = key::Modifier::CTRL,
						};
					}
					else if(c4 >= 'P' and c4 <= 'S')
					{
						return Event{
							.key = key::Key(c4 - 'P' + int(key::F1)),
							.key_modifiers = key::Modifier::CTRL,
						};
					}
				}
			}
			else if(c1 == '3')
			{
			}
			return -1; // TODO: error code?
		} // c2 == ';'
		else if(c2 >= '0' and c2 <= '9')
		{
			char c3 { '\0' };
			if(not next(c3, _))
				return -1; // TODO: error code?

			fmt::print(g_log, "  csi: {}{}{}\n", c1, c2, c3);

			if(c3 == '~')
			{
				if(c2 == '1' and c3 >= '5' and c3 <= '9')
					return Event{ .key = key::Key(c3 - '5' + int(key::F5)) }; // F5 - F8
				else if(c2 == '2' and c3 >= '0' and c3 <= '4')
					return Event{ .key = key::Key(c3 - '0' + int(key::F9)) }; // F9 - F12
			}

		} // c2 in ('0' - '9')

	} // c1 in ('0' - '9')

	return -1;
}

std::variant<Event, int> parse_mouse(const std::string_view &in, std::size_t &eaten)
{
//	fmt::print(g_log, "parse_mouse...\n");

	// '\e[<0;63;16M'  (button | modifiers ; X ; Y ; pressed or motion)
	// '\e[<0;63;16m'  (button | modifiers ; X ; Y ; released)

	char c { '\0' };

	// read until 'M' or 'm' (max 11 chars; 2 + 1 + 3 + 1 + 3 + 1)
	std::string seq;
	for(int idx = 0; idx < 11 and next(c, _); idx++)
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

//	fmt::print(g_log, "  mouse seq: {:02x} {} {} {}\n", std::stoi(parts[0].data()), parts[1], parts[2], tail);

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
//		fmt::print(g_log, "  mouse move: {},{}\n", mouse_x, mouse_y);
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
//			fmt::print(g_log, "  button  pressed: {} mods: {:03b}  @ {},{}\n", mouse_button, mods, mouse_x, mouse_y);
			return Event{
				.key_modifiers = mods,
				.mouse = {
					.button_action = ButtonPressed,
					.button = mouse_button,
					.position = { mouse_x, mouse_y },
				},
			};
		}
		else if(button_released)
		{
//			fmt::print(g_log, "  button released: {} mods: {:03b}  @ {},{}\n", mouse_button, mods, mouse_x, mouse_y);
			return Event{
				.key_modifiers = mods,
				.mouse = {
					.button_action = ButtonReleased,
					.button = mouse_button,
					.position = { mouse_x, mouse_y },
				},
			};
		}
		else if(mouse_wheel != 0)
		{
//			fmt::print(g_log, "      wheel moved: {} mods: {:03b}  @ {},{}\n", mouse_wheel, mods, mouse_x, mouse_y);
			return Event{
				.key_modifiers = mods,
				.mouse = {
					.wheel_moved = mouse_wheel,
					.position = { mouse_x, mouse_y },
				},
			};
		}
	}

	return -1;
}
*/
std::string hex(const std::string &s)
{
	std::string res;
	for(const auto &c: s)
		res += fmt::format("\\x{:02x}", (unsigned char)c);
	return res;
}

std::string safe(const std::string &s)
{
	std::string res;
	for(const auto &c: s)
	{
		if(c == 0x1b)
			res += "\\e";
		else if(c == '\n')
			res += "\\n";
		else if(c == '\r')
			res += "\\r";
		else if(c < 0x20)
			res += fmt::format("\\x{:02x}", (unsigned char)c);
		else
			res += c;
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

} // NS: term
