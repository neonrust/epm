#pragma once

#include <string>
#include <functional>
#include <cstdint>

#include "event.h"

using namespace std::literals::string_view_literals;
using namespace std::literals::string_literals;


namespace term
{

enum Options
{
	Defaults          = 0,
	Fullscreen        = 1 << 0,
	HideCursor        = 1 << 1,
	MouseButtonEvents = 1 << 2,
	MouseMoveEvents   = 1 << 3,
	MouseEvents       = MouseButtonEvents | MouseMoveEvents,
};

struct App
{
	friend void signal_received(int signum);

	App(Options opts = Defaults);
	~App();

	operator bool() const;

	void loop(std::function<bool(Event)> handler);


private:
	bool initialize(Options opts);
	void shutdown();
	std::tuple<std::size_t, std::size_t> get_size() const;
	void write(const std::string_view &s);
	Event read_input() const;

	std::size_t _width { 0 };
	std::size_t _height { 0 };
	bool _initialized { false };
};

} // NS: term

namespace esc
{

const auto esc { "\x1b"s };
const auto csi { esc + "[" };

} // NS: esc
