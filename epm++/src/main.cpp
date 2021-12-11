#include "term.h"

#include <tuple>
#include <fmt/core.h>
#include <variant>


std::FILE *g_log { nullptr };

// these are stolen from: https://en.cppreference.com/w/cpp/utility/variant/visit
// helper type for the visitor #4
template<class... Ts> struct overloaded : Ts... { using Ts::operator()...; };
// explicit deduction guide (not needed as of C++20)
template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;


int main()
{
	g_log = fopen("epm.log", "w");
	::setbuf(g_log, nullptr);  // disable buffering

	fmt::print(g_log, "epm term app...\n");

	using namespace term;

	App app(Fullscreen | MouseEvents | HideCursor);
	if(not app)
		return 1;

	app.loop([&app](const event::Event &e) {

		bool keep_going = std::visit(overloaded{
			[](const event::Key &k) {
				fmt::print(g_log, "[main]   key: {}\n", key::to_string(k.key, k.modifiers));
				return not (k.key == key::Q and k.modifiers == key::NoMod);
		    },
			[&app](const event::MouseMove &mm) {
				//fmt::print("[main]   mouse move: {},{}\n", mm.x, mm.y);

				app.debug_print(10, 10, fmt::format("mouse: {}x{}  ", mm.x, mm.y), "3", "0", "");
				return true;
		    },
			[](const event::MouseButton &mb) {
				fmt::print(g_log, "[main]  mouse button {} {} @ {},{}\n",
														mb.button,
														mb.pressed? "pressed": "released",
														mb.x,
														mb.y
				);
				return true;
			},
			[](const event::MouseWheel &mw) {
				fmt::print(g_log, "[main]  mouse wheel: {}\n", mw.delta);
				return true;
			},
			[](const event::Char &c) {
				fmt::print(g_log, "[main]  text: '{}' 0x{:08x}\n", c.to_string(), std::uint32_t(c.codepoint));
				return true;
			},
			[&app](const event::Resize &rs) {
				app.debug_print(rs.width - 10, rs.height - 1, fmt::format("size: {}x{}", rs.width, rs.height), "3", "0", "1");
				return true;
			},
			[](auto){ return true; },
		}, e);

		return keep_going;
	});

	return 0;
}


