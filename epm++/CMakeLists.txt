cmake_minimum_required(VERSION 3.5)

project(epm LANGUAGES CXX)

set(CXX g++)
set(CC gcc)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wextra -Wall -Wpedantic -Wconversion -Werror -Wno-padded)

add_executable(epm
	src/main.cpp
	src/event.h
	src/term.h
	src/term.cpp
	src/term-input.cpp
	src/keycodes.h
)

target_link_libraries(epm fmt pthread dl)
