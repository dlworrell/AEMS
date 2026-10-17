
typedef unsigned long size_t;
extern "C" {
char *gets(char *);
char *strcpy(char *, const char *);
char *strcat(char *, const char *);
int sprintf(char *, const char *, ...);
int vsprintf(char *, const char *, __builtin_va_list);
int atoi(const char *);
long atol(const char *);
long long atoll(const char *);
char *tmpnam(char *);
char *mktemp(char *);
int system(const char *);
void *popen(const char *, const char *);
int scanf(const char *, ...);
int sscanf(const char *, const char *, ...);
int fscanf(void *, const char *, ...);
int snprintf(char *, size_t, const char *, ...);
void *memcpy(void *, const void *, size_t);
void *memmove(void *, const void *, size_t);
char *strncpy(char *, const char *, size_t);
void *malloc(size_t);
void *calloc(size_t, size_t);
void *realloc(void *, size_t);
void free(void *);
void *memset(void *, int, size_t);
void explicit_bzero(void *, size_t);
int pthread_create(void *, const void *, void *(*)(void *), void *);
int sqlite3_exec(void *, const char *, void *, void *, char **);
}

namespace unrelated {
int system(const char *) { return 0; }
char *strcpy(char *out, const char *) { return out; }
}

void banned(char *out, const char *input, __builtin_va_list args) {
    gets(out);
    strcpy(out, input);
    strcat(out, input);
    sprintf(out, "%s", input);
    vsprintf(out, "%s", args);
    (void)atoi(input);
    (void)atol(input);
    (void)atoll(input);
    (void)tmpnam(out);
    (void)mktemp(out);
    (void)system(input);
    (void)popen(input, "r");
    auto indirect = &strcpy;
    indirect(out, input);
    unrelated::system(input);
    unrelated::strcpy(out, input);
    // strcpy(out, input); not executable code
    const char *description = "system and strcpy are banned";
    (void)description;
}

void scanf_cases(char *out, const char *input) {
    scanf("%s", out);
    sscanf(input, "%s", out);
    scanf("%ls", out);
    scanf("%%s %s", out);
    scanf("%31s", out);
    scanf("%*s");
    scanf("%%s");
    scanf("%*s %7s", out);
}

void primitives(char *out, const char *input, size_t len) {
    memcpy(out, input, len);
    memmove(out, input, len);
    strncpy(out, input, len);
    (void)snprintf(out, len, "%s", input);
    void *memory = malloc(len);
    memory = realloc(memory, len);
    free(memory);
    memory = calloc(len, 1);
    free(memory);
    int *object = new int(4);
    delete object;
    int *array = new int[4];
    delete[] array;
    (void)reinterpret_cast<const char *>(object);
    (void)const_cast<char *>(input);
}

void truncation(char *out, size_t len) {
    snprintf(out, len, "truncated");
    (void)snprintf(out, len, "also discarded");
    int result = snprintf(out, len, "checked");
    if (result < 0 || (size_t)result >= len) return;
}

void mutable_key(unsigned char *key, size_t key_len) { (void)key; (void)key_len; }
void missing_length(const unsigned char *secret) { (void)secret; }
void readonly_key(const unsigned char *key, size_t key_len) { (void)key; (void)key_len; }
typedef const unsigned char readonly_byte;
void readonly_typedef(const readonly_byte *key, size_t key_len) { (void)key; (void)key_len; }
void ordinary_output(unsigned char *output, size_t len) { (void)output; (void)len; }

void const_writes(const unsigned char *input, size_t len, unsigned char *out) {
    memset(const_cast<unsigned char *>(input), 0, len);
    unsigned char *alias = const_cast<unsigned char *>(input);
    explicit_bzero(alias, len);
    memcpy(out, input, len);
}

void erasure_review(unsigned char *secret, size_t len, unsigned char *output) {
    memset(secret, 0, len);
    unsigned char *alias = secret;
    memset(alias, 0, len);
    explicit_bzero(secret, len);
    memset(output, 0, len);
}

void async_callback(void *arg, void *(*callback)(void *)) {
    pthread_create(arg, 0, callback, arg);
}

void disk_temporary_state(void *db) {
    sqlite3_exec(db, "PRAGMA temp_store=FILE;", 0, 0, 0);
    const char *query = "pragma main.temp_store = 1;";
    sqlite3_exec(db, query, 0, 0, 0);
    sqlite3_exec(db, "PRAGMA temp_store=MEMORY;", 0, 0, 0);
    sqlite3_exec(db, "PRAGMA temp_store=2;", 0, 0, 0);
    sqlite3_exec(db, "SELECT 'temp_store=FILE'", 0, 0, 0);
}

#include "vendor/external.cpp"
#include "tests/fixtures/synthetic.cpp"

void sql_literal_is_not_a_pragma(void *db) {
    sqlite3_exec(db, "SELECT 'PRAGMA temp_store=FILE;'", 0, 0, 0);
}
