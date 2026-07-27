#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>

extern int sqlite3_key(void *, const void *, int);
extern int sqlite3_exec(void *, const char *, void *, void *, void *);

static void zero_bytes(uint8_t *bytes, size_t length) {
    volatile uint8_t *cursor = bytes;
    while (length > 0U) {
        *cursor++ = 0U;
        length--;
    }
}

static int key_connection(void *database, const uint8_t *key, size_t key_length) {
    int result = sqlite3_key(database, key, (int)key_length);
    if (result == 0) {
        result = sqlite3_exec(database, "PRAGMA temp_store = MEMORY;", 0, 0, 0);
    }
    return result;
}

static int reserve_private_restore(const char *path) {
    return open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
}
