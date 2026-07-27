#include <stddef.h>
#include <stdint.h>

typedef int (*ab_visitor)(const void *row, void *context);

int ab_database_open_encrypted(const uint8_t *key, size_t key_length);
void ab_database_close(void);
int ab_list_books(ab_visitor visitor, void *context);
