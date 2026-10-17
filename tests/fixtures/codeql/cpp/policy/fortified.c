/* Checked and builtin forms of policy interfaces (isCInterface).
 * Darwin-style _FORTIFY_SOURCE headers rewrite calls with macros, so the call
 * site itself targets __builtin___<name>_chk; glibc exports __<name>_chk. */
typedef unsigned long size_t;
extern char *__strcpy_chk(char *, const char *, size_t);
#define strcpy(d, s) __builtin___strcpy_chk(d, s, __builtin_object_size(d, 1))
#define sprintf(d, ...) __builtin___sprintf_chk(d, 0, __builtin_object_size(d, 1), __VA_ARGS__)

void fortified_forms(char *out, const char *input, size_t len) {
    strcpy(out, input);
    sprintf(out, "%s", input);
    __strcpy_chk(out, input, len);
    __builtin_strcpy(out, input);
    unsigned char session_key[16];
    __builtin___memset_chk(session_key, 0, sizeof session_key, __builtin_object_size(session_key, 0));
    __builtin___snprintf_chk(out, len, 0, len, "%s", input);
}
