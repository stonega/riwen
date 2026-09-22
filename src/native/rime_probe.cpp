// Real Rime session, JSON line protocol; never connects to the desktop IBus.
#include "rime_bridge.h"
#include <rime_api.h>
#include <iostream>
#include <sstream>
#include <string>

int main(int argc, char** argv) {
  // Test-only deployment into an explicitly supplied isolated directory.
  if (argc == 3 && std::string(argv[1]) == "--deploy") {
    auto* api = rime_get_api();
    RIME_STRUCT(RimeTraits, traits);
    traits.user_data_dir = argv[2];
    traits.shared_data_dir = argv[2];
    traits.app_name = "rime.riwen.fixture";
    traits.min_log_level = 2;
    traits.log_dir = argv[2];
    api->setup(&traits);
    api->deployer_initialize(&traits);
    return api->deploy() ? 0 : 1;
  }
  if (argc != 4) {
    std::cerr << "Usage: rime-probe USER_DIR LUA_PLUGIN SCHEMA_ID\n";
    return 2;
  }
  if (const auto* error = riwen_init(argv[1], argv[2])) {
    std::cerr << error << '\n'; return 2;
  }
  auto session = riwen_create(argv[3]);
  if (!session) { std::cerr << "Could not create schema session\n"; riwen_finalize(); return 2; }
  std::cout << "{\"ready\":true,\"lua\":true,\"version\":\"" << riwen_version() << "\"}" << std::endl;
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream command(line);
    std::string action;
    command >> action;
    if (action == "quit") break;
    if (action == "type") {
      std::string input; command >> input;
      for (unsigned char key : input) riwen_key(session, key, 0);
    } else if (action == "key") {
      int key = 0, mask = 0;
      if (!(command >> key >> mask)) { std::cerr << "Invalid key\n"; break; }
      riwen_key(session, key, mask);
    } else if (action == "property") {
      std::string name, value; command >> name >> value;
      riwen_property(session, name.c_str(), value.c_str());
    } else if (action == "new") {
      riwen_destroy(session);
      session = riwen_create(argv[3]);
      if (!session) break;
    } else if (action != "get") {
      std::cerr << "Unknown action\n"; break;
    }
    std::cout << riwen_state(session) << std::endl;
  }
  riwen_destroy(session);
  riwen_finalize();
  // Keep the plugin loaded through process exit; registry destructors may use it.
  return 0;
}
