/*
 * Real-header end-to-end fixture for the AES C/C++ CodeQL pack.
 *
 * Unlike tests/fixtures/codeql/cpp, which declares libc functions by hand, this
 * file includes the system headers so calls resolve exactly as they do in real
 * builds. CI extracts it twice, plain (-O0) and with -O2 -D_FORTIFY_SOURCE=2,
 * and requires the same AES findings from both. gets() is deliberately absent:
 * modern glibc no longer declares it.
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void format_into(char *out, const char *format, va_list args) {
    vsprintf(out, format, args);
}

void real_header_banned(char *out, const char *input, ...) {
    va_list args;
    va_start(args, input);
    format_into(out, input, args);
    va_end(args);

    strcpy(out, input);
    strcat(out, input);
    sprintf(out, "%s", input);
    if (system(input) != 0) {
        return;
    }
    FILE *pipe = popen(input, "r");
    if (pipe != NULL) {
        (void)pclose(pipe);
    }
    int value = atoi(input);
    (void)value;
}

void real_header_review(char *out, size_t len) {
    unsigned char session_key[32];
    memset(session_key, 0, sizeof session_key);
    snprintf(out, len, "discarded");
}
