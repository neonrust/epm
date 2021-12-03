#include "term.h"

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
		fmt::print(g_log, "\x1b[33;1mevent: text: '{}' ({})\x1b[m\n", e.text, e.text.size());
		return true;
	});

	return 0;
}


