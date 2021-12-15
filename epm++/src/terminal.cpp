#include "app.h"

#include <iostream>
#include <tuple>
#include <variant>
#include <csignal>
#include <fmt/core.h>
#include <cuchar>
#include <string_view>

#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>

using namespace std::literals::string_view_literals;

extern std::FILE *g_log;

namespace esc
{
const auto screen_alternate { "\x1b[?1049h"sv };
const auto screen_normal { "\x1b[?1049l"sv };

const auto cursor_hide { "\x1b[?25l"sv };
const auto cursor_show { "\x1b[?25h"sv };

// reporting of mouse buttons (including position)
// https://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
const auto mouse_buttons_on  { "\x1b[?1002h\x1b[?1015h\x1b[?1006h"sv };
const auto mouse_buttons_off { "\x1b[?1002l\x1b[?1015l\x1b[?1006l"sv };
// reporting of mouse position
const auto mouse_move_on  { "\x1b[?1003h"sv };
const auto mouse_move_off { "\x1b[?1003l"sv };

// terminal synchronized output markers
const auto synch_start { "\x1b[?2026h"sv };
const auto synch_end   { "\x1b[?2026l"sv };

} // NS: esc

namespace term
{

void write(const std::string_view s);

extern std::string safe(const std::string &s);

using IOFlag = decltype(termios::c_lflag);
// NOTE: make sure these flag bits does not overlap if used simultaneously
[[maybe_unused]] static constexpr IOFlag LocalEcho      = ECHO;
[[maybe_unused]] static constexpr IOFlag LineBuffering  = ICANON;
[[maybe_unused]] static constexpr IOFlag SignalDecoding = ISIG;
[[maybe_unused]] static constexpr IOFlag EightBit       = CS8;
[[maybe_unused]] static constexpr IOFlag CRtoLF         = ICRNL;

::termios initial_settings; // this is here instead of .h to avoid extra includes (and only one app is supported anyway)

bool modify_io_flags(bool set, IOFlag flags);
bool clear_in_flags(IOFlag flags);

bool init_terminal(Options opts)
{
	if(not isatty(STDIN_FILENO))
		return false;

	if(::tcgetattr(STDIN_FILENO, &initial_settings) != 0)
		return false;

	//const std::string current_tty { ::ttyname(STDIN_FILENO) != NULL ? ::ttyname(STDIN_FILENO) : "unknown" };

	fmt::print(g_log, "turning off stdio synch..\n");
	std::cin.sync_with_stdio(false);
	std::cout.sync_with_stdio(false);

	fmt::print(g_log, "turning off tied stream...\n");
	std::cin.tie(nullptr);
	std::cout.tie(nullptr);

	fmt::print(g_log, "clear termios flags..\n");
	clear_in_flags(LocalEcho | LineBuffering);
	//modify_io_flags(true, EightBit | CRtoLF);

	if((opts & NoSignalDecode) > 0)
	{
		fmt::print(g_log, "disabling signal sequence decoding...\n");
		clear_in_flags(SignalDecoding);
	}

	if((opts & Fullscreen) > 0)
	{
		fmt::print(g_log, "enabling alternate screen...\n");
		write(esc::screen_alternate);
	}
	if((opts & HideCursor) > 0)
	{
		fmt::print(g_log, "hiding cursor...\n");
		write(esc::cursor_hide);
	}
	if((opts & MouseButtonEvents) > 0)
	{
		fmt::print(g_log, "enabling mouse button events...\n");
		write(esc::mouse_buttons_on);
	}
	if((opts & MouseMoveEvents) > 0)
	{
		fmt::print(g_log, "enabling mouse move events...\n");
		write(esc::mouse_move_on);
	}

	return true;
}

void restore_terminal()
{
	fmt::print(g_log, "\x1b[31;1mshutdown()\x1b[m\n");

	::tcsetattr(STDIN_FILENO, TCSANOW, &initial_settings);

	write(esc::mouse_move_off);
	write(esc::mouse_buttons_off);
	write(esc::screen_normal);
	write(esc::cursor_show);
}

void write(const std::string_view s)
{
	//fmt::print(g_log, "write: '{}' ({})\n", safe(std::string(s)), s.size());
	::write(STDOUT_FILENO, s.data(), s.size());
	//::flush(STDOUT_FILENO);
}

bool clear_in_flags(IOFlag flags)
{
	return modify_io_flags(false, flags);
}

bool modify_io_flags(bool set, IOFlag flags)
{
	::termios settings;

	if(::tcgetattr(STDIN_FILENO, &settings))
		return false;

	// NOTE: this only works if none of the flag bits overlap between lflags, cflags and iflags
	static constexpr auto iflags_mask = CRtoLF;
	static constexpr auto cflags_mask = EightBit;
	static constexpr auto lflags_mask = LocalEcho | LineBuffering  | SignalDecoding;

	const auto iflags = flags & iflags_mask;
	const auto lflags = flags & lflags_mask;
	const auto cflags = flags & cflags_mask;
	if(set)
	{
		if(iflags)
			settings.c_iflag |= iflags;
		if(cflags)
			settings.c_cflag |= cflags;
		if(lflags)
			settings.c_lflag |= lflags;
	}
	else
	{
		if(iflags)
			settings.c_iflag &= ~iflags;
		if(cflags)
			settings.c_cflag &= ~cflags;
		if(lflags)
			settings.c_lflag &= ~lflags;
	}

	if(::tcsetattr(STDIN_FILENO, TCSANOW, &settings))
		return false;

	if(flags & LineBuffering)
	{
		if(set)
			::setlinebuf(stdin);
		else
			::setbuf(stdin, nullptr);
	}

	return true;
}

} // NS: term
