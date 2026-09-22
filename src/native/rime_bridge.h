#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
const char* riwen_init(const char* user_dir, const char* plugin);
const char* riwen_version(void);
uint64_t riwen_create(const char* schema);
void riwen_destroy(uint64_t session);
void riwen_finalize(void);
int riwen_key(uint64_t session, int key, int mask);
void riwen_property(uint64_t session, const char* name, const char* value);
void riwen_clear(uint64_t session);
int riwen_choose(uint64_t session, int index);
const char* riwen_state(uint64_t session);
#ifdef __cplusplus
}
#endif
