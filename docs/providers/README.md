# Provider implementation notes

Per-provider technical details — the API endpoints we call, authentication, field mappings, and known quirks. Useful when:

- You're debugging why your PMS isn't returning the data you expect
- You're adding a new provider and want a reference for what "done" looks like
- The PMS changed their API and we need to track down what broke

Most users don't need any of this — see the main [README](../../README.md) for the user-facing guide and [CONTRIBUTING.md](../../CONTRIBUTING.md) for the contributor onboarding.

## Supported providers

| Provider | Doc | Auth | mark_arrived | mark_checked_out | Verification |
|---|---|---|---|---|---|
| [Host Tools](https://hosttools.com) | [host_tools.md](host_tools.md) | Bearer token | ✅ | ✅ | ✅ Tested against the live API |
| Custom Endpoint | [custom_endpoint.md](custom_endpoint.md) + [backend-api-spec.md](backend-api-spec.md) | Bearer token | ✅ | ✅ | ✅ Contract is small enough to verify by inspection |
| [Hostfully](https://hostfully.com) | — | API key in header | ✅ | ✅ | ⚠️ Not yet verified against a live account |
| [Guesty](https://guesty.com) | — | OAuth2 client credentials | ✅ | ✅ | ⚠️ Not yet verified against a live account |

The Hostfully and Guesty providers were built from the public API documentation and pass the unit-test suite, but no one has run them against a real account end-to-end. If you do, please [open an issue](https://github.com/chschafl/ha-str-concierge/issues) with your findings — the goal is to promote both to "tested" as soon as we have first-hand confirmation.

Want to add another? See [CONTRIBUTING.md → Adding a new PMS provider](../../CONTRIBUTING.md#adding-a-new-pms-provider).
