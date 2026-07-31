#include <aes_fixture/fixture.h>

int main(void)
{
    return aes_fixture_add(20, 22) == 42 ? 0 : 1;
}
