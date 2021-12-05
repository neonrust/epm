#include "term.h"

#include <tuple>
#include <fmt/core.h>

std::FILE *g_log { nullptr };

int main()
{
	g_log = fopen("epm.log", "w");
	::setbuf(g_log, nullptr);  // disable buffering

	fmt::print(g_log, "epm term app...\n");


	term::App app(term::MouseEvents);
	if(not app)
		return 1;

	app.loop([](term::Event e) {

		if(e.mouse.button_action != term::NoAction)
		{
			fmt::print(
				"  mouse button {} {} @ {},{}\n",
				e.mouse.button,
				e.mouse.button_action==term::ButtonPressed? "pressed": "released",
				std::get<0>(e.mouse.position),
				std::get<1>(e.mouse.position)
			);
		}
		else if(e.mouse.wheel_moved != 0)
			fmt::print("  mouse wheel: {}\n", e.mouse.wheel_moved);

		else if(std::get<0>(e.mouse.position) != -1)
			fmt::print(
				"   mouse move: {},{}\n",
				std::get<0>(e.mouse.position),
				std::get<1>(e.mouse.position)
			);

		else if(e.key != key::None)
			fmt::print("   key: {}\n", key::to_string(e.key, e.key_modifiers));
		else
			fmt::print("  text: '{}' ({})\n", e.text, e.text.size());

		return true;
	});

	return 0;
}


