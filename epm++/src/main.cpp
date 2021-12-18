#include "app.h"
#include "canvas.h"
#include "samplers.h"

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

	fmt::print(g_log, "term test app!\n");

	using namespace term;

	App app(Fullscreen /*| MouseEvents*/ | HideCursor);
	if(not app)
		return 1;

	Canvas canvas(app.screen());
	//color::Gradient sampler({ color::Cyan, color::Yellow }, 0);
	color::Constant sampler(Color(0x206090));

//	app.on_app_start.connect([&app]() {
//		auto size = app.screen().size();
//		app.screen().print({0, 0}, "A");
//		app.screen().print({size.width - 1, size.height - 1}, "E");
//	});

	int seq { -1 };
	app.on_key_event.connect([&app, &seq, &canvas, &sampler](const event::Key &k) {
		fmt::print(g_log, "[main]    key: {}\n", key::to_string(k.key, k.modifiers));

		if(k.key == key::ESCAPE and k.modifiers == key::NoMod)
			app.quit();

		if(k.key == key::RIGHT and k.modifiers == key::NoMod and seq < 4)
			seq++;
		else if(k.key == key::LEFT and k.modifiers == key::NoMod and seq > 0)
			seq--;

		fmt::print(g_log, "\x1b[97;32;1mtest seq: {}\x1b[m\n", seq);
		canvas.clear();
//		switch(seq)
//		{
//		case 0: app.screen().print({ 4, 4 }, "blue              ", color::Blue, color::Default, style::Default); break;
//		case 1: app.screen().print({ 4, 4 }, "purple          OB", color::Purple, color::Default, style::Overstrike); break;
//		case 2: app.screen().print({ 4, 4 }, "yellow on blue   U", color::Yellow, color::Blue, style::Underline); break;
//		case 3: app.screen().print({ 4, 4 }, "green on (same) UI", color::Green, color::Unchanged, style::Underline | style::Italic); break;
//		case 4: app.screen().print({ 4, 4 }, "white on red     B", color::White, color::Red, style::Bold); break;
//		}
		switch(seq)
		{
		case 0: canvas.fill({ { 0, 0 }, { 5, 5 } }, &sampler); app.screen().print({5,5}, "+"); break;
		case 1: canvas.fill({ { 0, 0 }, { 5, 6 } }, &sampler); app.screen().print({5,6}, "+"); break;
		case 2: canvas.fill({ { 0, 0 }, { 5, 5 } }, &sampler); break;
		case 3: canvas.fill({ { 0, 0 }, { 5, 5 } }, &sampler); break;
		case 4: canvas.fill({ { 0, 0 }, { 5, 5 } }, &sampler); break;
		}
	});
	app.on_input_event.connect([](const event::Input &c) {
		fmt::print(g_log, "[main]  input: '{}' 0x{:08x}\n", c.to_string(), std::uint32_t(c.codepoint));
		return true;
	});
	app.on_mouse_move_event.connect([](const event::MouseMove &mm) {
		fmt::print(g_log, "[main]  mouse: {},{}\n", mm.x, mm.y);

		//app.screen().print({ 10, 10 }, fmt::format("mouse: {},{}  ", mm.x, mm.y));
//		canvas.clear();
//		canvas.fill({ { 0, 0 }, { mm.x, mm.y } }, &sampler);
	});
	app.on_mouse_button_event.connect([](const event::MouseButton &mb) {
		fmt::print(g_log, "[main] button: {} {} @ {},{}\n",
				   mb.button,
				   mb.pressed? "pressed": "released",
				   mb.x,
				   mb.y
		);
	});
	app.on_mouse_wheel_event.connect([](const event::MouseWheel &mw) {
		fmt::print(g_log, "[main]  wheel: {}\n", mw.delta);
	});
	app.on_resize_event.connect([&app](const event::Resize &rs) {
		(void)app;
		(void)rs;
		//app.screen().print(rs.size.width - 10, rs.size.height - 1, fmt::format("size: {}x{}", rs.size.width, rs.size.height));
	});

	return app.run();
}


