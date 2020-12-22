CXX = g++
#CXX = clang++
FLAGS = -g -Wall

drmexplore: drm.cpp drm.h drmexplore.cpp Makefile
	$(CXX) $(FLAGS) -o drmexplore drm.cpp drmexplore.cpp -lz

clean:
	rm -f drmexplore

