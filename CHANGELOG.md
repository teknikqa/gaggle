# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project bootstrapped as a gas-only sibling of
  [`haggle`](https://github.com/NaanyaBiz/haggle) (electricity), ported from
  `haggle` commit `04ebc21b53315ec9b176b71c2abfbe69d80ce8d7`: Auth0 PKCE auth
  flow, refresh-token rotation, TLS Trust-On-First-Use pinning, contract
  discovery (`gasContract` filtering), and the statistics-import machinery
  (throttled backfill, trailing rewindow, idempotent recorder writes).
- Solar and Time-of-Use code paths removed (not applicable to gas).
- Gas usage fetch is a deliberate `NotImplementedError` stub pending a real
  AGL gas API capture — see `docs/gas-api.md`.

### Targets for next sprint

- Phase 0: capture AGL's real gas usage endpoint (URL, headers, response
  envelope, units, granularity) from a live device and document it in
  `docs/gas-api.md`, replacing the stub.
