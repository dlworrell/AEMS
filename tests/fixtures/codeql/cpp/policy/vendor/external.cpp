extern "C" int system(const char *);
void third_party() { system("upstream"); }
