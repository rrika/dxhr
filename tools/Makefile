CC = gcc
CXX = g++
#CXX = clang++
FLAGS = -g -Wall

all: drmexplore bigfuse

drmexplore: drm.cpp drm.h drmexplore.cpp Makefile
	$(CXX) $(FLAGS) -o drmexplore drm.cpp drmexplore.cpp -lz

bigfuse: bigfuse.c Makefile
	$(CC) $(FLAGS) -o bigfuse bigfuse.c `pkg-config fuse --cflags --libs`

clean:
	rm -f drmexplore bigfuse
