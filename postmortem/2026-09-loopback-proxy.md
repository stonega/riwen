# Loopback requests inherited the runtime proxy

Synthetic tests found that Bun fetch and Bun's node:http sent loopback requests
through the configured HTTP proxy, returning 502. Installed Bun 1.3.14 did not
disable proxying with `proxy: ""`, `null`, or `false`.

Riwen now adds `127.0.0.1` to `NO_PROXY` and `no_proxy` in its own process before
model requests. Endpoint validation restricts the host and redirects are rejected.
The model test asserts the local server received the structured request, so proxy
errors cannot masquerade as successful invalid-output tests. Only synthetic
phrases were used during development.
