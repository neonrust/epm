cmake_minimum_required(VERSION 3.5)

project(epm LANGUAGES CXX)

set(CXX g++)
set(CC gcc)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wextra -Wall -Wpedantic -Wconversion -Werror -Wno-padded)

set(sources
	src/main.cpp
	src/event.h
	src/term.h
	src/term.cpp
	src/term-input.cpp
	src/keycodes.h
	src/keycodes.cpp
)

add_executable(epm ${sources})
target_link_libraries(epm fmt pthread dl)
