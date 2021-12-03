#include "term.h"

#include <iostream>
#include <tuple>
#include <csignal>
#include <fmt/core.h>

#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>

extern std::FILE *g_log;

namespace esc
{
const auto screen_alternate { csi + "?1049h" };
const auto screen_normal { csi + "?1049l" };

const auto cursor_hide { csi + "?25l" };
const auto cursor_show { csi + "?25h" };

const auto home         { csi + "H" };
const auto clear_eol    { csi + "0J" };
const auto clear_bol    { csi + "1J" };
const auto clear_screen { csi + "2J" + csi + "0;0f" }; // NOTE: why not 'home'

// reporting of mouse buttons (including position)
// https://invisible-island.net/xterm/ctlseqs/ctlseqs.pdf
const auto mouse_buttons_on  { csi + "?1002h" + csi + "?1015h" + csi + "?1006h" };
const auto mouse_buttons_off { csi + "?1002l" + csi + "?1015l" + csi + "?1006l" };
// reporting of mouse position
const auto mouse_move_on  { csi + "?1003h" };
const auto mouse_move_off { csi + "?1003l" };

// terminal synchronized output markers
const auto synch_start { csi + "?2026h" };
const auto synch_end   { csi + "?2026l" };

} // NS: esc

namespace term
{

extern std::string safe(const std::string &s);

using IOFlag = decltype(termios::c_lflag);
IOFlag LocalEcho = ECHO;
IOFlag LineBuffering = ICANON;

void signal_received(int signum);

static App *g_app { nullptr };

::termios initial_settings; // this is here instead of .h to avoid extra includes (and only one app is supported anyway)


static void shutdown()
{
	if(g_app)
		delete g_app;
	g_app = nullptr;
}

App::App(Options opts)
{
	g_app = this;

	initialize(opts);

	::atexit(term::shutdown);
	std::signal(SIGINT, signal_received);
	std::signal(SIGTERM, signal_received);
	std::signal(SIGABRT, signal_received);
	std::signal(SIGFPE, signal_received);
}

App::~App()
{
	g_app = nullptr;
	this->shutdown();
}

App::operator bool() const
{
	return _initialized;
}

void App::loop(std::function<bool (Event)> handler)
{
	while(true)
	{
		auto event = read_input();
		if(event.eof)
		{
			fmt::print(g_log, "\x1b[31;1mEOF\x1b[m\n");
			break;
		}
		if(not handler(event))
			break;
	}

	fmt::print(g_log, "\x1b[31;1mApp:loop exiting\x1b[m\n");
}



bool set_in_flags(IOFlag flags, bool set=true);
bool clear_in_flags(IOFlag flags);

bool App::initialize(Options opts)
{
	if(not isatty(STDIN_FILENO))
		return false;

	if(::tcgetattr(STDIN_FILENO, &initial_settings) != 0)
		return false;

	_initialized = true;

	//const std::string current_tty { ::ttyname(STDIN_FILENO) != NULL ? ::ttyname(STDIN_FILENO) : "unknown" };

	fmt::print(g_log, "turning off stdio synch..\n");
	std::cin.sync_with_stdio(false);
	std::cout.sync_with_stdio(false);

	fmt::print(g_log, "turning off tied stream...\n");
	std::cin.tie(nullptr);
	std::cout.tie(nullptr);

	fmt::print(g_log, "clear termios flags..\n");
	clear_in_flags(LocalEcho | LineBuffering);

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

	const auto size = get_size();
	_width = std::get<0>(size);
	_height = std::get<1>(size);
	fmt::print(g_log, "terminal size: {}x{}\n", _width, _height);

	return true;
}

void App::shutdown()
{
	fmt::print(g_log, "\x1b[31;1mshutdown()\x1b[m\n");

	if(not _initialized)
		return;

	::tcsetattr(STDIN_FILENO, TCSANOW, &initial_settings);

	write(esc::mouse_move_off);
	write(esc::mouse_buttons_off);
	write(esc::screen_normal);
	write(esc::cursor_show);

	_initialized = false;
}

std::tuple<std::size_t, std::size_t> App::get_size() const
{
	::winsize size;

	if(::ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) < 0)
		return { 0, 0 };

	return { std::size_t(size.ws_col), std::size_t(size.ws_row) };
}

void App::write(const std::string_view &s)
{
	fmt::print(g_log, "write: '{}' ({})\n", safe(std::string(s)), s.size());
	::write(STDOUT_FILENO, s.data(), s.size());
	//::flush(STDOUT_FILENO);
}

bool clear_in_flags(IOFlag flags)
{
	return set_in_flags(flags, false);
}

bool set_in_flags(IOFlag flags, bool set)
{
	::termios settings;

	if(::tcgetattr(STDIN_FILENO, &settings))
		return false;

	if(set)
		settings.c_lflag |= flags;
	else
		settings.c_lflag &= ~flags;

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


void signal_received(int signum)
{
	fmt::print(g_log, "\x1b[33;1msignal: {}\x1b[m\n", signum);

	if(g_app)
		g_app->shutdown();
	g_app = nullptr;

	std::signal(signum, SIG_DFL);
	std::raise(signum);
}

} // NS: term