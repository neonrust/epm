#include "term.h"

#include <iostream>
#include <tuple>
#include <variant>
#include <csignal>
#include <fmt/core.h>
#include <cuchar>

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
// NOTE: make sure these flag bits does not overlap if used simultaneously
[[maybe_unused]] static constexpr IOFlag LocalEcho      = ECHO;
[[maybe_unused]] static constexpr IOFlag LineBuffering  = ICANON;
[[maybe_unused]] static constexpr IOFlag SignalDecoding = ISIG;
[[maybe_unused]] static constexpr IOFlag EightBit       = CS8;
[[maybe_unused]] static constexpr IOFlag CRtoLF         = ICRNL;

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

int App::run()
{
	std::size_t prev_mx { static_cast<std::size_t>(-1) };
	std::size_t prev_my { static_cast<std::size_t>(-1) };


	while(not _should_quit)
	{
		if(_resize_recevied)
		{
			_resize_recevied = false;

			const auto size = get_size();
			const auto new_width = std::get<0>(size);
			const auto new_height = std::get<1>(size);

			enqueue_resize_event(size);

			apply_resize(new_width, new_height);
		}

		// first handle any internally queued events
		for(const auto &event: _internal_events)
			dispatch_event(event);
		_internal_events.clear();

		if(_refresh_needed > 0)
			render();

		flush_buffer();

		const auto event = read_input();

		if(event.has_value())
		{
			const auto *mm = std::get_if<event::MouseMove>(&event.value());
			if(mm != nullptr)
			{
				if(mm->x == prev_mx and mm->y == prev_my)
					continue;
				prev_mx = mm->x;
				prev_my = mm->y;
			}

			dispatch_event(event.value());
		}
	}

	fmt::print(g_log, "\x1b[31;1mApp:loop exiting\x1b[m\n");

	return 0;
}

void App::quit()
{
	_should_quit = true;
}

bool App::dispatch_event(const event::Event &e)
{
	if(std::holds_alternative<event::Key>(e))
		return on_key_event(std::get<event::Key>(e)), true;
	else if(std::holds_alternative<event::Input>(e))
		return on_input_event(std::get<event::Input>(e)), true;
	else if(std::holds_alternative<event::MouseButton>(e))
		return on_mouse_button_event(std::get<event::MouseButton>(e)), true;
	else if(std::holds_alternative<event::MouseMove>(e))
		return on_mouse_move_event(std::get<event::MouseMove>(e)), true;
	else if(std::holds_alternative<event::MouseWheel>(e))
		return on_mouse_wheel_event(std::get<event::MouseWheel>(e)), true;
	else if(std::holds_alternative<event::Resize>(e))
		return on_resize_event(std::get<event::Resize>(e)), true;

	fmt::print(g_log, "unhandled event type index:{}\n", e.index());

	return false;
}

Size App::size() const
{
	return { _width, _height };
}

void App::enqueue_resize_event(std::tuple<std::size_t, std::size_t> size)
{
	_internal_events.emplace_back<event::Resize>({
		.width = std::get<0>(size),
		.height = std::get<1>(size),
		.old = {
			.width = _width,
			.height = _height,
	    },
	});
}


bool modify_io_flags(bool set, IOFlag flags);
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

	if((opts & Fullscreen) > 0)
	{
		_fullscreen = true;
		std::signal(SIGWINCH, signal_received);
	}

	const auto size = get_size();
	auto w = std::get<0>(size);
	auto h = std::get<1>(size);

	apply_resize(w, h);

	if(not init_input())
		return false;

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

	shutdown_input();

	_initialized = false;
}

std::tuple<std::size_t, std::size_t> App::get_size() const
{
	::winsize size { 0, 0, 0, 0 };

	if(::ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) < 0)
		return { 0, 0 };

	return { std::size_t(size.ws_col), std::size_t(size.ws_row) };
}

void App::flush_buffer()
{
	if(not _output_buffer.empty())
	{
		write(_output_buffer);
		_output_buffer.clear();
	}
	_refresh_needed = 0;
}

void App::write(const std::string_view &s)
{
	fmt::print(g_log, "write: '{}' ({})\n", safe(std::string(s)), s.size());
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


void signal_received(int signum)
{
	if(signum == SIGWINCH)
	{
		if(g_app)
			g_app->_resize_recevied = true;
		return;
	}

	fmt::print(g_log, "\x1b[33;1msignal: {}\x1b[m\n", signum);

	if(g_app)
		g_app->shutdown();
	g_app = nullptr;

	std::signal(signum, SIG_DFL);
	std::raise(signum);
}

} // NS: term
