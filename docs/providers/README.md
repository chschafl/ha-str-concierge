# Provider implementation notes

Per-provider technical details — the API endpoints we call, authentication, field mappings, and known quirks. Useful when:

- You're debugging why your PMS isn't returning the data you expect
- You're adding a new provider and want a reference for what "done" looks like
- The PMS changed their API and we need to track down what broke

Most users don't need any of this — see the main [README](../../README.md) for the user-facing guide and [CONTRIBUTING.md](../../CONTRIBUTING.md) for the contributor onboarding.

## Supported providers

| Provider | Doc | Auth | mark_arrived | mark_checked_out |
|---|---|---|---|---|
| [Host Tools](https://hosttools.com) | [host_tools.md](host_tools.md) | Bearer token | ✅ | ✅ |
| Custom Endpoint | [custom_endpoint.md](custom_endpoint.md) | Bearer token | ✅ | ✅ |
| [Hostfully](https://hostfully.com) | — | API key in header | ✅ | ✅ |
| [Guesty](https://guesty.com) | — | OAuth2 client credentials | ✅ | ✅ |

Want to add another? See [CONTRIBUTING.md → Adding a new PMS provider](../../CONTRIBUTING.md#adding-a-new-pms-provider).
