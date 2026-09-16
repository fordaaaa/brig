#include <vector>
#include "foo.h"

// Greeter class.
class Greeter {
public:
    Greeter();
    // Greet a name.
    std::string greet(const std::string& name);
};

// Double a value.
template <typename T>
T double_it(T x) {
    return x * 2;
}
