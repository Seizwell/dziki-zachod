CXX = mpic++
CXXFLAGS = -O2 -Wall -Wextra -std=c++17
TARGET = dziki_zachod

.PHONY: all clean run run4 run6 run8

all: $(TARGET)

$(TARGET): dziki_zachod.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)

# Przykładowe uruchomienia
run4: $(TARGET)
	mpirun --allow-run-as-root -np 4 ./$(TARGET) 2

run6: $(TARGET)
	mpirun --allow-run-as-root -np 6 ./$(TARGET) 2

run8: $(TARGET)
	mpirun --allow-run-as-root -np 8 ./$(TARGET) 4

run: run6
