#include "rime_bridge.h"
#include <rime_api.h>
#include <dlfcn.h>
#include <sstream>
#include <string>

// Every exported operation is called on one frontend/main thread.
static RimeApi* api = nullptr;
static std::string result;
static std::string user_directory;

static std::string json(const char* raw) {
  std::ostringstream out;
  out << '"';
  for (const unsigned char c : std::string(raw ? raw : "")) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) {
      const char* hex = "0123456789abcdef";
      out << "\\u00" << hex[c >> 4] << hex[c & 15];
    } else out << c;
  }
  out << '"';
  return out.str();
}

static std::string property(uint64_t session, const char* name) {
  char value[1024] = {};
  api->get_property(session, name, value, sizeof(value));
  return value;
}

const char* riwen_init(const char* user_dir, const char* plugin_path) {
  // Keep the module loaded through exit: registry destructors refer to its code.
  if (!dlopen(plugin_path, RTLD_NOW | RTLD_GLOBAL)) {
    result = dlerror(); return result.c_str();
  }
  api = rime_get_api();
  user_directory = user_dir;
  RIME_STRUCT(RimeTraits, traits);
  static const char* modules[] = {"default", "lua", nullptr};
  traits.user_data_dir = user_directory.c_str();
  traits.shared_data_dir = "/usr/share/rime-data";
  traits.app_name = "rime.riwen";
  traits.modules = modules;
  traits.min_log_level = 2;
  traits.log_dir = user_directory.c_str();
  api->setup(&traits);
  api->initialize(&traits);
  return api->find_module("lua") ? nullptr : "Lua module missing";
}

const char* riwen_version() { return api->get_version(); }
uint64_t riwen_create(const char* schema) {
  auto session = api->create_session();
  if (session && api->select_schema(session, schema)) return session;
  if (session) api->destroy_session(session);
  return 0;
}
void riwen_destroy(uint64_t session) { api->destroy_session(session); }
void riwen_finalize() { if (api) { api->finalize(); api = nullptr; } }
int riwen_key(uint64_t session, int key, int mask) { return api->process_key(session, key, mask); }
void riwen_property(uint64_t session, const char* name, const char* value) {
  api->set_property(session, name, value);
}
void riwen_clear(uint64_t session) { api->clear_composition(session); }
int riwen_choose(uint64_t session, int index) {
  return index >= 0 && api->select_candidate_on_current_page(session, index);
}

const char* riwen_state(uint64_t session) {
  RIME_STRUCT(RimeContext, context);
  RIME_STRUCT(RimeCommit, commit);
  const bool has_context = api->get_context(session, &context);
  const bool has_commit = api->get_commit(session, &commit);
  std::ostringstream out;
  out << "{\"input\":" << json(api->get_input(session))
      << ",\"commit\":" << json(has_commit ? commit.text : "")
      << ",\"riwen_session\":" << json(property(session, "riwen_session").c_str())
      << ",\"status\":" << json(property(session, "riwen_status").c_str())
      << ",\"qwen_choice\":" << json(property(session, "riwen_choice").c_str())
      << ",\"preedit\":" << json(has_context ? context.composition.preedit : "")
      << ",\"cursor\":" << (has_context ? context.composition.cursor_pos : 0)
      << ",\"page\":" << (has_context ? context.menu.page_no : 0)
      << ",\"selected\":" << (has_context ? context.menu.highlighted_candidate_index : 0)
      << ",\"candidates\":[";
  if (has_context) {
    for (int i = 0; i < context.menu.num_candidates; ++i) {
      if (i) out << ',';
      out << json(context.menu.candidates[i].text);
    }
  }
  out << "]}";
  if (has_context) api->free_context(&context);
  if (has_commit) api->free_commit(&commit);
  result = out.str();
  return result.c_str();
}
