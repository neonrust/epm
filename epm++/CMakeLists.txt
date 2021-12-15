cmake_minimum_required(VERSION 3.5)

project(epm LANGUAGES CXX)

set(CXX g++)
set(CC gcc)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wextra -Wall -Wpedantic -Wconversion -Werror -Wno-padded)

set(sources
	src/main.cpp
	src/app.h
	src/app.cpp
	src/event.h
	src/terminal.h
	src/terminal.cpp
	src/cell.h
	src/size.h
	src/screen.h
	src/screen.cpp
	src/screen-buffer.h
	src/screen-buffer.cpp
	src/input.h
	src/input.cpp
	src/keycodes.h
	src/keycodes.cpp
)

#link_directories(epm extern/termlib/lib/)
include_directories(epm extern/TheWhisp-signals/)

add_executable(epm ${sources})

target_link_libraries(epm fmt pthread dl)
