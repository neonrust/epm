#include "input.h"

#include <string_view>
#include <unordered_set>
#include <nlohmann/json.hpp>
#include <fmt/core.h>
#include <fstream>

#include <signal.h>
#include <poll.h>


extern std::FILE *g_log;

using namespace std::literals::string_view_literals;

namespace term
{


static std::variant<event::Event, int> parse_mouse(const std::string_view &in, std::size_t &eaten);
static std::variant<event::Event, int> parse_utf8(const std::string_view &in, std::size_t &eaten);
static std::vector<std::string_view> split(const std::string_view &s, const std::string &sep);
static std::string safe(const std::string &s);
static std::string hex(const std::string &s);


static constexpr auto mouse_prefix { "\x1b[<"sv };

Input::Input(std::istream &s) :
    _in(s)
{
	setup_keys("keys.json");
}

std::optional<event::Event> Input::wait()
{
	// if no data already available, wait for data to arrive
	//   but allow interruptions
	if(_in.rdbuf()->in_avail() == 0)
	{
		static pollfd pollfds = {
		    .fd = STDIN_FILENO,
		    .events = POLLIN,
		    .revents = 0,
		};
		sigset_t sigs;
		sigemptyset(&sigs);
		int rc = ::ppoll(&pollfds, 1, nullptr, &sigs);
		if(rc == -1 and errno == EINTR)  // something more urgent came up
			return std::nullopt;
	}

	std::string in;
	in.resize(std::size_t(_in.rdbuf()->in_avail()));

	_in.read(in.data(), int(in.size()));

	auto revert = [this](const std::string &chars) {
		for(auto iter = chars.rbegin(); iter != chars.rend(); iter++)
			_in.putback(*iter);
	};


	// TODO: parse cursor position report: "\e[n;mR" (between 6 and 10 characters?)
//	if(in.size() >= 6)
//	{
//		static const auto cpr_ptn = std::regex("^\x1b[(\\d+);(\\d+)R");
//		std::smatch m;
//		if(std::regex_search(in, m, cpr_ptn))
//		{
//			auto cx = m[0];
//			auto cy = m[1];
//		}
//	}


	if(in.size() >= 9 and in.starts_with(mouse_prefix))
	{
		std::size_t eaten { 0 };

		auto event = parse_mouse(std::string_view(in.begin() + int(sizeof(mouse_prefix) - 1), in.end()), eaten);
		if(eaten > 0)
		{
			revert(in.substr(sizeof(mouse_prefix) - 1 + eaten));
			return std::get<event::Event>(event);
		}
	}

	for(const auto &kseq: _key_sequences)
	{
		if(in.starts_with(kseq.sequence))
		{
			// put the rest of the read chars
			revert(in.substr(kseq.sequence.size()));

			return event::Key{
				.key = kseq.key,
				.modifiers = kseq.mods,
			};
		}
	}


	// TODO: parse utf-8 character
	std::size_t eaten { 0 };
	auto event = parse_utf8(std::string_view(in.begin(), in.end()), eaten);
	if(eaten > 0)
	{
		revert(in.substr(eaten));
		return std::get<event::Event>(event);
	}

	fmt::print(g_log, "\x1b[33;1mparse failed: {}\x1b[m {}  ({})\n", safe(in), hex(in), in.size());
	return {};
}

static std::variant<event::Event, int> parse_mouse(const std::string_view &in, std::size_t &eaten)
{
	// '0;63;16M'  (button | modifiers ; X ; Y ; pressed or motion)
	// '0;63;16m'  (button | modifiers ; X ; Y ; released)

//	fmt::print(g_log, "mouse: {}\n", safe(std::string(in)));

	// read until 'M' or 'm' (max 11 chars; 2 + 1 + 3 + 1 + 3 + 1)
	std::size_t len = 0;
	while(len < in.size())
	{
		char c = in[len++];
		if(c == 'M' or c == 'm')
			break;
	}

	if(len < 6) // shortest possible is 6 chars
		return -1;

	const auto tail = in[len - 1];

	// must end with 'M' or 'm'
	if(tail != 'M' and tail != 'm')
		return -1;

	// skip trailing M/m
	std::string_view seq(in.begin(), in.begin() + len - 1);

	// split by ';'
	const auto parts = split(seq, ";");
	if(parts.size() != 3)
		return -1;

//	fmt::print(g_log, "  mouse seq: {:02x} {} {} {}\n", std::stoi(parts[0].data()), parts[1], parts[2], tail);

	std::uint64_t buttons_modifiers = std::stoul(parts[0].data());
	const std::size_t mouse_x = std::stoul(parts[1].data()) - 1;
	const std::size_t mouse_y = std::stoul(parts[2].data()) - 1;

	const auto movement = (buttons_modifiers & 0x20) > 0;

	auto button_pressed = not movement and tail == 'M';
	auto button_released = not movement and tail == 'm';

	std::uint8_t mouse_button = 0;
	int mouse_wheel = 0;

	if(not movement)
	{
		// what about mouse buttons 8 - 11 ?
		if(buttons_modifiers >= 128u)
			mouse_button = static_cast<std::uint8_t>((buttons_modifiers & ~0x80u) + 5);
		else if(buttons_modifiers >= 64u)
		{
			mouse_button = static_cast<std::uint8_t>((buttons_modifiers & ~0x40u) + 3);
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

	eaten = len;

	if(movement)
		return event::MouseMove{
			.x = mouse_x,
			.y = mouse_y,
			.modifiers = mods,
		};

	if(button_pressed)
		return event::MouseButton{
			.button = mouse_button,
			.pressed = true,
			.x = mouse_x,
			.y = mouse_y,
			.modifiers = mods,
		};

	if(button_released)
		return event::MouseButton{
			.button = mouse_button,
			.pressed = false,
			.x = mouse_x,
			.y = mouse_y,
			.modifiers = mods,
		};

	if(mouse_wheel != 0)
		return event::MouseWheel{
			.delta = mouse_wheel,
			.x = mouse_x,
			.y = mouse_y,
			.modifiers = mods,
		};


	eaten = 0;

	return -1;
}

// this was ruthlessly stolen from termlib (tkbd.c)
static const std::uint8_t utf8_length[] = {
    1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 0x00
    1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 0x20
    1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 0x40
    1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 0x60
    1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 0x80
    1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 0xa0
    2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2, // 0xc0
    3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,4,4,4,4,4,4,4,4,5,5,5,5,6,6,1,1  // 0xe0
};
static const std::uint8_t utf8_mask[] = {0x7f, 0x1f, 0x0f, 0x07, 0x03, 0x01};

static std::variant<event::Event, int> parse_utf8(const std::string_view &in, std::size_t &eaten)
{
	if(in.empty())
		return -1;

	std::size_t len = utf8_length[(uint8_t)in[0]];
	if (len > in.size())
		return -1;

	const auto mask = utf8_mask[len - 1];
	char32_t codepoint = static_cast<char8_t>(in[0] & mask);

	for(std::size_t idx = 1; idx < len; ++idx)
	{
		codepoint <<= 6;
		codepoint |= static_cast<char32_t>(in[idx] & 0x3f);
	}

	eaten = len;

	return event::Input{
		.codepoint = codepoint,
	};
}

bool Input::setup_keys(const std::string &filename)
{
	std::ifstream fp(filename);
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

		const auto seq_str = item["seq"].get<std::string>();
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
	// TODO:  better to sort alphabetically?
	//   when searching, we can then stop if 'in' is past (alphabetically) than the 'sequence'
	std::sort(_key_sequences.begin(), _key_sequences.end(), [](const auto &A, const auto &B) {
		return A.sequence.size() > B.sequence.size();
	});

	return true;
}


static std::string hex(const std::string &s)
{
	std::string res;
	for(const auto &c: s)
		res += fmt::format("\\x{:02x}", (unsigned char)c);
	return res;
}

static std::string safe(const std::string &s)
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

static std::vector<std::string_view> split(const std::string_view &s, const std::string &sep)
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
