#pragma once

#include <string>
#include <functional>
#include <cstdint>
#include <cwchar>

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
	NoSignalDecode    = 1 << 4,
};

struct KeySequence
{
	std::string sequence;
	key::Modifier mods;
	key::Key key;
};

struct Cell
{
	char8_t ch;  // single UTF-8 character
	// TODO: fg color
	// TODO: bg color
	// TODO: text style
	bool dirty { false };
};

struct App
{
	friend void signal_received(int signum);

	App(Options opts=Defaults);
	~App();

	operator bool() const;

	void loop(std::function<bool(Event)> handler);

	//std::shared_ptr<Surface> screen_surface();
	//std::shared_ptr<Surface> create_surface(std::size_t x, std::size_t y, std::size_t width, std::size_t height);

private:
	bool initialize(Options opts);
	void shutdown();
	std::tuple<std::size_t, std::size_t> get_size() const;
	void write(const std::string_view &s);

	bool init_input();
	Event read_input() const;
	void shutdown_input();

	void refresh();
	void draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed=true);

private:
	std::size_t _width { 0 };
	std::size_t _height { 0 };
	std::vector<KeySequence> _key_sequences;
	std::size_t _refresh_needed { 0 };

	bool _initialized { false };

	// TODO: use a 2d array instead
	//   that way we can keep (most of) the existing data when the terminal is resized
	//   hm.. but is that an assumption we can make about the terminal itself?  will it visually keep the content without redraw?
	std::vector<Cell> _cells;
};

} // NS: term

namespace esc
{

const auto esc { "\x1b"s };
const auto csi { esc + "[" };

} // NS: esc
