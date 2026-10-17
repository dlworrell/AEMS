
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

// Secret-name heuristic: every MUST name is reported by MutableKeyParameter and
// CandidateSecretMemset; no MUST-NOT name is reported by either query.
void name_must_session_key(unsigned char *session_key) { (void)session_key; }
void name_must_aes_key(unsigned char *aes_key) { (void)aes_key; }
void name_must_api_key(unsigned char *api_key) { (void)api_key; }
void name_must_api_keys(unsigned char *api_keys) { (void)api_keys; }
void name_must_keyBytes(unsigned char *keyBytes) { (void)keyBytes; }
void name_must_sessionKey(unsigned char *sessionKey) { (void)sessionKey; }
void name_must_m_secret(unsigned char *m_secret) { (void)m_secret; }
void name_must_KEY(unsigned char *KEY) { (void)KEY; }
void name_must_privateKeyBytes(unsigned char *privateKeyBytes) { (void)privateKeyBytes; }
void name_must_secret_2(unsigned char *secret_2) { (void)secret_2; }
void name_must_APIKey(unsigned char *APIKey) { (void)APIKey; }
void name_must_AESKey(unsigned char *AESKey) { (void)AESKey; }
void name_must_secret_valid(unsigned char *secret_valid) { (void)secret_valid; }
void name_must_key_bytes(unsigned char *key_bytes) { (void)key_bytes; }
void name_must_recovery_key(unsigned char *recovery_key) { (void)recovery_key; }
void name_must_derived_key(unsigned char *derived_key) { (void)derived_key; }
void name_must_private_key(unsigned char *private_key) { (void)private_key; }
void name_must_secret_1(unsigned char *secret_1) { (void)secret_1; }
void name_mustnot_keyboard(unsigned char *keyboard) { (void)keyboard; }
void name_mustnot_monkey(unsigned char *monkey) { (void)monkey; }
void name_mustnot_keys_count(unsigned char *keys_count) { (void)keys_count; }
void name_mustnot_key_len(unsigned char *key_len) { (void)key_len; }
void name_mustnot_keyLen(unsigned char *keyLen) { (void)keyLen; }
void name_mustnot_key_id(unsigned char *key_id) { (void)key_id; }
void name_mustnot_hotkey(unsigned char *hotkey) { (void)hotkey; }
void name_mustnot_secretary_note(unsigned char *secretary_note) { (void)secretary_note; }
void name_memset_cases() {
    { unsigned char session_key[16]; memset(session_key, 0, sizeof session_key); } // MUST session_key
    { unsigned char aes_key[16]; memset(aes_key, 0, sizeof aes_key); } // MUST aes_key
    { unsigned char api_key[16]; memset(api_key, 0, sizeof api_key); } // MUST api_key
    { unsigned char api_keys[16]; memset(api_keys, 0, sizeof api_keys); } // MUST api_keys
    { unsigned char keyBytes[16]; memset(keyBytes, 0, sizeof keyBytes); } // MUST keyBytes
    { unsigned char sessionKey[16]; memset(sessionKey, 0, sizeof sessionKey); } // MUST sessionKey
    { unsigned char m_secret[16]; memset(m_secret, 0, sizeof m_secret); } // MUST m_secret
    { unsigned char KEY[16]; memset(KEY, 0, sizeof KEY); } // MUST KEY
    { unsigned char privateKeyBytes[16]; memset(privateKeyBytes, 0, sizeof privateKeyBytes); } // MUST privateKeyBytes
    { unsigned char secret_2[16]; memset(secret_2, 0, sizeof secret_2); } // MUST secret_2
    { unsigned char APIKey[16]; memset(APIKey, 0, sizeof APIKey); } // MUST APIKey
    { unsigned char AESKey[16]; memset(AESKey, 0, sizeof AESKey); } // MUST AESKey
    { unsigned char secret_valid[16]; memset(secret_valid, 0, sizeof secret_valid); } // MUST secret_valid
    { unsigned char key_bytes[16]; memset(key_bytes, 0, sizeof key_bytes); } // MUST key_bytes
    { unsigned char recovery_key[16]; memset(recovery_key, 0, sizeof recovery_key); } // MUST recovery_key
    { unsigned char derived_key[16]; memset(derived_key, 0, sizeof derived_key); } // MUST derived_key
    { unsigned char private_key[16]; memset(private_key, 0, sizeof private_key); } // MUST private_key
    { unsigned char secret_1[16]; memset(secret_1, 0, sizeof secret_1); } // MUST secret_1
    { unsigned char keyboard[16]; memset(keyboard, 0, sizeof keyboard); } // MUST-NOT keyboard
    { unsigned char monkey[16]; memset(monkey, 0, sizeof monkey); } // MUST-NOT monkey
    { unsigned char keys_count[16]; memset(keys_count, 0, sizeof keys_count); } // MUST-NOT keys_count
    { unsigned char key_len[16]; memset(key_len, 0, sizeof key_len); } // MUST-NOT key_len
    { unsigned char keyLen[16]; memset(keyLen, 0, sizeof keyLen); } // MUST-NOT keyLen
    { unsigned char key_id[16]; memset(key_id, 0, sizeof key_id); } // MUST-NOT key_id
    { unsigned char hotkey[16]; memset(hotkey, 0, sizeof hotkey); } // MUST-NOT hotkey
    { unsigned char secretary_note[16]; memset(secretary_note, 0, sizeof secretary_note); } // MUST-NOT secretary_note
}
