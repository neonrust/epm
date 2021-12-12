#pragma once

#include <string>
#include <functional>
#include <cstdint>
#include <cwchar>
#include <optional>
#include <memory>
#include <signals.hpp>

#include "event.h"
#include "screen-buffer.h"


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
// bitwise OR of multiple 'Options' is still an 'Options'
inline Options operator | (Options a, Options b)
{
	return static_cast<Options>(static_cast<int>(a) | static_cast<int>(b));
}

struct KeySequence
{
	std::string sequence;
	key::Modifier mods;
	key::Key key;
};

constexpr std::size_t max_color_seq_len { 16 };  // e.g. "8;5;r;g;b"
constexpr std::size_t max_style_seq_len { 6 };   // e.g. "1;2;3"

using Color = char[max_color_seq_len];//std::string;
using Style = char[max_color_seq_len];//std::string;

struct Cell
{
	bool dirty { false };
	Color fg { '\0' };//[max_color_seq_len] { '\0' };    // an already "compiled" sequence, e.g. "8;5;r;g;b"   (the '3' prefix is implied)
	Color bg { '\0' };//[max_color_seq_len] { '\0' };    // an already "compiled" sequence, e.g. "1"        (the '4' prefix is implied)
	Style style { '\0' };//[max_style_seq_len] { '\0' }; // an already "compiled" sequence, e.g. "1"
	wchar_t ch { '\0' };                    // a single UTF-8 character
	bool is_virtual { false };              // true: this cell is displaying content from its left neighbor (i.e. a double-width character)
};

struct Size
{
	std::size_t width;
	std::size_t height;
};

struct App
{
	friend void signal_received(int signum);

	App(Options opts=Defaults);
	~App();

	operator bool() const;

	fteng::signal<void(const event::Key)> on_key_event;
	fteng::signal<void(const event::Input)> on_input_event;
	fteng::signal<void(const event::MouseMove)> on_mouse_move_event;
	fteng::signal<void(const event::MouseButton)> on_mouse_button_event;
	fteng::signal<void(const event::MouseWheel)> on_mouse_wheel_event;
	fteng::signal<void(const event::Resize)> on_resize_event;

	int run();

	void quit();

	//std::shared_ptr<Surface> screen_surface();
	//std::shared_ptr<Surface> create_surface(std::size_t x, std::size_t y, std::size_t width, std::size_t height);

	Size size() const;

	void debug_print(std::size_t x, std::size_t y, const std::string &s, const Color fg="0", const Color bg="0", const Style st="");

	void clear();

private:
	bool initialize(Options opts);
	void shutdown();
	std::tuple<std::size_t, std::size_t> get_size() const;

	bool init_input();
	std::optional<event::Event> read_input() const;
	void shutdown_input();

	bool dispatch_event(const event::Event &e);

	void enqueue_resize_event(std::tuple<std::size_t, std::size_t> size);
	void apply_resize(std::size_t width, std::size_t height);
	void render();
	void draw_cell(std::size_t x, std::size_t y, const Cell &cell, bool move_needed=true, bool style_needed=true);
	void flush_buffer();

	void write(const std::string_view &s);

private:
	using CellRow = std::vector<Cell>;
	using CellRowRef = std::shared_ptr<CellRow>;

	ScreenBuffer _back_buffer;
	ScreenBuffer _front_buffer;
	std::vector<CellRowRef> _cell_rows;

	std::size_t _refresh_needed { 0 };

	std::size_t _width { 0 };
	std::size_t _height { 0 };

	std::vector<KeySequence> _key_sequences;

	bool _emit_resize_event { false };
	std::vector<event::Event> _internal_events;

	std::string _output_buffer;

	bool _fullscreen { false };
	bool _initialized { false };

	bool _should_quit { false };
};

} // NS: term

namespace esc
{

const auto esc { "\x1b"s };
const auto csi { esc + "[" };

const auto cuu { csi + "{:d}A" };
const auto cud { csi + "{:d}B" };
const auto cuf { csi + "{:d}C" };
const auto cub { csi + "{:d}D" };
const auto cup { csi + "{:d};{:d}H" };  // y; x
const auto ed  { csi + "{}J" }; // erase lines: 0 = before cursor, 1 = after cursor, 2 = entire screen
const auto el  { csi + "{}K" }; // erase line:  0 = before cursor, 1 = after cursor, 2 = entire line

} // NS: esc
