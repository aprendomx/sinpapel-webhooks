# Changelog

All notable changes to `sinpapel-webhooks` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — S14.1 (work-in-progress)

- Paquete skeleton (`pyproject.toml`, `LICENSE`, `MANIFEST.in`).
- HMAC-SHA256 signing utilities (`compute_signature`, `verify_signature`)
  con header Stripe-compatible `t=<ts>,v1=<hex>` (ADR-014).
- 5 known-good HMAC test vectors hardcoded para regression protection.
- Exceptions module: `SinpapelWebhooksError`, `WebhookSignatureError`,
  `WebhookDeliveryError`, `WebhookReceiverNotFound`.
- AppConfig skeleton (`SinpapelWebhooksConfig`) — signal connections en T4.

## [0.1.0] - TBD (E14 epic close)

- v0.1.0 inicial — outbound delivery + inbound receiver framework. Ver
  `work/epics/e14-sinpapel-webhooks/` para detalles del epic.
