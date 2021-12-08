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

	App app(Fullscreen);
	if(not app)
		return 1;

	app.loop([](const event::Event &e) {

		bool keep_going = std::visit(overloaded{
		    [](const event::Key &k) {
				fmt::print("[main]   key: {}\n", key::to_string(k.key, k.modifiers));
				return not (k.key == key::Q and k.modifiers == key::NoMod);
		    },
		    [](const event::MouseMove &mm) {
				fmt::print("[main]   mouse move: {},{}\n", mm.x, mm.y);
				return true;
		    },
		    [](const event::MouseButton &mb) {
		        fmt::print(
				"[main]  mouse button {} {} @ {},{}\n",
		        mb.button,
		        mb.pressed? "pressed": "released",
		        mb.x,
		        mb.y
				);
				return true;
			},
		    [](const event::MouseWheel &mw) {
				fmt::print("[main]  mouse wheel: {}\n", mw.delta);
				return true;
			},
		    [](const event::Char &c) {
		        (void)c;
				fmt::print("[main]  text: '{}' 0x{:08x}\n", c.to_string(), std::uint32_t(c.codepoint));
				return true;
			},
		    [](const event::Resize &rs) {
				fmt::print("[main]  resize: {}x{}+{}+{}   was: {}x{}+{}+{}\n", rs.width, rs.height, rs.x, rs.y, rs.old.width, rs.old.height, rs.old.x, rs.old.y);
				return true;
			},
		}, e);

		return keep_going;
	});

	return 0;
}


