typedef unsigned long size_t;
extern char *strcpy(char *, const char *);
extern int scanf(const char *, ...);
extern void *memset(void *, int, size_t);

void c_policy(char *output, const char *input, size_t len) {
    strcpy(output, input);
    scanf("%s", output);
    scanf("%7s", output);
    memset((void *)input, 0, len);
}
