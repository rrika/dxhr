CC = gcc
CXX = g++
#CXX = clang++
FLAGS = -g -Wall 
CXXFLAGS = $(FLAGS) -std=c++17

all: drmexplore bigfuse

drmexplore: drm.cpp drm.h drmexplore.cpp script.cpp script.h script_symbols.cpp Makefile
	$(CXX) $(CXXFLAGS) -o drmexplore drm.cpp drmexplore.cpp script.cpp script_symbols.cpp -lz

bigfuse: bigfuse.c Makefile
	$(CC) $(FLAGS) -o bigfuse bigfuse.c `pkg-config fuse --cflags --libs`

clean:
	rm -f drmexplore bigfuse
