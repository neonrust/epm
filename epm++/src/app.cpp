#include "app.h"
#include "terminal.h"

#include <csignal>

#include <sys/ioctl.h>


namespace term
{

void signal_received(int signum);
void app_atexit();

static App *g_app { nullptr };

App::App(Options opts) :
    _input(std::cin),
    _screen(STDOUT_FILENO),
    _fullscreen((opts & Fullscreen) > 0)
{
	g_app = this;

	init_terminal(opts);

	::atexit(app_atexit);
	std::signal(SIGINT, signal_received);
	std::signal(SIGTERM, signal_received);
	std::signal(SIGABRT, signal_received);
	std::signal(SIGFPE, signal_received);

	if((opts & Fullscreen) > 0)
		std::signal(SIGWINCH, signal_received);
}

void app_atexit()
{
	if(g_app)
		g_app->shutdown();
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

	_emit_resize_event = true;  // to emit the initial resize

	while(not _should_quit)
	{
		if(_emit_resize_event)
		{
			_emit_resize_event = false;

			const auto size = _screen.get_terminal_size();

			enqueue_resize_event(size);

			_screen.set_size(size);
		}

		// first handle any internally queued events
		for(const auto &event: _internal_events)
			dispatch_event(event);
		_internal_events.clear();

		_screen.update();

		const auto event = _input.wait();

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

void App::shutdown()
{
	if(_initialized)
	{
		_initialized = false;
		restore_terminal();
	}
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

void App::enqueue_resize_event(Size size)
{
	_internal_events.emplace_back<event::Resize>({
	    .size = size,
	    .old = {
	        .size = _screen.size(),
	    },
	});
}

void signal_received(int signum)
{
	if(signum == SIGWINCH)
	{
		if(g_app)
			g_app->_emit_resize_event = true;
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
