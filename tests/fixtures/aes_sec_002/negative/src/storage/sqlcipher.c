#include <string.h>

extern int sqlite3_key(void *, const void *, int);
extern int sqlite3_exec(void *, const char *, void *, void *, void *);

int unsafe_open(void *database, unsigned char *key, int key_length, char *target) {
    int result = sqlite3_exec(database, "PRAGMA temp_store = MEMORY;", 0, 0, 0);
    strncpy(target, "unsafe", 6);
    return result == 0 ? sqlite3_key(database, key, key_length) : result;
}
